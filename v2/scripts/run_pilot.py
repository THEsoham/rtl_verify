"""Pilot experiment runner for Cross-Family RTL Verification.

Executes the 20-problem pilot study across Conditions A, B, B', C, C', D.
Saves incremental results to JSON and CSV after every problem.
Generates publication plots and summary statistics.
"""

import argparse
import csv
import json
import os
import sys
import time
import yaml

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from v2.src.llm_client import LLMClient
from v2.src.verilog_sim import VerilogSimulator
from v2.src.mutator import VerilogMutator
from v2.src.problems import ProblemLoader
from v2.src.pipeline import ExperimentPipeline, TrialResult
from v2.src.metrics import compute_condition_metrics, compute_cross_family_advantage
from v2.src.plots import plot_escape_rate_comparison, plot_mutation_score_comparison, generate_results_table_markdown


def load_config(config_path: str = "d:/rtl-verification/v2/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Run Cross-Family RTL Verification Pilot")
    parser.add_argument("--config", default="d:/rtl-verification/v2/config.yaml", help="Path to config.yaml")
    parser.add_argument("--count", type=int, default=20, help="Number of pilot problems")
    parser.add_argument("--dry-run", action="store_true", help="Quick dry run with 1 problem")
    parser.add_argument("--generator", default="qwen-1.5b", help="Generator model ID")
    parser.add_argument("--same-family", default="qwen-verilog-tuned", help="Same-family adversary model ID")
    parser.add_argument("--cross-family", default="llama-8b", help="Cross-family adversary model ID")
    parser.add_argument("--run-name", default="pilot", help="Identifier prefix for output files")
    args = parser.parse_args()

    cfg = load_config(args.config)
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

    # Resolve models
    models_by_id = {m["id"]: m for m in cfg.get("models", [])}
    gen_model = models_by_id.get(args.generator)
    same_model = models_by_id.get(args.same_family, gen_model)
    cross_model = models_by_id.get(args.cross_family)

    if not gen_model or not cross_model:
        print(f"Error: Could not resolve models. Available: {list(models_by_id.keys())}")
        sys.exit(1)

    print("=================================================================")
    print(f"  Cross-Family RTL Verification Experiment (Run: {args.run_name})")
    print("=================================================================")
    print(f"  Generator (G)      : {gen_model['name']} ({gen_model['family']})")
    print(f"  Same-Family (G')   : {same_model['name']} ({same_model['family']})")
    print(f"  Cross-Family (T)   : {cross_model['name']} ({cross_model['family']})")
    print(f"  Simulator          : Icarus Verilog 12.0 ({simulator.iverilog_path})")
    print("=================================================================\n")

    # Load problems
    prob_count = 1 if args.dry_run else args.count
    loader = ProblemLoader(golden_dir=paths.get("golden", "d:/rtl-verification/v2/golden"))
    problems = loader.select_pilot_set(count=prob_count)
    print(f"Loaded {len(problems)} pilot problems (~50% comb, ~50% seq).")

    conditions = ["A", "B", "B_prime", "C", "C_prime", "D"]
    all_trials: List[TrialResult] = []

    json_out = os.path.join(results_dir, f"{args.run_name}_trials.json")
    csv_out = os.path.join(results_dir, f"{args.run_name}_trials.csv")
    summary_md_path = os.path.join(results_dir, f"{args.run_name}_plumbing_report.md")

    total_steps = len(problems) * len(conditions)
    step_num = 0
    t0 = time.time()

    for p_idx, prob in enumerate(problems, 1):
        print(f"\n--- [{p_idx}/{len(problems)}] Problem: {prob.problem_id} ({prob.category}) ---")

        # Precompute and validate non-equivalent mutants of golden RTL using random differential simulation
        golden_dut = prob.golden_rtl.replace("RefModule", "TopModule")
        raw_mutants = mutator.generate_mutants(golden_dut, max_mutants=cfg.get("mutation", {}).get("max_mutants_per_problem", 10))
        valid_mutants = mutator.validate_and_filter_mutants(raw_mutants, prob.golden_rtl)
        non_equiv = [m for m in valid_mutants if m.compiles and not m.is_equivalent]
        ex_log = mutator.last_exclusion_log
        print(f"  Mutants: {ex_log.get('total_generated', len(raw_mutants))} generated -> {len(non_equiv)} valid non-equivalent (Excluded: {ex_log.get('compile_failures', 0)} compile fail, {ex_log.get('equivalent_excluded', 0)} equivalent)")

        # Generate candidate design ONCE per (problem, generator) and reuse in all conditions
        print(f"  Generating candidate RTL from {gen_model['name']}...", end="", flush=True)
        candidate_design = pipeline.generate_candidate_design(prob, gen_model, seed=42)
        print(f" Done | Compiled: {candidate_design['design_compiled']} | Passed Golden TB: {candidate_design['design_passed_golden_tb']}")

        for cond in conditions:
            step_num += 1
            # Select tester model for condition
            if cond == "A" or cond == "D":
                t_model = gen_model
            elif cond in ["B", "B_prime"]:
                t_model = same_model
            else:
                t_model = cross_model

            print(f"  [{step_num}/{total_steps}] Running Condition {cond}...", end="", flush=True)

            try:
                trial = pipeline.run_problem_condition(
                    problem=prob,
                    condition=cond,
                    gen_model_config=gen_model,
                    test_model_config=t_model,
                    precomputed_mutants=non_equiv,
                    candidate_design=candidate_design,
                    seed=42,
                )
                all_trials.append(trial)
                print(f" Done ({trial.duration_sec:.2f}s) | Valid TB: {trial.test_passed_golden_rtl} (vacuous: {trial.test_vacuous}) | Kills: {trial.mutants_killed}/{trial.mutants_total}")
            except Exception as e:
                print(f" ERROR: {e}")

        # Save incremental results to disk
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in all_trials], f, indent=2)

        # Write CSV
        if all_trials:
            keys = list(all_trials[0].to_dict().keys())
            with open(csv_out, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for t in all_trials:
                    writer.writerow(t.to_dict())

    # Compute Plumbing Metrics (Rule 6: Pilot is for plumbing only, no effect claims)
    print("\n=================================================================")
    print("  Aggregating Plumbing Metrics (Plumbing Only — No Effect Claims)...")
    print("=================================================================")
    trials_by_cond = {}
    for t in all_trials:
        trials_by_cond.setdefault(t.condition, []).append(t.to_dict())

    from v2.src.metrics import compute_plumbing_metrics, generate_plumbing_report_markdown

    plumbing_summaries = {}
    for cond in conditions:
        if cond in trials_by_cond:
            plumbing_summaries[cond] = compute_plumbing_metrics(trials_by_cond[cond])

    plumbing_md = generate_plumbing_report_markdown(plumbing_summaries)
    summary_md_path = os.path.join(results_dir, "pilot_plumbing_report.md")
    with open(summary_md_path, "w", encoding="utf-8") as f:
        f.write("# Pilot Plumbing Validation Report\n\n")
        f.write(f"- **Problems Tested:** {len(problems)}\n")
        f.write(f"- **Total Trials:** {len(all_trials)}\n")
        f.write(f"- **Elapsed Wallclock Time:** {time.time() - t0:.1f}s\n\n")
        f.write(plumbing_md)
        f.write("\n\n> **DISCLAIMER:** This pilot is strictly for pipeline verification. No scientific effect claims are made.\n")

    print("\n" + plumbing_md)
    print(f"\nPilot run complete. Plumbing report written to {summary_md_path}")


if __name__ == "__main__":
    main()
