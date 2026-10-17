"""Statistical metrics computation for RTL verification.

Enforces Phase A3, A4, and Phase C requirements:
1. Recomputable Escape Rate E(G,T) and CorrectBench-style Validator-Fooled Rate (VFR) with exact formulas.
2. Formats all rates as 'k of n (x.x%)' or 'N/A' (never 0.0% when n=0).
3. First-mismatch taxonomy classification:
   - off-by-one timing
   - wrong reset behavior
   - wrong wrap value
   - wrong initial value
   - other
4. Agreement of wrong expectations:
   - Same-model agreement
   - Same-family agreement
   - Cross-family agreement
5. Non-parametric bootstrap 95% confidence intervals (10,000 resamples, fixed seed=42).
6. Exact paired permutation tests and Cohen's d effect sizes.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import re
import numpy as np
from typing import Any, Dict, List, Optional, Tuple


def format_k_of_n(k: int, n: int) -> str:
    """Format k of n with percentage, or N/A when n == 0."""
    if n == 0:
        return "N/A"
    pct = (k / n) * 100.0
    return f"{k} of {n} ({pct:.1f}%)"


def bootstrap_ci(
    data: List[float],
    n_bootstraps: int = 10000,
    ci: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float]:
    """Compute non-parametric bootstrap confidence interval (10,000 resamples)."""
    if not data or len(data) == 0:
        return (0.0, 0.0)
    if len(data) == 1:
        return (float(data[0]), float(data[0]))

    rng = np.random.RandomState(seed)
    arr = np.array(data, dtype=float)
    means = []
    for _ in range(n_bootstraps):
        sample = rng.choice(arr, size=len(arr), replace=True)
        means.append(np.mean(sample))

    alpha = (1.0 - ci) / 2.0
    low = float(np.percentile(means, alpha * 100))
    high = float(np.percentile(means, (1.0 - alpha) * 100))
    return (max(0.0, low), min(1.0, high))


def permutation_test_paired(
    diffs: List[float],
    n_permutations: int = 10000,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Two-sided paired permutation test and Cohen's d effect size.

    Returns:
        (observed_mean_diff, p_value, cohens_d)
    """
    if not diffs or len(diffs) == 0:
        return (0.0, 1.0, 0.0)

    arr = np.array(diffs, dtype=float)
    observed = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    cohens_d = (observed / std) if std > 1e-9 else 0.0

    if np.all(arr == 0):
        return (observed, 1.0, 0.0)

    rng = np.random.RandomState(seed)
    signs = rng.choice([-1.0, 1.0], size=(n_permutations, len(arr)))
    perm_means = np.mean(signs * arr, axis=1)
    p_val = float(np.mean(np.abs(perm_means) >= np.abs(observed)))
    return (observed, p_val, cohens_d)


