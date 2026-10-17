import json
import sys
sys.path.insert(0, 'd:/rtl-verification')
from scratch.test_mut import generate_mutants, build_diff_tb
from v2.src.verilog_sim import VerilogSimulator

sim = VerilogSimulator()

with open('v2/golden/verilogeval_all.json') as f:
    probs = json.load(f)

seq_probs = [p for p in probs if p['category'] == 'sequential']

print(f"Testing {len(seq_probs)} sequential problems for mutator yield (target: >= 8 non-equivalent mutants)...")

results = []
for p in seq_probs:
    pid = p['problem_id']
    code = p['golden_rtl'].replace('RefModule', 'TopModule')
    # Filter out trivial modules with <= 1 line of logic
    candidates = generate_mutants(code)
    if len(candidates) < 8:
        results.append((pid, len(candidates), 0, "Too few candidates generated (<8)"))
        continue
    
    non_equiv_count = 0
    for m in candidates:
        tb, g_mod, m_mod = build_diff_tb(code, m.mutated_code, num_vectors=1500)
        res = sim.compile_and_run(dut_code=m_mod, tb_code=tb, ref_code=g_mod)
        lines = [l.strip() for l in res.sim_stdout.splitlines()]
        if res.compile_ok and "EQUIV_RESULT: DIFFERENT" in lines:
            non_equiv_count += 1
            if non_equiv_count >= 8:
                break # Reached threshold
    
    status = "USABLE (>=8)" if non_equiv_count >= 8 else f"UNUSABLE ({non_equiv_count} non-equiv)"
    results.append((pid, len(candidates), non_equiv_count, status))
    print(f"  {pid:30} | Cand: {len(candidates):2} | Non-equiv: {non_equiv_count:2} | Status: {status}")
    if len([r for r in results if "USABLE" in r[3]]) >= 15:
        break # Found enough usable sequential problems
