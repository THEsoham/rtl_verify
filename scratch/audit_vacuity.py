import json
import sys
sys.path.insert(0, 'd:/rtl-verification')
from v2.src.verilog_sim import VerilogSimulator

sim = VerilogSimulator()

with open('v2/golden/verilogeval_all.json') as f:
    probs = {p['problem_id']: p for p in json.load(f)}

runs = [
    ('Run 1 Qwen', 'v2/results_old/pair1_local_qwen_gen_trials.json'),
    ('Run 2 Llama', 'v2/results_old/pair2_local_llama_gen_trials.json'),
    ('Run 3 GPT', 'v2/results_old/pair3_cloud_gpt_gen_trials.json'),
    ('Run 4 Gemini', 'v2/results_old/pair4_cloud_gemini_gen_trials.json'),
]

for run_name, run_file in runs:
    with open(run_file) as f:
        trials = json.load(f)
    valid_trials = [t for t in trials if t.get('test_passed_golden_rtl', False)]
    print(f"\n=== {run_name} (Previously marked 'valid' tests: {len(valid_trials)} / {len(trials)}) ===")
    vacuous_count = 0
    for t in valid_trials:
        pid = t['problem_id']
        cond = t['condition']
        tb = t['test_code']
        prob = probs.get(pid)
        if not prob:
            continue
        golden = prob['golden_rtl']
        # Build inverted output gate
        port_pat = r"(input|output)\s+(reg\s+|wire\s+)?(?:signed\s+)?(?:\[([^\]]+)\]\s+)?(\w+)"
        import re
        ports = []
        for m in re.finditer(port_pat, golden):
            ports.append({'dir': m.group(1), 'width': f"[{m.group(3)}]" if m.group(3) else "", 'name': m.group(4)})
        
        g_conns = []
        inverts = []
        for p in ports:
            if p['dir'] == 'input':
                g_conns.append(f".{p['name']}({p['name']})")
            else:
                g_conns.append(f".{p['name']}(g_{p['name']})")
                inverts.append(f"  wire {p['width']} g_{p['name']}; assign {p['name']} = ~g_{p['name']};")
        
        # Build inverted TopModule
        mod_decl = re.search(r'\bmodule\s+\w+\s*\([^;]*\);', golden, re.DOTALL)
        if not mod_decl:
            continue
        hdr = mod_decl.group(0).replace('RefModule', 'TopModule')
        inv_code = f"{hdr}\n" + "\n".join(inverts) + f"\n  GoldenRef golden_inst ({', '.join(g_conns)});\nendmodule\n" + golden.replace('RefModule', 'GoldenRef')
        
        res = sim.compile_and_run(dut_code=inv_code, tb_code=tb, enforce_contract=True)
        if res.passed:
            vacuous_count += 1
            print(f"  [VACUOUS] Problem: {pid:25} | Cond: {cond:7} | TB passed on inverted design!")
        else:
            print(f"  [OK-FAIL] Problem: {pid:25} | Cond: {cond:7} | TB caught inverted design as expected.")
    print(f"Summary {run_name}: {vacuous_count} out of {len(valid_trials)} previously 'valid' tests were VACUOUS ({vacuous_count/max(1, len(valid_trials))*100:.1f}%)")
