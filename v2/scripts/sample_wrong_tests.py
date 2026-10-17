"""Sample 25 wrong tests for manual expert review.

Extracts 25 concrete cases of testbenches that compiled and satisfied contract
but failed when simulated against verified golden RTL.
"""

import json
import os
import sys

sys.path.insert(0, ".")
from v2.src.pipeline import extract_first_mismatch
from v2.src.problems import ProblemLoader

loader = ProblemLoader()
all_probs = {p.problem_id: p for p in loader.load_all()}

wrong_tests = []
seen_probs = set()

with open("d:/rtl-verification/v2/final/data/incremental_trials.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        t = json.loads(line)
        if t.get("test_compiled") and t.get("test_contract_valid") and not t.get("test_passed_golden_rtl"):
            wrong_tests.append(t)

# Select 25 diverse cases across problems and models
selected = []
# Prioritize diverse problems
for t in wrong_tests:
    pid = t["problem_id"]
    if pid not in seen_probs:
        selected.append(t)
        seen_probs.add(pid)
    if len(selected) >= 20:
        break

# Fill remaining up to 25 with different conditions/models
for t in wrong_tests:
    if t not in selected:
        selected.append(t)
    if len(selected) >= 25:
        break

print(f"Selected {len(selected)} wrong tests for manual inspection.")

records = []
for idx, t in enumerate(selected):
    pid = t["problem_id"]
    prob = all_probs.get(pid)
    golden_rtl = prob.golden_rtl if prob else ""
    stdout = t.get("golden_sim_stdout", "")
    mm = extract_first_mismatch(stdout, golden_rtl)
    
    records.append({
        "sample_id": idx + 1,
        "problem_id": pid,
        "category": prob.category if prob else "unknown",
        "condition": t.get("condition"),
        "generator_id": t.get("generator_id"),
        "tester_id": t.get("tester_id"),
        "seed": t.get("seed"),
        "cycle": mm.get("cycle"),
        "time": mm.get("time"),
        "signal": mm.get("signal"),
        "expected": mm.get("expected"),
        "actual": mm.get("actual"),
        "rule_category": mm.get("category"),
        "raw_line": mm.get("raw_line"),
        "test_code_snippet": t.get("test_code", "")[:400],
    })

with open("d:/rtl-verification/v2/final/data/manual_inspection_25_tests.json", "w", encoding="utf-8") as f:
    json.dump(records, f, indent=2)

print("Saved 25 samples to d:/rtl-verification/v2/final/data/manual_inspection_25_tests.json")