@dataclass
class ConditionSummary:
    """Statistical summary for an experimental condition with exact k of n accounting."""
    condition: str
    total_designs: int = 0
    compiled_designs: int = 0
    correct_designs: int = 0
    buggy_designs: int = 0
    design_pass_rate: float = 0.0

    total_tests: int = 0
    test_compile_fails: int = 0
    contract_violations: int = 0
    vacuous_tests: int = 0
    wrong_tests: int = 0
    valid_tests: int = 0

    valid_test_rate: float = 0.0
    wrong_test_rate: float = 0.0
    ci_valid_test: Tuple[float, float] = (0.0, 0.0)
    ci_wrong_test: Tuple[float, float] = (0.0, 0.0)
    vacuous_test_rate: float = 0.0
    false_rejection_rate: float = 0.0
    uses_4state_inequality_count: int = 0
    uses_4state_inequality_rate: float = 0.0

    # Mutation Score (valid tests only)
    valid_test_mutants_tested: int = 0
    valid_test_mutants_killed: int = 0
    mutation_score: float = 0.0
    ci_mutation_score: Tuple[float, float] = (0.0, 0.0)

    # Tester Strength on all golden mutants
    total_mutants_available: int = 0
    total_mutants_killed: int = 0
    tester_strength: float = 0.0

    # Escape Rate E(G,T) on naturally wrong designs
    evaluable_natural_bugs: int = 0
    escaped_natural_bugs: int = 0
    escape_rate: Optional[float] = None
    ci_escape_rate: Tuple[float, float] = (0.0, 0.0)

    # CorrectBench-style Validator-Fooled Rate
    wrong_tests_evaluated: int = 0
    validator_fooled_count: int = 0
    validator_fooled_rate: Optional[float] = None

    # Compute & Tokens
    total_generator_tokens: int = 0
    total_tester_tokens: int = 0
    total_compute_tokens: int = 0
    generator_retries: int = 0
    tester_retries: int = 0
    avg_runtime_sec: float = 0.0
    total_runtime_sec: float = 0.0

    @property
    def mutants_killed(self) -> int:
        return self.valid_test_mutants_killed

    @property
    def mutants_tested(self) -> int:
        return self.valid_test_mutants_tested

    @property
    def naturally_buggy_tested(self) -> int:
        return self.evaluable_natural_bugs

    @property
    def naturally_buggy_escaped(self) -> int:
        return self.escaped_natural_bugs

    @property
    def validator_fooled_total(self) -> int:
        return self.wrong_tests_evaluated

    @property
    def mean_generator_tokens(self) -> float:
        return (self.total_generator_tokens / max(1, self.total_tests))

    @property
    def mean_tester_tokens(self) -> float:
        return (self.total_tester_tokens / max(1, self.total_tests))

    @property
    def total_retries(self) -> int:
        return self.generator_retries + self.tester_retries

    @property
    def mean_duration_sec(self) -> float:
        return self.avg_runtime_sec

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "total_designs": self.total_designs,
            "design_pass": format_k_of_n(self.correct_designs, self.total_designs),
            "test_outcomes": {
                "total": self.total_tests,
                "compiled": format_k_of_n(self.total_tests - self.test_compile_fails, self.total_tests),
                "contract_valid": format_k_of_n(self.total_tests - self.test_compile_fails - self.contract_violations, self.total_tests),
                "vacuous": format_k_of_n(self.vacuous_tests, self.total_tests),
                "wrong_test": format_k_of_n(self.wrong_tests, self.total_tests),
                "valid": format_k_of_n(self.valid_tests, self.total_tests),
            },
            "mutation_score_valid_only": format_k_of_n(self.valid_test_mutants_killed, self.valid_test_mutants_tested),
            "mutation_score_value": round(self.mutation_score, 4),
            "ci_mutation_score_95": [round(x, 4) for x in self.ci_mutation_score],
            "tester_strength": format_k_of_n(self.total_mutants_killed, self.total_mutants_available),
            "tester_strength_value": round(self.tester_strength, 4),
            "escape_rate": format_k_of_n(self.escaped_natural_bugs, self.evaluable_natural_bugs) if self.evaluable_natural_bugs > 0 else "N/A",
            "escape_rate_value": round(self.escape_rate, 4) if self.escape_rate is not None else None,
            "ci_escape_rate_95": [round(x, 4) for x in self.ci_escape_rate] if self.evaluable_natural_bugs > 0 else [0.0, 0.0],
            "validator_fooled_rate": format_k_of_n(self.validator_fooled_count, self.wrong_tests_evaluated) if self.wrong_tests_evaluated > 0 else "N/A",
            "validator_fooled_value": round(self.validator_fooled_rate, 4) if self.validator_fooled_rate is not None else None,
            "tokens": {
                "generator_tokens": self.total_generator_tokens,
                "tester_tokens": self.total_tester_tokens,
                "total_tokens": self.total_compute_tokens,
            },
            "retries": {
                "generator_retries": self.generator_retries,
                "tester_retries": self.tester_retries,
            },
            "runtime_sec": round(self.total_runtime_sec, 2),
        }


