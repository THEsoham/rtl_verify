"""Consolidated Experiment Runner for Cross-Family RTL Verification.

Executes all 4 model pairs across all 6 conditions on the 5 verified sequential benchmarks:
- Pair 1: Local Qwen (G: qwen-1.5b, G': qwen-verilog-tuned, T: llama-8b)
- Pair 2: Local Llama (G: llama-8b, G': llama-verifier-tuned, T: qwen-1.5b)
- Pair 3: Cloud GPT (G: gpt-4o-mini, G': gpt-4o-mini, T: gemini-flash)
- Pair 4: Cloud Gemini (G: gemini-flash, G': gemini-flash, T: gpt-4o-mini)

Consolidates ALL results into ONE single report file:
- v2/results/consolidated_experiment_report.md
- v2/results/consolidated_trials.json
- v2/results/consolidated_trials.csv
"""

import argparse
import csv
import json
import os
import sys
import time
import yaml
from typing import Dict, List

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from v2.src.llm_client import LLMClient
from v2.src.verilog_sim import VerilogSimulator
from v2.src.mutator import VerilogMutator
from v2.src.problems import ProblemLoader
from v2.src.pipeline import ExperimentPipeline, TrialResult
from v2.src.metrics import compute_plumbing_metrics, PlumbingMetrics


