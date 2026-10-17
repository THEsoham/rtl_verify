"""Final Research Experiment Execution Engine for Cross-Family RTL Verification.

Executes:
- All model pairs (Local and Cloud)
- All 6 conditions: A, B, B', C, C', D
- Both arms: Free-form Arm and Template Arm
- On the benchmark problems meeting Phase A1 (>= 8 non-equivalent mutants) and Phase A6 (golden reference verified)
- Incremental persistence to v2/final/data/
- Full auditing: golden stdout, mutant lists with operators/decisions, full designs used, first-mismatch taxonomy.
"""

import argparse
import csv
import json
import os
import sys
import time
from typing import Any, Dict, List
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from v2.src.llm_client import LLMClient
from v2.src.verilog_sim import VerilogSimulator
from v2.src.mutator import VerilogMutator, Mutant
from v2.src.problems import ProblemLoader, Problem
from v2.src.pipeline import ExperimentPipeline, TrialResult
from v2.src.metrics import (
    compute_condition_metrics,
    compute_wrong_expectation_agreement,
    compute_first_mismatch_taxonomy,
    permutation_test_paired,
    format_k_of_n,
)


def load_config(config_path: str = "d:/rtl-verification/v2/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def precompute_problem_mutants(
    problems: List[Problem],
    mutator: VerilogMutator,
    cache_path: str = "d:/rtl-verification/v2/final/data/precomputed_mutants.json",
) -> Dict[str, List[Mutant]]:
    """Precompute and validate mutants for all benchmark problems, enforcing >= 8 non-equivalent mutants."""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    loaded_cache = {}
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for pid, m_list in raw.items():
                    loaded_cache[pid] = [
                        Mutant(
                            mutant_id=m["mutant_id"],
                            operator=m["operator"],
                            description=m["description"],
                            original_code="",
                            mutated_code=m["mutated_code"],
                            compiles=m["compiles"],
                            is_equivalent=m["is_equivalent"],
                            compile_error=m.get("compile_error", ""),
                            exclusion_reason=m.get("exclusion_reason", ""),
                        )
                        for m in m_list
                    ]
        except Exception as e:
            print(f"Warning: Failed to load mutant cache: {e}")

    final_mutants: Dict[str, List[Mutant]] = {}
    for p in problems:
        pid = p.problem_id
        if pid in loaded_cache and len([m for m in loaded_cache[pid] if m.compiles and not m.is_equivalent]) >= 8:
            final_mutants[pid] = loaded_cache[pid]
            continue

        print(f"Generating mutants for {pid}...")
        cands = mutator.generate_mutants(p.golden_rtl, max_mutants=25)
        validated = mutator.validate_and_filter_mutants(cands, p.golden_rtl)
        non_equiv = [m for m in validated if m.compiles and not m.is_equivalent]
        if len(non_equiv) < 8:
            raise ValueError(
                f"[HARD CHECK FAILED - A1] Problem '{pid}' has only {len(non_equiv)} non-equivalent mutants "
                f"(< 8 minimum required). Problem must be excluded!"
            )
        final_mutants[pid] = validated

    # Save to disk
    cache_export = {}
    for pid, m_list in final_mutants.items():
        cache_export[pid] = [
            {
                "mutant_id": m.mutant_id,
                "operator": m.operator,
                "description": m.description,
                "mutated_code": m.mutated_code,
                "compiles": m.compiles,
                "is_equivalent": m.is_equivalent,
                "compile_error": m.compile_error,
                "exclusion_reason": m.exclusion_reason,
            }
            for m in m_list
        ]
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_export, f, indent=2)

    return final_mutants