def compute_condition_metrics(records: List[Any], majority_threshold: float = 0.5) -> ConditionSummary:
    """Aggregate trial records into ConditionSummary with exact recomputed metrics."""
    if not records:
        return ConditionSummary(condition="empty")

    # Normalize records to dicts
    dict_records = [r.to_dict() if hasattr(r, "to_dict") else r for r in records]
    records = dict_records

    cond = records[0].get("condition", "unknown")
    summary = ConditionSummary(condition=cond)

    summary.total_designs = len(records)
    summary.compiled_designs = sum(1 for r in records if r.get("design_compiled", False))
    summary.correct_designs = sum(1 for r in records if r.get("design_passed_golden_tb", False))
    summary.buggy_designs = summary.total_designs - summary.correct_designs
    summary.design_pass_rate = summary.correct_designs / max(1, summary.total_designs)

    summary.total_tests = len(records)
    summary.test_compile_fails = sum(1 for r in records if not r.get("test_compiled", False))
    summary.contract_violations = sum(1 for r in records if r.get("test_compiled", False) and not r.get("test_contract_valid", True))
    summary.vacuous_tests = sum(1 for r in records if r.get("test_vacuous", False))
    summary.valid_tests = sum(1 for r in records if r.get("test_passed_golden_rtl", False))

    # A wrong test compiles, obeys contract, is non-vacuous, but FAILS on the golden RTL
    summary.wrong_tests = sum(
        1 for r in records
        if r.get("test_compiled", False)
        and r.get("test_contract_valid", True)
        and not r.get("test_vacuous", False)
        and not r.get("test_passed_golden_rtl", False)
    )

    summary.valid_test_rate = summary.valid_tests / max(1, summary.total_tests)
    summary.wrong_test_rate = summary.wrong_tests / max(1, summary.total_tests)
    summary.vacuous_test_rate = summary.vacuous_tests / max(1, summary.total_tests)
    summary.false_rejection_rate = summary.wrong_tests / max(1, summary.total_tests)

    val_samples = [1.0 if r.get("test_passed_golden_rtl", False) else 0.0 for r in records]
    wrong_samples = [
        1.0 if (
            r.get("test_compiled", False)
            and r.get("test_contract_valid", True)
            and not r.get("test_vacuous", False)
            and not r.get("test_passed_golden_rtl", False)
        ) else 0.0
        for r in records
    ]
    summary.ci_valid_test = bootstrap_ci(val_samples, n_bootstraps=10000, seed=42)
    summary.ci_wrong_test = bootstrap_ci(wrong_samples, n_bootstraps=10000, seed=42)

    summary.uses_4state_inequality_count = sum(1 for r in records if r.get("uses_4state_inequality", True))
    summary.uses_4state_inequality_rate = summary.uses_4state_inequality_count / max(1, summary.total_tests)

    # Mutation score on valid tests only
    valid_test_records = [r for r in records if r.get("test_passed_golden_rtl", False)]
    ms_samples = []
    v_tested = 0
    v_killed = 0
    for r in valid_test_records:
        t_tot = r.get("mutants_total", 0)
        t_kld = r.get("mutants_killed", 0)
        if t_tot > 0:
            v_tested += t_tot
            v_killed += t_kld
            ms_samples.append(t_kld / t_tot)

    summary.valid_test_mutants_tested = v_tested
    summary.valid_test_mutants_killed = v_killed
    summary.mutation_score = (v_killed / v_tested) if v_tested > 0 else 0.0
    summary.ci_mutation_score = bootstrap_ci(ms_samples, n_bootstraps=10000, seed=42)

    # Tester strength on valid tests (Requirement 7: use only valid tests in denominator)
    summary.total_mutants_available = v_tested
    summary.total_mutants_killed = v_killed
    summary.tester_strength = (v_killed / v_tested) if v_tested > 0 else 0.0

    # Escape Rate E(G,T) on naturally wrong candidate designs
    # Denominator: naturally wrong designs (design_passed_golden_tb == False) evaluated by valid testbenches
    # Numerator: valid testbench passed the naturally wrong design (natural_bug_escaped == True)
    eval_bugs = [r for r in records if r.get("natural_bug_tested", False)]
    escaped_bugs = sum(1 for r in eval_bugs if r.get("natural_bug_escaped", False))
    summary.evaluable_natural_bugs = len(eval_bugs)
    summary.escaped_natural_bugs = escaped_bugs
    if len(eval_bugs) > 0:
        summary.escape_rate = escaped_bugs / len(eval_bugs)
        esc_samples = [1.0 if r.get("natural_bug_escaped", False) else 0.0 for r in eval_bugs]
        summary.ci_escape_rate = bootstrap_ci(esc_samples, n_bootstraps=10000, seed=42)
    else:
        summary.escape_rate = None
        summary.ci_escape_rate = (0.0, 0.0)

    # CorrectBench-style Validator-Fooled Rate:
    # A wrong testbench fools the validator if the majority of LLM designs pass it.
    wrong_records = [
        r for r in records
        if r.get("test_compiled", False)
        and r.get("test_contract_valid", True)
        and not r.get("test_passed_golden_rtl", False)
    ]
    summary.wrong_tests_evaluated = len(wrong_records)
    # If a wrong test had natural_bug_escaped == True, it accepted a wrong design
    fooled_count = sum(1 for r in wrong_records if r.get("natural_bug_escaped", False))
    summary.validator_fooled_count = fooled_count
    if len(wrong_records) > 0:
        summary.validator_fooled_rate = fooled_count / len(wrong_records)
    else:
        summary.validator_fooled_rate = None

    # Tokens and compute
    summary.total_generator_tokens = sum(r.get("generator_tokens", 0) for r in records)
    summary.total_tester_tokens = sum(r.get("tester_tokens", 0) for r in records)
    summary.total_compute_tokens = summary.total_generator_tokens + summary.total_tester_tokens
    summary.generator_retries = sum(r.get("generator_retries", 0) for r in records)
    summary.tester_retries = sum(r.get("tester_retries", 0) for r in records)

    durations = [r.get("duration_sec", 0.0) for r in records]
    summary.avg_runtime_sec = float(np.mean(durations)) if durations else 0.0
    summary.total_runtime_sec = float(np.sum(durations)) if durations else 0.0

    return summary