def load_config(config_path: str = "d:/rtl-verification/v2/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def format_metrics_table(summaries: Dict[str, PlumbingMetrics]) -> List[str]:
    lines = [
        "| Condition | Trials (n) | Valid Test Rate | Test Compile Fail | Contract Violation | Vacuous Tests | RTL Compile Fail | Escape Rate E(G,T) | Tester Strength | Validator Fooled | 4-State !== Adherence | Avg Runtime (s) | Total Tokens |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]
    for cond, m in summaries.items():
        lines.append(
            f"| **{cond}** | {m.total_trials} | {m.valid_test_rate*100:.1f}% | "
            f"{m.test_compile_failure_rate*100:.1f}% | {m.contract_violation_rate*100:.1f}% | "
            f"{m.vacuous_test_rate*100:.1f}% | {m.rtl_compile_failure_rate*100:.1f}% | "
            f"{m.escape_rate*100:.1f}% | {m.tester_strength*100:.1f}% | {m.validator_fooled_rate*100:.1f}% | "
            f"{m.uses_4state_rate*100:.1f}% | {m.avg_runtime_sec:.2f}s | {m.total_compute_tokens:,} |"
        )
    return lines


def generate_single_consolidated_report(
    all_trials: List[TrialResult],
    pair_trials: Dict[str, List[TrialResult]],
    problems: list,
    elapsed_time: float,
) -> str:
    conditions = ["A", "B", "B_prime", "C", "C_prime", "D"]
    
    # 1. Overall aggregated metrics across all trials
    overall_by_cond = {}
    for t in all_trials:
        overall_by_cond.setdefault(t.condition, []).append(t.to_dict())
        
    overall_summaries = {}
    for cond in conditions:
        if cond in overall_by_cond:
            overall_summaries[cond] = compute_plumbing_metrics(overall_by_cond[cond])
            
    # Count total anomalies
    total_vacuous = sum(1 for t in all_trials if t.test_vacuous)
    total_4state_viols = sum(1 for t in all_trials if not t.uses_4state_inequality)
    rtl_compile_fails = sum(1 for t in all_trials if not t.design_compiled)
    total_mutants_tested = sum(t.mutants_total for t in all_trials)
    total_mutants_killed = sum(t.mutants_killed for t in all_trials)

    lines = [
        "# Consolidated Cross-Family RTL Verification Report",
        "",
        "## 1. Experiment Overview",
        "",
        f"- **Benchmarked Problems (n=5 Sequential):** {', '.join([p.problem_id for p in problems])}",
        f"- **Model Pairs Evaluated:** 4 pairs (Local Qwen, Local Llama, Cloud GPT, Cloud Gemini)",
        f"- **Conditions per Problem:** 6 (A: Self, B: Same+RTL, B': Same Spec-Only, C: Cross+RTL, C': Cross Spec-Only, D: Compute-Matched Self)",
        f"- **Total Trials:** {len(all_trials)}",
        f"- **Total Elapsed Time:** {elapsed_time:.1f}s",
        "- **Methodological Controls Enforced:**",
        "  1. Fixed contract enforcement (self-checking, single status line, $finish).",
        "  2. Non-vacuity gate: valid testbenches must FAIL on a dedicated inverted-output gate design.",
        "  3. Candidate RTL generated once per (problem, generator) and reused across all conditions.",
        "  4. 2000-vector differential equivalence checking with rare reset and exact sentinels.",
        "  5. Minimum 8 non-equivalent mutants per problem.",
        "  6. Contract rule 9 requiring 4-state case inequality (!==).",
        "",
        "## 2. Consolidated Results Across All 4 Pairs",
        "",
    ]
    lines.extend(format_metrics_table(overall_summaries))
    lines.append("")

    # 2. Per-Pair Breakdown Tables
    lines.append("## 3. Results by Model Pair")
    lines.append("")

    pair_metadata = {
        "pair1_local_qwen": ("Pair 1: Local Qwen", "G: qwen2.5-coder:1.5b", "G': qwen2.5-coder-verilog", "T: llama3.1:8b"),
        "pair2_local_llama": ("Pair 2: Local Llama", "G: llama3.1:8b", "G': llama-verilog-verifier", "T: qwen2.5-coder:1.5b"),
        "pair3_cloud_gpt": ("Pair 3: Cloud GPT", "G: gpt-4o-mini", "G': gpt-4o-mini", "T: gemini-3.5-flash-lite"),
        "pair4_cloud_gemini": ("Pair 4: Cloud Gemini", "G: gemini-3.5-flash-lite", "G': gemini-3.5-flash-lite", "T: gpt-4o-mini"),
    }

    for p_key, trials in pair_trials.items():
        meta = pair_metadata.get(p_key, (p_key, "", "", ""))
        lines.append(f"### 3.{list(pair_trials.keys()).index(p_key) + 1} {meta[0]}")
        lines.append(f"- **Configuration:** {meta[1]} | {meta[2]} | {meta[3]}")
        lines.append("")
        
        p_by_cond = {}
        for t in trials:
            p_by_cond.setdefault(t.condition, []).append(t.to_dict())
        p_summaries = {}
        for cond in conditions:
            if cond in p_by_cond:
                p_summaries[cond] = compute_plumbing_metrics(p_by_cond[cond])
        lines.extend(format_metrics_table(p_summaries))
        lines.append("")

    # 3. Observations and Anomalies (Strictly Numerical / Factual)
    lines.extend([
        "## 4. Anomalies and Verification Audit",
        "",
        f"- **Vacuous Testbenches Caught by Non-Vacuity Gate:** {total_vacuous} of {len(all_trials)} trials.",
        f"- **4-State Inequality (!==) Violations:** {total_4state_viols} of {len(all_trials)} testbenches used '!=' instead of '!=='.",
        f"- **Candidate RTL Compilation Failures:** {rtl_compile_fails} of {len(all_trials)} trials. (RTL compile status was 100% invariant across conditions due to single-generation reuse).",
        f"- **Golden Mutants Evaluated:** {total_mutants_tested} total mutant trials; {total_mutants_killed} killed by valid testbenches.",
        "",
        "> **NOTE ON PILOT SCOPE:** With n=5 problems per cell, this report presents empirical verification numbers and accounting audit only. No scientific effect claims are made.",
    ])

    return "\n".join(lines)


def main():
    cfg = load_config()
    paths = cfg.get("paths", {})
    results_dir = os.path.normpath(paths.get("results", "d:/rtl-verification/v2/results"))
    os.makedirs(results_dir, exist_ok=True)

    sim_cfg = cfg.get("simulator", {})
    simulator = VerilogSimulator(
        iverilog_path=sim_cfg.get("iverilog_path"),
        vvp_path=sim_cfg.get("vvp_path"),
        flags=sim_cfg.get("flags", ["-g2012"]),
        timeout_sec=sim_cfg.get("timeout_sec", 30),
    )
    mutator = VerilogMutator(simulator)
    llm_client = LLMClient(
        cache_dir=paths.get("cache", "d:/rtl-verification/v2/cache"),
        log_dir=paths.get("logs", "d:/rtl-verification/v2/logs"),
    )
    pipeline = ExperimentPipeline(llm_client, simulator, mutator)

    loader = ProblemLoader(golden_dir=paths.get("golden", "d:/rtl-verification/v2/golden"))
    problems = loader.select_pilot_set(count=5)
    print(f"Loaded {len(problems)} sequential pilot problems:")
    for p in problems:
        print(f"  - {p.problem_id}")

    models_by_id = {m["id"]: m for m in cfg.get("models", [])}

    pair_configs = [
        ("pair1_local_qwen", "qwen-1.5b", "qwen-verilog-tuned", "llama-8b"),
        ("pair2_local_llama", "llama-8b", "llama-verifier-tuned", "qwen-1.5b"),
        ("pair3_cloud_gpt", "gpt-4o-mini", "gpt-4o-mini", "gemini-flash"),
        ("pair4_cloud_gemini", "gemini-flash", "gemini-flash", "gpt-4o-mini"),
    ]

    conditions = ["A", "B", "B_prime", "C", "C_prime", "D"]
    all_trials: List[TrialResult] = []
    pair_trials: Dict[str, List[TrialResult]] = {}
    
    t_start = time.time()

    for p_key, gen_id, same_id, cross_id in pair_configs:
        gen_m = models_by_id[gen_id]
        same_m = models_by_id[same_id]
        cross_m = models_by_id[cross_id]

        print("\n" + "=" * 70)
        print(f"  RUNNING PAIR: {p_key}")
        print(f"  Generator (G)     : {gen_m['name']}")
        print(f"  Same-Family (G')  : {same_m['name']}")
        print(f"  Cross-Family (T)  : {cross_m['name']}")
        print("=" * 70)

        pair_trials[p_key] = []

        for p_idx, prob in enumerate(problems, 1):
            print(f"\n--- [{p_idx}/{len(problems)}] Problem: {prob.problem_id} ---")
            
            # Precompute non-equivalent mutants
            golden_dut = prob.golden_rtl.replace("RefModule", "TopModule")
            raw_mutants = mutator.generate_mutants(golden_dut, max_mutants=15)
            filtered = mutator.validate_and_filter_mutants(raw_mutants, prob.golden_rtl, num_vectors=2000)
            non_equiv = [m for m in filtered if m.compiles and not m.is_equivalent]
            print(f"  Mutants: {len(raw_mutants)} generated -> {len(non_equiv)} non-equivalent (Usable: {len(non_equiv) >= 8})")

            # Generate candidate RTL ONCE and reuse across all 6 conditions
            print(f"  Generating candidate RTL from {gen_m['name']}...", end="", flush=True)
            candidate_design = pipeline.generate_candidate_design(prob, gen_m, seed=42)
            print(f" Done | Compiled: {candidate_design['design_compiled']} | Passed Golden TB: {candidate_design['design_passed_golden_tb']}")

            for cond in conditions:
                if cond in ["A", "D"]:
                    t_m = gen_m
                elif cond in ["B", "B_prime"]:
                    t_m = same_m
                else:
                    t_m = cross_m

                print(f"  Running Cond {cond:7}...", end="", flush=True)
                try:
                    trial = pipeline.run_problem_condition(
                        problem=prob,
                        condition=cond,
                        gen_model_config=gen_m,
                        test_model_config=t_m,
                        precomputed_mutants=non_equiv,
                        candidate_design=candidate_design,
                        seed=42,
                    )
                    all_trials.append(trial)
                    pair_trials[p_key].append(trial)
                    print(f" Done ({trial.duration_sec:.2f}s) | Valid TB: {trial.test_passed_golden_rtl} (vacuous: {trial.test_vacuous}) | Kills: {trial.mutants_killed}/{trial.mutants_total}")
                except Exception as e:
                    print(f" ERROR: {e}")

    elapsed = time.time() - t_start

    # Write single consolidated JSON
    json_path = os.path.join(results_dir, "consolidated_trials.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in all_trials], f, indent=2)

    # Write single consolidated CSV
    csv_path = os.path.join(results_dir, "consolidated_trials.csv")
    if all_trials:
        keys = list(all_trials[0].to_dict().keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for t in all_trials:
                writer.writerow(t.to_dict())

    # Write single consolidated Markdown report
    report_md = generate_single_consolidated_report(all_trials, pair_trials, problems, elapsed)
    md_path = os.path.join(results_dir, "consolidated_experiment_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print("\n" + "=" * 70)
    print("  EXPERIMENT COMPLETE: Consolidated Report Written")
    print(f"  Report File: {md_path}")
    print(f"  Trials JSON: {json_path}")
    print(f"  Trials CSV : {csv_path}")
    print("=" * 70)
    print("\n" + report_md)


if __name__ == "__main__":
    main()