def print_compute_budget_estimate(
    num_problems: int,
    num_pairs: int,
    samples_per_problem: int,
    conditions: List[str],
    arms: List[str],
):
    """Estimate compute budget, API cost, GPU time, and tokens before execution."""
    total_runs_per_cell = num_problems * samples_per_problem * len(conditions) * len(arms)
    total_calls = total_runs_per_cell * num_pairs
    avg_tokens_per_call = 900
    total_tokens = total_calls * avg_tokens_per_call
    
    # 50% cloud calls, 50% local calls
    cloud_calls = total_calls // 2
    local_calls = total_calls - cloud_calls
    
    # Cloud cost: average ~$0.30 per 1M tokens
    est_api_cost_usd = (cloud_calls * avg_tokens_per_call / 1_000_000) * 0.30
    
    # Local GPU time: average ~10s per call on RTX 4050
    est_gpu_hours = (local_calls * 10.0) / 3600.0

    print("=" * 70)
    print("COMPUTE BUDGET ESTIMATE (PHASE B6)")
    print("=" * 70)
    print(f"- Problems to Benchmark: {num_problems}")
    print(f"- Model Pairs: {num_pairs}")
    print(f"- Samples per Problem: {samples_per_problem}")
    print(f"- Conditions per Arm: {len(conditions)} ({', '.join(conditions)})")
    print(f"- Experimental Arms: {len(arms)} ({', '.join(arms)})")
    print(f"- Total Experimental Runs: {total_calls:,}")
    print(f"- Estimated Total Tokens: {total_tokens:,}")
    print(f"- Estimated Cloud API Cost: ${est_api_cost_usd:.2f} USD")
    print(f"- Estimated Local GPU Hours: {est_gpu_hours:.2f} hours")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Run Final Cross-Family Verification Experiment.")
    parser.add_argument("--samples", type=int, default=3, help="Samples per problem (default 3)")
    parser.add_argument("--max-problems", type=int, default=30, help="Maximum problems to evaluate (default 30)")
    parser.add_argument("--dry-run", action="store_true", help="Print budget estimate and exit")
    args = parser.parse_args()

    cfg = load_config()
    sim = VerilogSimulator(
        iverilog_path=cfg["simulator"]["iverilog_path"],
        vvp_path=cfg["simulator"]["vvp_path"],
    )
    mutator = VerilogMutator(sim)
    llm_client = LLMClient()
    pipeline = ExperimentPipeline(llm_client, sim, mutator)

    # 1. Load Screened Benchmark Problems meeting A1 and A6
    problem_list_file = "d:/rtl-verification/v2/final/data/problem_list.json"
    with open(problem_list_file, "r", encoding="utf-8") as f:
        screened_meta = json.load(f)

    valid_pids = [item["problem_id"] for item in screened_meta if item["passed"]]
    loader = ProblemLoader()
    all_probs = {p.problem_id: p for p in loader.load_all()}
    
    benchmark_problems = [all_probs[pid] for pid in valid_pids if pid in all_probs][:args.max_problems]
    print(f"Selected {len(benchmark_problems)} verified benchmark problems meeting A1 and A6.")

    # 2. Model Pair Definitions loaded strictly from Config (Phase B2)
    models_by_id = {m["id"]: m for m in cfg["models"]}
    raw_pairs = cfg.get("experiment", {}).get("model_pairs", {})
    model_pairs = {}
    for p_key, p_val in raw_pairs.items():
        model_pairs[p_key] = {
            "name": p_val["name"],
            "G": models_by_id[p_val["generator"]],
            "G_prime": models_by_id[p_val["generator_prime"]],
            "T": models_by_id[p_val["tester"]],
        }

    conditions = ["A", "B", "B_prime", "C", "C_prime", "D"]
    arms = ["freeform", "template"]

    # 3. Print Compute Budget Estimate (Phase B6)
    print_compute_budget_estimate(
        num_problems=len(benchmark_problems),
        num_pairs=len(model_pairs),
        samples_per_problem=args.samples,
        conditions=conditions,
        arms=arms,
    )

    if args.dry_run:
        print("Dry-run requested. Exiting without execution.")
        return

    # 4. Precompute and verify all mutants (Phase A1)
    print("\nPrecomputing and verifying mutant suites across all benchmark problems...")
    mutants_by_prob = precompute_problem_mutants(benchmark_problems, mutator)
    print("All mutant suites successfully verified (>= 8 non-equivalent mutants per problem).")

    # 5. Incremental Execution and Result Persistence with Resume Support
    incremental_file = "d:/rtl-verification/v2/final/data/incremental_trials.jsonl"
    os.makedirs(os.path.dirname(incremental_file), exist_ok=True)

    existing_trials_dict = {}
    if os.path.isfile(incremental_file):
        try:
            with open(incremental_file, "r", encoding="utf-8") as f_inc:
                for line in f_inc:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        # key: (arm, generator_id, tester_id, problem_id, seed, condition)
                        k = (d.get("arm"), d.get("generator_id"), d.get("tester_id"), d.get("problem_id"), d.get("seed"), d.get("condition"))
                        existing_trials_dict[k] = d
            print(f"Loaded {len(existing_trials_dict)} existing trials from {incremental_file} (resuming without recomputation).")
        except Exception as e:
            print(f"Warning: Failed to load incremental log: {e}")

    all_trials: List[TrialResult] = []
    start_total_time = time.time()

    # Optimal condition ordering to minimize model weight swapping:
    # A & D use gen_cfg; B & B_prime use gen_prime_cfg; C & C_prime use test_cfg
    cond_order = ["A", "D", "B", "B_prime", "C", "C_prime"]

    for arm in arms:
        print(f"\n{'='*70}\nSTARTING EXPERIMENTAL ARM: {arm.upper()}\n{'='*70}")
        for pair_key, pair in model_pairs.items():
            print(f"\n--- Model Pair: {pair['name']} (Arm: {arm}) ---")
            gen_cfg = pair["G"]
            gen_prime_cfg = pair["G_prime"]
            test_cfg = pair["T"]

            for p_idx, prob in enumerate(benchmark_problems):
                pid = prob.problem_id
                muts = mutants_by_prob[pid]

                for s_idx in range(args.samples):
                    seed = 42 + s_idx

                    # Check if all conditions for this problem/sample/pair already exist in cache
                    needed_conds = []
                    for cond in cond_order:
                        if cond in ["B", "B_prime"]:
                            c_test_cfg = gen_prime_cfg
                        elif cond in ["C", "C_prime"]:
                            c_test_cfg = test_cfg
                        else:
                            c_test_cfg = gen_cfg
                        k = (arm, gen_cfg["id"], c_test_cfg["id"], pid, seed, cond)
                        if k in existing_trials_dict:
                            all_trials.append(TrialResult(**existing_trials_dict[k]))
                        else:
                            needed_conds.append((cond, c_test_cfg, k))

                    if not needed_conds:
                        continue

                    # Generate Candidate RTL ONCE per (problem, generator, sample) and reuse across all conditions
                    cand_design = pipeline.generate_candidate_design(prob, gen_cfg, seed=seed)

                    for cond, current_test_cfg, k in needed_conds:
                        trial = pipeline.run_problem_condition(
                            problem=prob,
                            condition=cond,
                            gen_model_config=gen_cfg,
                            test_model_config=current_test_cfg,
                            precomputed_mutants=muts,
                            candidate_design=cand_design,
                            seed=seed,
                            arm=arm,
                        )
                        all_trials.append(trial)
                        existing_trials_dict[k] = trial.to_dict()

                        # Incremental write
                        with open(incremental_file, "a", encoding="utf-8") as f_inc:
                            f_inc.write(json.dumps(trial.to_dict()) + "\n")

                print(f"[{p_idx+1}/{len(benchmark_problems)}] Completed {pid} across all conditions and samples.")

    total_elapsed = time.time() - start_total_time
    print(f"\nAll experiments complete! Total runtime: {total_elapsed:.1f}s ({len(all_trials)} trials).")

    # 6. Save Consolidated Deliverables in v2/final/data/
    final_json = "d:/rtl-verification/v2/final/data/final_trials.json"
    final_csv = "d:/rtl-verification/v2/final/data/final_trials.csv"

    dict_trials = [t.to_dict() for t in all_trials]
    with open(final_json, "w", encoding="utf-8") as f:
        json.dump(dict_trials, f, indent=2)

    if dict_trials:
        keys = list(dict_trials[0].keys())
        with open(final_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in dict_trials:
                # Format non-primitive types cleanly for CSV
                row_copy = dict(row)
                for k, v in row_copy.items():
                    if isinstance(v, (list, dict)):
                        row_copy[k] = json.dumps(v)
                writer.writerow(row_copy)

    print(f"Saved full trials to {final_json} and {final_csv}")


if __name__ == "__main__":
    main()
