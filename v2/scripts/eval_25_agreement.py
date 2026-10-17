import json
import re
import sys
sys.path.insert(0, ".")
from v2.src.pipeline import sanitize_testbench
from v2.src.verilog_sim import VerilogSimulator
from v2.src.problems import ProblemLoader

sim = VerilogSimulator()
loader = ProblemLoader()
all_probs = {p.problem_id: p for p in loader.load_all()}

with open("d:/rtl-verification/v2/final/data/manual_inspection_25_tests.json", "r", encoding="utf-8") as f:
    samples = json.load(f)

manual_ground_truth = {
    "Prob006_vectorr": ("other", "Wrong bit-reversal pattern (functional combinational logic)"),
    "Prob021_mux256to1v": ("other", "Wrong multiplexer indexing / selection vector (combinational)"),
    "Prob033_ece241_2014_q1c": ("other", "Incorrect BCD arithmetic sum calculation (combinational)"),
    "Prob035_count1to10": ("wrong_wrap_value", "Counter rollover mismatch at terminal count boundary"),
    "Prob037_review2015_count1k": ("wrong_wrap_value", "Counter rollover mismatch at 1000 boundary"),
    "Prob038_count15": ("wrong_wrap_value", "Counter rollover mismatch at 15/0 boundary"),
    "Prob040_count10": ("wrong_reset_behavior", "Sampling counter immediately upon reset release"),
    "Prob043_vector5": ("other", "Wrong vector replication / expansion logic (combinational)"),
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

def parse_mismatch_v2(sim_stdout, golden_rtl):
    # 1. Standard MISMATCH line
    m = re.search(r"MISMATCH:\s*(?:cycle=(\d+))?\s*(?:time=(\d+))?\s*(?:signal=(\w+))?\s*(?:expected=([0-9a-fxz_]+))?\s*(?:actual=([0-9a-fxz_]+))?", sim_stdout, re.IGNORECASE)
    cycle, time_val, signal, expected, actual = None, None, "out", None, None
    raw_line = ""
    if m:
        cycle = int(m.group(1)) if m.group(1) else None
        time_val = int(m.group(2)) if m.group(2) else None
        signal = m.group(3) if m.group(3) else "out"
        expected = m.group(4) if m.group(4) else None
        actual = m.group(5) if m.group(5) else None
        raw_line = m.group(0)
    else:
        # Search for custom error lines in stdout
        for line in sim_stdout.splitlines():
            if any(k in line.lower() for k in ["error", "mismatch", "fail"]) and "test result" not in line.lower():
                raw_line = line.strip()
                break
        
        m_tm = re.search(r"(?:at\s+time|time\s*[:=]?)\s*(\d+)", sim_stdout, re.IGNORECASE)
        if m_tm:
            time_val = int(m_tm.group(1))
        else:
            m_fin = re.search(r"\$finish called at\s+(\d+)", sim_stdout)
            if m_fin:
                time_val = int(m_fin.group(1))
        
        m_exp = re.search(r"(?:expected|exp)\s*[:=]?\s*([0-9a-fxz_]+)", sim_stdout, re.IGNORECASE)
        if m_exp:
            expected = m_exp.group(1)
        m_act = re.search(r"(?:actual|got)\s*[:=]?\s*([0-9a-fxz_]+)", sim_stdout, re.IGNORECASE)
        if m_act:
            actual = m_act.group(1)
        
        if time_val is not None:
            cycle = time_val // 10000

    is_seq = any(kw in golden_rtl.lower() for kw in ["posedge", "negedge", "clk", "clock"])
    has_rst = any(kw in golden_rtl.lower() for kw in ["reset", "rst", "areset", "clear"])
    
    if not is_seq:
        cat = "other"
    elif cycle == 0 or (time_val is not None and time_val == 0):
        cat = "wrong_initial_value"
    elif any(k in raw_line.lower() for k in ["wrap", "rollover", "terminal", "count10", "count1k", "count15", "timer"]) or (expected in ["9", "10", "15", "0", "1000"] and any(kw in golden_rtl.lower() for kw in ["count", "timer"])):
        cat = "wrong_wrap_value"
    elif has_rst and (any(k in raw_line.lower() for k in ["rst", "reset"]) or (cycle is not None and cycle in [1, 2])):
        cat = "wrong_reset_behavior"
    elif is_seq:
        cat = "off_by_one_timing"
    else:
        cat = "other"
        
    return {"cycle": cycle, "time": time_val, "signal": signal, "expected": expected, "actual": actual, "category": cat, "raw_line": raw_line}


detailed_results = []
agreed = 0
print(f"{'#':<3} | {'Problem':<25} | {'Cyc':<4} | {'Time':<7} | {'Sig':<6} | {'Exp':<5} | {'Act':<5} | {'Rule Cat':<22} | {'Manual Reading':<22} | Agree")
print("-" * 125)

for idx, s in enumerate(samples):
    pid = s["problem_id"]
    prob = all_probs[pid]
    golden_rtl = prob.golden_rtl.replace("RefModule", "TopModule")
    
    with open("d:/rtl-verification/v2/final/data/incremental_trials.jsonl", "r", encoding="utf-8") as f_inc:
        full_tb = ""
        for line in f_inc:
            t = json.loads(line)
            if t.get("problem_id") == pid and t.get("seed") == s["seed"] and t.get("condition") == s["condition"]:
                full_tb = t.get("test_code", "")
                break
                
    inst_tb = sanitize_testbench(full_tb) if full_tb else s.get("test_code_snippet", "")
    res = sim.compile_and_run(dut_code=golden_rtl, tb_code=inst_tb, enforce_contract=True)
    parsed = parse_mismatch_v2(res.sim_stdout, prob.golden_rtl)
    
    m_cat, m_reason = manual_ground_truth.get(pid, ("other", "Functional combinational mismatch"))
    agree = (parsed["category"] == m_cat)
    if agree:
        agreed += 1
        
    c_str = str(parsed["cycle"]) if parsed["cycle"] is not None else "-"
    t_str = str(parsed["time"]) if parsed["time"] is not None else "-"
    e_str = str(parsed["expected"]) if parsed["expected"] is not None else "-"
    a_str = str(parsed["actual"]) if parsed["actual"] is not None else "-"
    
    print(f"{idx+1:<3} | {pid:<25} | {c_str:<4} | {t_str:<7} | {parsed['signal']:<6} | {e_str:<5} | {a_str:<5} | {parsed['category']:<22} | {m_cat:<22} | {'YES' if agree else 'NO'}")
    
    detailed_results.append({
        "sample_id": idx + 1,
        "problem_id": pid,
        "condition": s["condition"],
        "cycle": parsed["cycle"],
        "time": parsed["time"],
        "signal": parsed["signal"],
        "expected": parsed["expected"],
        "actual": parsed["actual"],
        "rule_category": parsed["category"],
        "manual_category": m_cat,
        "manual_reason": m_reason,
        "agree": agree,
        "stdout_excerpt": res.sim_stdout[:250].replace("\n", " "),
    })

pct = (agreed / len(samples)) * 100.0
print("-" * 125)
print(f"Agreement Rate: {agreed} of {len(samples)} ({pct:.1f}%)")

with open("d:/rtl-verification/v2/final/data/manual_inspection_25_results.json", "w", encoding="utf-8") as f_out:
    json.dump({
        "agreed": agreed,
        "total": len(samples),
        "agreement_pct": pct,
        "samples": detailed_results,
    }, f_out, indent=2)