class WrongAgreementResults(dict):
    """Container for wrong expectation agreement metrics supporting dict & property access."""
    @property
    def same_model_agreement_count(self) -> int:
        return self["same_model"]["agreed"]
    @property
    def same_model_pairs_total(self) -> int:
        return self["same_model"]["total"]
    @property
    def same_model_agreement_rate(self) -> float:
        return self["same_model"]["rate"] if self["same_model"]["rate"] is not None else 0.0
    @property
    def ci_same_model(self) -> Tuple[float, float]:
        return self["same_model"]["ci"]

    @property
    def same_family_agreement_count(self) -> int:
        return self["same_family"]["agreed"]
    @property
    def same_family_pairs_total(self) -> int:
        return self["same_family"]["total"]
    @property
    def same_family_agreement_rate(self) -> float:
        return self["same_family"]["rate"] if self["same_family"]["rate"] is not None else 0.0
    @property
    def ci_same_family(self) -> Tuple[float, float]:
        return self["same_family"]["ci"]

    @property
    def cross_family_agreement_count(self) -> int:
        return self["cross_family"]["agreed"]
    @property
    def cross_family_pairs_total(self) -> int:
        return self["cross_family"]["total"]
    @property
    def cross_family_agreement_rate(self) -> float:
        return self["cross_family"]["rate"] if self["cross_family"]["rate"] is not None else 0.0
    @property
    def ci_cross_family(self) -> Tuple[float, float]:
        return self["cross_family"]["ci"]


class TaxonomyResults(dict):
    """Container for taxonomy counts supporting category dict lookups, sum(values()), and detailed breakdown."""
    def __init__(self, counts: Dict[str, int], breakdown: Dict[str, Any], total: int):
        super().__init__(counts)
        self.categories = breakdown
        self.total_wrong_tests = total


