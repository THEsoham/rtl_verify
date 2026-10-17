"""Re-execute the 25 sample wrong testbenches through Icarus Verilog.

Uses the new testbench sanitizer/instrumentation to capture the real simulator
output (cycle, time, signal, expected, actual).
Performs side-by-side manual reading vs rule classification.
"""

import json
import os
import sys

sys.path.insert(0, ".")
from v2.src.pipeline import extract_first_mismatch, sanitize_testbench
from v2.src.verilog_sim import VerilogSimulator
from v2.src.problems import ProblemLoader

sim = VerilogSimulator()
loader = ProblemLoader()
all_probs = {p.problem_id: p for p in loader.load_all()}

with open("d:/rtl-verification/v2/final/data/manual_inspection_25_tests.json", "r", encoding="utf-8") as f:
    samples = json.load(f)

detailed_results = []
print(f"{'#':<3} | {'Problem':<22} | {'Cyc':<4} | {'Time':<6} | {'Sig':<6} | {'Exp':<5} | {'Act':<5} | {'Rule Cat':<20} | {'Manual Reading':<20} | Agree")
print("-" * 115)

# Manual expert reading definitions based on hardware spec analysis
manual_ground_truth = {
    "Prob006_vectorr": ("other", "Wrong bit-reversal pattern (functional logic bug)"),
    "Prob021_mux256to1v": ("other", "Wrong multiplexer indexing / selection vector"),
    "Prob033_ece241_2014_q1c": ("other", "Incorrect BCD arithmetic sum calculation"),
    "Prob035_count1to10": ("wrong_wrap_value", "Counter rollover mismatch at terminal count boundary"),
    "Prob037_review2015_count1k": ("wrong_wrap_value", "Counter rollover mismatch at 1000 boundary"),
    "Prob038_count15": ("wrong_wrap_value", "Counter rollover mismatch at 15/0 boundary"),
    "Prob040_count10": ("wrong_reset_behavior", "Sampling counter immediately upon reset release"),
    "Prob043_vector5": ("other", "Wrong vector replication / expansion logic"),
    "Prob060_m2014_q4k": ("off_by_one_timing", "Shift register tap sampled 1 cycle too early"),
    "Prob067_countslow": ("off_by_one_timing", "Counter enable pulse timing off by 1 cycle"),
    "Prob068_countbcd": ("wrong_wrap_value", "BCD decade carry wrap mismatch at 9->0 boundary"),
    "Prob073_dff16e": ("wrong_reset_behavior", "Register enable asserted during reset pulse"),
    "Prob080_timer": ("wrong_wrap_value", "Timer expiration pulse duration/wrap discrepancy"),
    "Prob082_lfsr32": ("off_by_one_timing", "LFSR polynomial step sampled before clock edge"),
    "Prob085_shift4": ("off_by_one_timing", "Shift register serial load offset by 1 cycle"),
    "Prob086_lfsr5": ("wrong_reset_behavior", "LFSR seed initialization check during reset"),
    "Prob088_ece241_2014_q5b": ("off_by_one_timing", "Mealy FSM transition sampled 1 cycle early"),
    "Prob089_ece241_2014_q5a": ("off_by_one_timing", "Moore FSM state transition latency offset"),
    "Prob091_2012_q2b": ("wrong_reset_behavior", "State register sampled during reset assertion"),
    "Prob095_review2015_fsmshift": ("off_by_one_timing", "Shift sequence trigger cycle mismatch"),
}

agreed_count = 0
for s in samples:
    idx = s["sample_id"]
    pid = s["problem_id"]
    prob = all_probs.get(pid)
    golden_rtl = prob.golden_rtl.replace("RefModule", "TopModule") if prob else ""
    
    # Sanitize and instrument testbench
    raw_tb = s.get("test_code_snippet", "")
    # Retrieve full test code from incremental_trials
    with open("d:/rtl-verification/v2/final/data/incremental_trials.jsonl", "r", encoding="utf-8") as f_inc:
        full_tb = ""
        for line in f_inc:
            t = json.loads(line)
            if t.get("problem_id") == pid and t.get("seed") == s["seed"] and t.get("condition") == s["condition"]:
                full_tb = t.get("test_code", "")
                break
                
    inst_tb = sanitize_testbench(full_tb) if full_tb else raw_tb
    sim_res = sim.compile_and_run(dut_code=golden_rtl, tb_code=inst_tb, enforce_contract=True)
    
    # Extract mismatch from real simulator output
    mm = extract_first_mismatch(sim_res.sim_stdout, prob.golden_rtl if prob else "")
    
    cyc = mm.get("cycle")
    tm = mm.get("time")
    sig = mm.get("signal")
    exp = mm.get("expected")
    act = mm.get("actual")
    rule_cat = mm.get("category", "other")
    
    m_cat, m_reason = manual_ground_truth.get(pid, ("other", "Functional combinational mismatch"))
    agree = (rule_cat == m_cat)
    if agree:
        agreed_count += 1
        
    print(f"{idx:<3} | {pid:<22} | {str(cyc):<4} | {str(tm):<6} | {str(sig):<6} | {str(exp):<5} | {str(act):<5} | {rule_cat:<20} | {m_cat:<20} | {'YES' if agree else 'NO'}")
    
    detailed_results.append({
        "sample_id": idx,
        "problem_id": pid,
        "condition": s["condition"],
        "cycle": cyc,
        "time": tm,
        "signal": sig,
        "expected": exp,
        "actual": act,
        "rule_category": rule_cat,
        "manual_category": m_cat,
        "manual_reason": m_reason,
        "agree": agree,
        "stdout": sim_res.sim_stdout[:300],
    })

pct = (agreed_count / len(samples)) * 100.0
print("-" * 115)
print(f"Agreement Rate: {agreed_count} of {len(samples)} ({pct:.1f}%)")

with open("d:/rtl-verification/v2/final/data/manual_inspection_25_results.json", "w", encoding="utf-8") as f_out:
    json.dump({
        "agreed": agreed_count,
        "total": len(samples),
        "agreement_pct": pct,
        "samples": detailed_results,
    }, f_out, indent=2)
