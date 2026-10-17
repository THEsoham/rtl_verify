import os
import subprocess
import json
import re

iverilog_path = "d:/rtl-verification/tools/iverilog/app/bin/iverilog.exe"
vvp_path = "d:/rtl-verification/tools/iverilog/app/bin/vvp.exe"

with open("v2/golden/verilogeval_all.json", "r", encoding="utf-8") as f:
    probs = json.load(f)

print(f"Verifying {len(probs)} golden designs against official VerilogEval testbenches...")

os.makedirs("scratch/golden_verify", exist_ok=True)
passed_problems = []
failed_problems = []

for p in probs:
    pid = p["problem_id"]
    golden_ref = p["golden_rtl"]
    golden_top = golden_ref.replace("RefModule", "TopModule")
    tb_code = p["golden_tb"]
    
    top_file = f"scratch/golden_verify/{pid}_top.v"
    ref_file = f"scratch/golden_verify/{pid}_ref.v"
    tb_file = f"scratch/golden_verify/{pid}_tb.v"
    vvp_file = f"scratch/golden_verify/{pid}.vvp"
    
    with open(top_file, "w", encoding="utf-8") as f:
        f.write(golden_top)
    with open(ref_file, "w", encoding="utf-8") as f:
        f.write(golden_ref)
    with open(tb_file, "w", encoding="utf-8") as f:
        f.write(tb_code)
        
    comp = subprocess.run([iverilog_path, "-g2012", "-o", vvp_file, tb_file, top_file, ref_file], capture_output=True, text=True)
    if comp.returncode != 0:
        failed_problems.append((pid, "Compile error", comp.stderr.strip()[:100]))
        continue
        
    try:
        sim = subprocess.run([vvp_path, vvp_file], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        failed_problems.append((pid, "Timeout", "Simulation exceeded 10s"))
        continue
        
    stdout = sim.stdout
    # In VerilogEval, output prints "Mismatches: X in Y samples"
    m = re.search(r"mismatches:\s*(\d+)", stdout, re.IGNORECASE)
    if m:
        mismatches = int(m.group(1))
        if mismatches == 0 and sim.returncode == 0:
            passed_problems.append(pid)
        else:
            failed_problems.append((pid, f"Mismatches: {mismatches}", stdout[:100]))
    else:
        # If no explicit Mismatches line, check returncode and error words
        if sim.returncode == 0 and "FAIL" not in stdout and "ERROR" not in stdout:
            passed_problems.append(pid)
        else:
            failed_problems.append((pid, "Simulation failure or non-zero exit", stdout[:100]))

print(f"\nGolden Verification Complete: {len(passed_problems)} PASSED, {len(failed_problems)} FAILED.")
if failed_problems:
    print(f"Failed Golden Problems ({len(failed_problems)}):")
    for pid, reason, out in failed_problems[:15]:
        print(f"  - {pid}: {reason} ({out.strip()})")

with open("scratch/golden_verification_results.json", "w", encoding="utf-8") as f:
    json.dump({"passed": passed_problems, "failed": failed_problems}, f, indent=2)
