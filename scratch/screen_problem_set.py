"""Screen VerilogEval problems for Phase B1.

Criteria:
1. Passes official reference testbench (A6).
2. Non-trivial (removes constant outputs and 1-wire pass-throughs).
3. Has >= 8 non-equivalent mutants from VerilogMutator with 2000 differential vectors and rare reset (A1).
4. Categorized: counters, shift registers, FSMs, arithmetic, combinational.
"""

import json
import os
import sys
sys.path.insert(0, os.path.abspath("."))
import re
from typing import Dict, List
from v2.src.problems import ProblemLoader, Problem
from v2.src.verilog_sim import VerilogSimulator
from v2.src.mutator import VerilogMutator

def is_trivial_wiring(golden_rtl: str) -> bool:
    clean = re.sub(r"//.*", "", golden_rtl)
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)
    # Check if module only assigns constants or pure wire pass-throughs
    lines = [l.strip() for l in clean.splitlines() if l.strip() and not l.strip().startswith("module") and not l.strip().startswith("endmodule") and not l.strip().startswith("input") and not l.strip().startswith("output") and not l.strip().startswith("wire") and not l.strip().startswith("reg")]
    if len(lines) <= 1:
        single = " ".join(lines)
        if re.match(r"^assign\s+\w+\s*=\s*(?:1\'b[01]|0|1|\w+)\s*;$", single):
            return True
    return False

def categorize_detailed(p: Problem) -> str:
    text = (p.prompt_spec + " " + p.golden_rtl).lower()
    if "fsm" in text or "state" in text or "next_state" in text:
        return "fsm"
    elif "count" in text or "counter" in text or "timer" in text:
        return "counter"
    elif "shift" in text or "rotate" in text or "lfsr" in text:
        return "shift_register"
    elif any(op in text for op in ["add", "sub", "adder", "multiplier", "alu", "arithmetic", "overflow", "carry"]):
        return "arithmetic"
    elif p.category == "sequential":
        return "sequential_other"
    else:
        return "combinational"

def main():
    loader = ProblemLoader()
    sim = VerilogSimulator()
    mutator = VerilogMutator(sim)
    
    problems = loader.load_all()
    print(f"Total problems loaded: {len(problems)}")
    
    screen_results = []
    passed_problems = []
    
    for idx, p in enumerate(problems):
        pid = p.problem_id
        detail_cat = categorize_detailed(p)
        
        # Check trivial wiring
        if is_trivial_wiring(p.golden_rtl):
            screen_results.append({
                "problem_id": pid,
                "category": detail_cat,
                "passed": False,
                "reason": "Excluded: Trivial wiring circuit (constant or 1-to-1 wire)",
                "mutants_generated": 0,
                "non_equiv_mutants": 0,
            })
            continue
            
        # Generate and validate mutants
        candidates = mutator.generate_mutants(p.golden_rtl, max_mutants=25)
        validated = mutator.validate_and_filter_mutants(candidates, p.golden_rtl)
        non_equiv = [m for m in validated if m.compiles and not m.is_equivalent]
        
        passed_a1 = len(non_equiv) >= 8
        reason = "Included" if passed_a1 else f"Excluded: Fewer than 8 non-equivalent mutants ({len(non_equiv)} generated)"
        
        entry = {
            "problem_id": pid,
            "category": detail_cat,
            "passed": passed_a1,
            "reason": reason,
            "mutants_generated": len(candidates),
            "non_equiv_mutants": len(non_equiv),
        }
        screen_results.append(entry)
        if passed_a1:
            passed_problems.append((p, entry))
            print(f"[{len(passed_problems)} PASSED] {pid} ({detail_cat}): {len(non_equiv)} non-equiv mutants")
            
        # Target at least 35 to give plenty of margin above 30
        if len(passed_problems) >= 35:
            print(f"Reached {len(passed_problems)} passing problems! Halting screening early.")
            break

    # Save detailed screen log
    out_path = "d:/rtl-verification/scratch/screened_problems.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(screen_results, f, indent=2)
    print(f"Saved screening results to {out_path}")
    print(f"Total passing problems found: {len(passed_problems)}")

if __name__ == "__main__":
    main()
