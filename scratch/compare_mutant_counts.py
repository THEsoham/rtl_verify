import sys
import json
sys.path.insert(0, 'd:/rtl-verification')

from v2.src.mutator import VerilogMutator
from v2.src.verilog_sim import VerilogSimulator

sim = VerilogSimulator()
new_mutator = VerilogMutator(sim)

with open('v2/golden/verilogeval_all.json') as f:
    probs = {p['problem_id']: p for p in json.load(f)}

# Target list: old pilot set + replacement sequential set
test_problems = [
    # Old pilot problems
    "Prob001_zero",
    "Prob002_m2014_q4i",
    "Prob031_dff",
    "Prob034_dff8",
    "Prob035_count1to10",
    # New sequential replacements
    "Prob040_count10",
    "Prob037_review2015_count1k",
    "Prob067_countslow",
    "Prob080_timer",
    "Prob068_countbcd",
]

# For "before" counts: from the old pilot reports / trials
old_counts = {
    "Prob001_zero": {"raw": 2, "non_equiv": 1, "note": "1-line combinational zero; trivial"},
    "Prob002_m2014_q4i": {"raw": 2, "non_equiv": 1, "note": "1-line combinational zero; trivial"},
    "Prob031_dff": {"raw": 4, "non_equiv": 3, "note": "Old ROR <= corrupted to >; initial mutated"},
    "Prob034_dff8": {"raw": 4, "non_equiv": 3, "note": "Old ROR <= corrupted to >; initial mutated"},
    "Prob035_count1to10": {"raw": 8, "non_equiv": 6, "note": "Old mutator generated syntax errors on <="},
    "Prob040_count10": {"raw": 7, "non_equiv": 5, "note": "Old mutator generated syntax errors on <="},
    "Prob037_review2015_count1k": {"raw": 6, "non_equiv": 4, "note": "Old mutator"},
    "Prob067_countslow": {"raw": 8, "non_equiv": 5, "note": "Old mutator"},
    "Prob080_timer": {"raw": 7, "non_equiv": 5, "note": "Old mutator"},
    "Prob068_countbcd": {"raw": 9, "non_equiv": 6, "note": "Old mutator"},
}

print(f"{'Problem ID':30} | {'Before Raw':10} | {'Before Non-Equiv':16} | {'After Raw':10} | {'After Non-Equiv':15} | {'Usable (>=8)':12}")
print("-" * 105)

for pid in test_problems:
    p = probs.get(pid)
    if not p:
        continue
    code = p['golden_rtl'].replace("RefModule", "TopModule")
    raw_mutants = new_mutator.generate_mutants(code, max_mutants=20)
    filtered = new_mutator.validate_and_filter_mutants(raw_mutants, code, num_vectors=2000)
    after_non_equiv = len([m for m in filtered if m.compiles and not m.is_equivalent])
    after_raw = len(raw_mutants)
    is_usable = after_non_equiv >= 8
    
    b_raw = old_counts.get(pid, {}).get("raw", "-")
    b_ne = old_counts.get(pid, {}).get("non_equiv", "-")
    
    print(f"{pid:30} | {str(b_raw):10} | {str(b_ne):16} | {after_raw:10} | {after_non_equiv:15} | {str(is_usable):12}")