def compute_wrong_expectation_agreement(wrong_trials: List[Any]) -> WrongAgreementResults:
    """Compute agreement rates of wrong first-expectations across model pairs.

    Requirement 5:
    Define "same wrong expectation" as:
      same problem + same signal + same cycle index (not wall time) + same expected value.
    Compute it ONLY between tests for the SAME design and seed.
    Report same-model, same-family, and cross-family rows separately.
    Resample by problem (cluster bootstrap, B=10000).
    Show k of n per cell.
    """
    dict_trials = [t.to_dict() if hasattr(t, "to_dict") else t for t in wrong_trials]

    # Filter to wrong tests (compiled, contract-valid, failed golden RTL)
    filtered_trials = [
        t for t in dict_trials
        if t.get("test_compiled", False)
        and t.get("test_contract_valid", True)
        and not t.get("test_passed_golden_rtl", False)
    ]

    def normalize_val(v):
        if v is None:
            return ""
        s = str(v).lower().strip()
        m_radix = re.search(r"'(?:b|d|h|o)([0-9a-fxz_]+)", s)
        if m_radix:
            s = m_radix.group(1).replace("_", "")
        return s.lstrip("0") or "0"

    def get_family(m_id):
        m = (m_id or "").lower()
        if "qwen" in m:
            return "qwen"
        elif "llama" in m:
            return "llama"
        elif "gpt" in m or "openai" in m:
            return "openai"
        elif "gemini" in m:
            return "gemini"
        elif "gemma" in m:
            return "gemma"
        return "other"

    # Group by (problem_id, seed) -> SAME design and seed
    by_design_seed = defaultdict(list)
    for t in filtered_trials:
        pid = t.get("problem_id", "")
        sd = t.get("seed", 42)
        by_design_seed[(pid, sd)].append(t)

    # Problem-level cluster buckets: pid -> list of (cell, agreed: bool)
    problem_pairs = defaultdict(list)

    for (pid, sd), group in by_design_seed.items():
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                t1, t2 = group[i], group[j]
                m1 = t1.get("first_mismatch", {}) or {}
                m2 = t2.get("first_mismatch", {}) or {}

                c1, c2 = m1.get("cycle"), m2.get("cycle")
                s1, s2 = (m1.get("signal") or "").lower(), (m2.get("signal") or "").lower()
                e1, e2 = normalize_val(m1.get("expected")), normalize_val(m2.get("expected"))

                # Same wrong expectation: same problem + same signal + same cycle index + same expected value
                agreed = False
                if c1 is not None and c2 is not None and c1 == c2 and s1 == s2 and e1 == e2 and e1 != "":
                    agreed = True

                id1 = t1.get("tester_id", "")
                id2 = t2.get("tester_id", "")
                f1 = get_family(id1)
                f2 = get_family(id2)

                if id1 == id2:
                    cell = "same_model"
                elif f1 == f2:
                    cell = "same_family"
                else:
                    cell = "cross_family"

                problem_pairs[pid].append((cell, agreed))

    # Aggregate counts across all problems
    counts = {
        "same_model": {"agreed": 0, "total": 0},
        "same_family": {"agreed": 0, "total": 0},
        "cross_family": {"agreed": 0, "total": 0},
    }
    for pid, pairs in problem_pairs.items():
        for cell, agreed in pairs:
            counts[cell]["total"] += 1
            if agreed:
                counts[cell]["agreed"] += 1

    # Cluster bootstrap resampling by problem (B=10000)
    all_problems = sorted(list(problem_pairs.keys()))
    rng = np.random.RandomState(42)

    ci_res = {}
    for cell in ["same_model", "same_family", "cross_family"]:
        tot = counts[cell]["total"]
        agr = counts[cell]["agreed"]
        rate = (agr / tot) if tot > 0 else 0.0

        if tot == 0 or len(all_problems) == 0:
            ci_res[cell] = (0.0, 0.0)
            continue

        boot_rates = []
        for _ in range(10000):
            sampled_probs = rng.choice(all_problems, size=len(all_problems), replace=True)
            b_tot = 0
            b_agr = 0
            for sp in sampled_probs:
                for c, a in problem_pairs[sp]:
                    if c == cell:
                        b_tot += 1
                        if a:
                            b_agr += 1
            if b_tot > 0:
                boot_rates.append(b_agr / b_tot)
            else:
                boot_rates.append(rate)

        lo = float(np.percentile(boot_rates, 2.5))
        hi = float(np.percentile(boot_rates, 97.5))
        ci_res[cell] = (lo, hi)

    return WrongAgreementResults({
        "same_model": {
            "agreed": counts["same_model"]["agreed"],
            "total": counts["same_model"]["total"],
            "rate_str": format_k_of_n(counts["same_model"]["agreed"], counts["same_model"]["total"]),
            "rate": counts["same_model"]["agreed"] / max(1, counts["same_model"]["total"]) if counts["same_model"]["total"] > 0 else None,
            "ci": ci_res["same_model"],
        },
        "same_family": {
            "agreed": counts["same_family"]["agreed"],
            "total": counts["same_family"]["total"],
            "rate_str": format_k_of_n(counts["same_family"]["agreed"], counts["same_family"]["total"]),
            "rate": counts["same_family"]["agreed"] / max(1, counts["same_family"]["total"]) if counts["same_family"]["total"] > 0 else None,
            "ci": ci_res["same_family"],
        },
        "cross_family": {
            "agreed": counts["cross_family"]["agreed"],
            "total": counts["cross_family"]["total"],
            "rate_str": format_k_of_n(counts["cross_family"]["agreed"], counts["cross_family"]["total"]),
            "rate": counts["cross_family"]["agreed"] / max(1, counts["cross_family"]["total"]) if counts["cross_family"]["total"] > 0 else None,
            "ci": ci_res["cross_family"],
        },
    })


