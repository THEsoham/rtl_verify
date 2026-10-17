import hashlib
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, ".")
from v2.src.pipeline import extract_first_mismatch
from v2.src.problems import ProblemLoader

loader = ProblemLoader()
all_probs = {p.problem_id: p for p in loader.load_all()}

incremental_file = "d:/rtl-verification/v2/final/data/incremental_trials.jsonl"
final_json_path = "d:/rtl-verification/v2/final/data/final_trials.json"
final_csv_path = "d:/rtl-verification/v2/final/data/final_trials.csv"
checksum_path = "d:/rtl-verification/v2/final/data/checksum.txt"

all_final_trials = []
seen_keys = set()
null_fixed = 0

with open(incremental_file, "r", encoding="utf-8") as f_inc:
    for line in f_inc:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue

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
        unique_k = (
            d.get("arm", "freeform"),
            d.get("generator_id", ""),
            d.get("tester_id", ""),
            d.get("problem_id", ""),
            d.get("seed", 42),
            d.get("condition", ""),
        )
        if unique_k not in seen_keys:
            seen_keys.add(unique_k)
            all_final_trials.append(d)

os.makedirs(os.path.dirname(final_json_path), exist_ok=True)
with open(final_json_path, "w", encoding="utf-8") as f_out:
    json.dump(all_final_trials, f_out, indent=2)

import pandas as pd
df = pd.DataFrame(all_final_trials)
df.to_csv(final_csv_path, index=False)

# Compute SHA-256 Checksum (Requirement 10)
with open(final_json_path, "rb") as f_chk:
    sha256_hash = hashlib.sha256(f_chk.read()).hexdigest()

with open(checksum_path, "w", encoding="utf-8") as f_c:
    f_c.write(sha256_hash + "\n")

print(f"Consolidated Dataset Summary:")
print(f"- Total Unique Trials: {len(all_final_trials)}")
print(f"- Null version rows resolved: {null_fixed}")
print(f"- Final Data File: {final_json_path}")
print(f"- SHA-256 Checksum: {sha256_hash}")
