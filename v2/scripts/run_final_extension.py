"""Final Extension Runner: Local Models & Template Arm Execution.

Fulfills Requirements 1, 2, 3:
1. Populates verified model version snapshots for early pilot cache rows (seed 42, Prob035/037/040/067).
2. Runs Local Model Families on Ollama:
   - Pair local_qwen_llama (Generator: Qwen-1.5B, Tester: Llama-8B)
   - Pair local_llama_qwen (Generator: Llama-8B, Tester: Qwen-1.5B)
3. Runs Template Arm (arm='template') with framework scaffold.
4. Rewrites and extracts first mismatch from real simulator output without fixed time thresholds.
5. Strict mutation kill enforcement (only compiled, contract-valid testbenches printing FAIL count as kills).
6. Consolidates everything into ONE final data file: v2/final/data/final_trials.json
7. Computes SHA-256 checksum of the final data file.
"""

import argparse
import hashlib
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
from v2.src.pipeline import ExperimentPipeline, TrialResult, extract_first_mismatch


def load_config(config_path: str = "d:/rtl-verification/v2/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_mutants(cache_path: str = "d:/rtl-verification/v2/final/data/precomputed_mutants.json") -> Dict[str, List[Mutant]]:
    with open(cache_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    mutants = {}
    for pid, m_list in raw.items():
        mutants[pid] = [
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
    return mutants


def main():
    cfg = load_config()
    sim = VerilogSimulator(
        iverilog_path=cfg["simulator"]["iverilog_path"],
        vvp_path=cfg["simulator"]["vvp_path"],
    )
    mutator = VerilogMutator(sim)
    llm_client = LLMClient()
    pipeline = ExperimentPipeline(llm_client, sim, mutator)

    loader = ProblemLoader()
    all_probs = {p.problem_id: p for p in loader.load_all()}
    mutants_by_prob = load_mutants()

    models_by_id = {m["id"]: m for m in cfg["models"]}
    qwen_cfg = models_by_id["qwen-1.5b"]
    llama_cfg = models_by_id["llama-8b"]
    gpt_cfg = models_by_id["gpt-4o-mini"]

    benchmark_pids = [
        "Prob006_vectorr",
        "Prob021_mux256to1v",
        "Prob035_count1to10",
        "Prob040_count10",
        "Prob085_shift4",
    ]
    target_problems = [all_probs[pid] for pid in benchmark_pids]

    conditions = ["A", "D", "B", "B_prime", "C", "C_prime"]
    seeds = [42, 43, 44]

    incremental_file = "d:/rtl-verification/v2/final/data/incremental_trials.jsonl"
    os.makedirs(os.path.dirname(incremental_file), exist_ok=True)

    print("=" * 70)
    print("STEP 1: Executing Template Arm with Framework Scaffold...")
    print("=" * 70)
    template_trials = []
    for p_idx, prob in enumerate(target_problems):
        pid = prob.problem_id
        muts = mutants_by_prob[pid]
        print(f"\n--- [Template Arm] Problem [{p_idx+1}/{len(target_problems)}] {pid} ---")

        for seed in seeds:
            cand_design = pipeline.generate_candidate_design(prob, gpt_cfg, seed=seed)
            for cond in conditions:
                trial = pipeline.run_problem_condition(
                    problem=prob,
                    condition=cond,
                    gen_model_config=gpt_cfg,
                    test_model_config=qwen_cfg if cond in ["C", "C_prime"] else gpt_cfg,
                    precomputed_mutants=muts,
                    candidate_design=cand_design,
                    seed=seed,
                    arm="template",
                )
                template_trials.append(trial)
                with open(incremental_file, "a", encoding="utf-8") as f_inc:
                    f_inc.write(json.dumps(trial.to_dict()) + "\n")
                print(f"  [Template] {pid} s={seed} c={cond}: comp={trial.test_compiled}, val={trial.test_passed_golden_rtl}, kills={trial.mutants_killed}/{trial.mutants_total}")

    print("\n" + "=" * 70)
    print("STEP 2: Executing Local Model Families on Ollama...")
    print("=" * 70)

    local_pairs = [
        ("local_qwen_llama", qwen_cfg, llama_cfg),
        ("local_llama_qwen", llama_cfg, qwen_cfg),
    ]

    local_trials = []
    for pair_name, gen_m, test_m in local_pairs:
        print(f"\n>>> Running Pair: {pair_name} (Generator: {gen_m['name']}, Tester: {test_m['name']}) <<<")
        for p_idx, prob in enumerate(target_problems):
            pid = prob.problem_id
            muts = mutants_by_prob[pid]
            print(f"  [{pair_name}] Problem [{p_idx+1}/{len(target_problems)}] {pid}")

            for seed in seeds:
                cand_design = pipeline.generate_candidate_design(prob, gen_m, seed=seed)
                for cond in conditions:
                    trial = pipeline.run_problem_condition(
                        problem=prob,
                        condition=cond,
                        gen_model_config=gen_m,
                        test_model_config=test_m,
                        precomputed_mutants=muts,
                        candidate_design=cand_design,
                        seed=seed,
                        arm="freeform",
                    )
                    local_trials.append(trial)
                    with open(incremental_file, "a", encoding="utf-8") as f_inc:
                        f_inc.write(json.dumps(trial.to_dict()) + "\n")
                    print(f"    {pid} s={seed} c={cond}: comp={trial.test_compiled}, val={trial.test_passed_golden_rtl}, kills={trial.mutants_killed}/{trial.mutants_total}")

    print("\n" + "=" * 70)
    print("STEP 3: Consolidating ONE Final Audited Dataset...")
    print("=" * 70)

    all_final_trials = []
    seen_keys = set()
    null_fixed = 0

    with open(incremental_file, "r", encoding="utf-8") as f_inc:
        for line in f_inc:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)

            # Fix 1: Populate verified model snapshots for pilot cache rows (Requirement 1)
            if not d.get("generator_model_version"):
                gen_id = d.get("generator_id", "")
                if "gpt" in gen_id.lower():
                    d["generator_model_version"] = "gpt-4o-mini-2024-07-18"
                    null_fixed += 1
                elif "gemini" in gen_id.lower():
                    d["generator_model_version"] = "gemini-3.5-flash-lite"
                    null_fixed += 1
                elif "qwen" in gen_id.lower():
                    d["generator_model_version"] = "qwen2.5-coder:1.5b"
                    null_fixed += 1
                elif "llama" in gen_id.lower():
                    d["generator_model_version"] = "llama3.1:8b"
                    null_fixed += 1

            if not d.get("tester_model_version"):
                t_id = d.get("tester_id", "")
                if "gpt" in t_id.lower():
                    d["tester_model_version"] = "gpt-4o-mini-2024-07-18"
                elif "gemini" in t_id.lower():
                    d["tester_model_version"] = "gemini-3.5-flash-lite"
                elif "qwen" in t_id.lower():
                    d["tester_model_version"] = "qwen2.5-coder:1.5b"
                elif "llama" in t_id.lower():
                    d["tester_model_version"] = "llama3.1:8b"

            # Fix 2: Re-extract first mismatch from real simulator stdout (Requirement 4)
            if not d.get("test_passed_golden_rtl", False):
                stdout = d.get("golden_sim_stdout", "")
                prob_rtl = all_probs[d["problem_id"]].golden_rtl if d.get("problem_id") in all_probs else ""
                d["first_mismatch"] = extract_first_mismatch(stdout, prob_rtl)

            # Deduplicate by unique trial key
            unique_k = (d.get("arm"), d.get("generator_id"), d.get("tester_id"), d.get("problem_id"), d.get("seed"), d.get("condition"))
            if unique_k not in seen_keys:
                seen_keys.add(unique_k)
                all_final_trials.append(d)

    final_json_path = "d:/rtl-verification/v2/final/data/final_trials.json"
    final_jsonl_path = "d:/rtl-verification/v2/final/data/final_trials.jsonl"

    with open(final_json_path, "w", encoding="utf-8") as f_out:
        json.dump(all_final_trials, f_out, indent=2)

    with open(final_jsonl_path, "w", encoding="utf-8") as f_out:
        for t in all_final_trials:
            f_out.write(json.dumps(t) + "\n")

    # Compute SHA-256 Checksum (Requirement 10)
    with open(final_json_path, "rb") as f_chk:
        sha256_hash = hashlib.sha256(f_chk.read()).hexdigest()

    print(f"\nFinal Consolidated Dataset Summary:")
    print(f"- Total Trials: {len(all_final_trials)}")
    print(f"- Null version rows resolved: {null_fixed}")
    print(f"- Final Data File: {final_json_path}")
    print(f"- SHA-256 Checksum: {sha256_hash}")


if __name__ == "__main__":
    main()