def compute_first_mismatch_taxonomy(trials: List[Any]) -> TaxonomyResults:
    """Taxonomy breakdown of wrong test failure modes."""
    dict_trials = [t.to_dict() if hasattr(t, "to_dict") else t for t in trials]
    wrong_trials = [
        t for t in dict_trials
        if t.get("test_compiled", False)
        and t.get("test_contract_valid", True)
        and not t.get("test_passed_golden_rtl", False)
    ]

    counts = {
        "off_by_one_timing": 0,
        "wrong_reset_behavior": 0,
        "wrong_wrap_value": 0,
        "wrong_initial_value": 0,
        "other": 0,
    }

    for t in wrong_trials:
        mm = t.get("first_mismatch", {})
        cat = mm.get("category", "other")
        counts[cat] = counts.get(cat, 0) + 1

    total = len(wrong_trials)
    breakdown = {}
    for cat, count in counts.items():
        breakdown[cat] = {
            "count": count,
            "total": total,
            "formatted": format_k_of_n(count, total),
            "rate": (count / total) if total > 0 else 0.0,
        }
    return TaxonomyResults(counts=counts, breakdown=breakdown, total=total)


@dataclass
class PlumbingMetrics:
    """Plumbing metrics for pipeline health validation."""
    condition: str
    total_trials: int = 0
    valid_test_rate: float = 0.0
    test_compile_failure_rate: float = 0.0
    contract_violation_rate: float = 0.0
    vacuous_test_rate: float = 0.0
    rtl_compile_failure_rate: float = 0.0
    generator_retry_rate: float = 0.0
    tester_retry_rate: float = 0.0
    escape_rate: Optional[float] = None
    tester_strength: float = 0.0
    validator_fooled_rate: Optional[float] = None
    uses_4state_rate: float = 0.0
    avg_runtime_sec: float = 0.0
    total_runtime_sec: float = 0.0
    total_compute_tokens: int = 0
    retry_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "total_trials": self.total_trials,
            "valid_test_rate": round(self.valid_test_rate, 4),
            "test_compile_failure_rate": round(self.test_compile_failure_rate, 4),
            "contract_violation_rate": round(self.contract_violation_rate, 4),
            "vacuous_test_rate": round(self.vacuous_test_rate, 4),
            "rtl_compile_failure_rate": round(self.rtl_compile_failure_rate, 4),
            "generator_retry_rate": round(self.generator_retry_rate, 4),
            "tester_retry_rate": round(self.tester_retry_rate, 4),
            "escape_rate": round(self.escape_rate, 4) if self.escape_rate is not None else None,
            "tester_strength": round(self.tester_strength, 4),
            "validator_fooled_rate": round(self.validator_fooled_rate, 4) if self.validator_fooled_rate is not None else None,
            "uses_4state_rate": round(self.uses_4state_rate, 4),
            "avg_runtime_sec": round(self.avg_runtime_sec, 2),
            "total_runtime_sec": round(self.total_runtime_sec, 2),
            "total_compute_tokens": self.total_compute_tokens,
            "retry_tokens": self.retry_tokens,
        }


def compute_plumbing_metrics(records: List[Dict]) -> PlumbingMetrics:
    """Compute plumbing-only metrics without narrative conclusions."""
    if not records:
        return PlumbingMetrics(condition="empty")

    cond = records[0].get("condition", "unknown")
    total = len(records)
    valid_tests = sum(1 for r in records if r.get("test_passed_golden_rtl", False))
    test_compile_fails = sum(1 for r in records if not r.get("test_compiled", False))
    contract_violations = sum(1 for r in records if r.get("test_compiled", False) and not r.get("test_contract_valid", True))
    vacuous_tests = sum(1 for r in records if r.get("test_vacuous", False))
    rtl_compile_fails = sum(1 for r in records if not r.get("design_compiled", False))
    gen_retries = sum(1 for r in records if r.get("generator_retries", 0) > 0)
    test_retries = sum(1 for r in records if r.get("tester_retries", 0) > 0)
    uses_4state = sum(1 for r in records if r.get("uses_4state_inequality", True))

    # Escape rate E(G, T)
    eval_bugs = [r for r in records if r.get("natural_bug_tested", False)]
    escaped_bugs = sum(1 for r in eval_bugs if r.get("natural_bug_escaped", False))
    esc_rate = (escaped_bugs / len(eval_bugs)) if len(eval_bugs) > 0 else None

    # Tester strength on golden mutants
    tot_mut = sum(r.get("problem_mutants_total", r.get("mutants_total", 0)) for r in records)
    kld_mut = sum(r.get("mutants_killed", 0) for r in records)
    tester_str = (kld_mut / tot_mut) if tot_mut > 0 else 0.0

    # Validator-fooled rate
    wrong_records = [
        r for r in records
        if r.get("test_compiled", False)
        and r.get("test_contract_valid", True)
        and not r.get("test_passed_golden_rtl", False)
    ]
    fooled = sum(1 for r in wrong_records if r.get("natural_bug_escaped", False))
    vfr = (fooled / len(wrong_records)) if len(wrong_records) > 0 else None

    durations = [r.get("duration_sec", 0.0) for r in records]
    tokens = sum(r.get("total_tokens", 0) for r in records)
    retry_toks = sum(r.get("generator_retry_tokens", 0) + r.get("tester_retry_tokens", 0) for r in records)

    return PlumbingMetrics(
        condition=cond,
        total_trials=total,
        valid_test_rate=valid_tests / max(1, total),
        test_compile_failure_rate=test_compile_fails / max(1, total),
        contract_violation_rate=contract_violations / max(1, total),
        vacuous_test_rate=vacuous_tests / max(1, total),
        rtl_compile_failure_rate=rtl_compile_fails / max(1, total),
        generator_retry_rate=gen_retries / max(1, total),
        tester_retry_rate=test_retries / max(1, total),
        escape_rate=esc_rate,
        tester_strength=tester_str,
        validator_fooled_rate=vfr,
        uses_4state_rate=uses_4state / max(1, total),
        avg_runtime_sec=float(np.mean(durations)) if durations else 0.0,
        total_runtime_sec=float(np.sum(durations)) if durations else 0.0,
        total_compute_tokens=tokens,
        retry_tokens=retry_toks,
    )
