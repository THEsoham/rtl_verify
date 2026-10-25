"""Independent re-simulation of every free-form testbench.

For each trial: compile test_code with the golden RTL (RefModule -> TopModule) under
Icarus Verilog, apply the same contract parser as the original pipeline, and, if it
passes, run it against the inverted-output gate. Optionally repeat with Verilator --timing.
Outputs a CSV comparing re-simulated outcomes with the archived flags.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

if __name__ == "__main__":
    CSV, GOLDEN_DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
    SIMS = sys.argv[4].split(",") if len(sys.argv) > 4 else ["icarus"]
TIMEOUT = 30


def parse_contract(stdout, rc):
    finish = "$finish" in stdout.lower()
    if rc != 0 or not finish:
        return "contract_violation"
    p = len(re.findall(r"\*\*\*\s*TEST RESULT:\s*PASS\s*\*\*\*", stdout, re.I))
    f = len(re.findall(r"\*\*\*\s*TEST RESULT:\s*FAIL\s*\*\*\*", stdout, re.I))
    if p == 1 and f == 0:
        return "pass"
    if f >= 1 and p == 0:
        return "fail"
    return "contract_violation"


def run_icarus(dut, tb):
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/dut.v", "w").write(dut)
        open(f"{d}/tb.v", "w").write(tb)
        try:
            c = subprocess.run(["iverilog", "-g2012", "-o", f"{d}/sim.vvp", f"{d}/tb.v", f"{d}/dut.v"],
                               capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return "compile_fail", ""
        if c.returncode != 0:
            return "compile_fail", c.stderr[-500:]
        try:
            r = subprocess.run(["vvp", "-n", f"{d}/sim.vvp"], capture_output=True, text=True, timeout=TIMEOUT, cwd=d)
        except subprocess.TimeoutExpired:
            return "contract_violation", "timeout"
        # Icarus prints "$finish called" on stdout; -n makes $stop behave like $finish
        return parse_contract(r.stdout, r.returncode), r.stdout[-2000:]


def run_verilator(dut, tb):
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/dut.v", "w").write(dut)
        open(f"{d}/tb.v", "w").write(tb)
        cmd = ["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style", "--top-module", "tb",
               "-j", "1", "--Mdir", f"{d}/obj", f"{d}/tb.v", f"{d}/dut.v", "-o", "simv"]
        try:
            c = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return "compile_fail", "build timeout"
        if c.returncode != 0:
            return "compile_fail", c.stderr[-500:]
        try:
            r = subprocess.run([f"{d}/obj/simv"], capture_output=True, text=True, timeout=TIMEOUT, cwd=d)
        except subprocess.TimeoutExpired:
            return "contract_violation", "timeout"
        out = r.stdout + ("\n$finish" if "- tb.v" in r.stdout or "$finish" in r.stderr or r.returncode == 0 else "")
        return parse_contract(out, r.returncode), r.stdout[-2000:]


def inverted_gate(golden):
    m = re.search(r"\bmodule\s+(\w+)\s*(?:#\s*\([^)]*\)\s*)?\((.*?)\);", golden, re.DOTALL)
    name, header = m.group(1), m.group(2)
    pat = re.compile(r"(input|output|inout)\s+(?:reg\s+|wire\s+|logic\s+)?(?:signed\s+)?(?:\[([^\]]+)\]\s+)?(\w+)")
    ports = []
    for item in re.split(r",(?![^\[]*\])", header):
        pm = pat.match(item.strip())
        if pm:
            ports.append((pm.group(1), f"[{pm.group(2)}]" if pm.group(2) else "", pm.group(3)))
    lines = ["module TopModule (", ",\n".join(f"  {a} {w} {n}" for a, w, n in ports), ");"]
    conns = []
    for a, w, n in ports:
        if a == "input":
            conns.append(f".{n}({n})")
        else:
            lines += [f"  wire {w} g_{n};", f"  assign {n} = ~g_{n};"]
            conns.append(f".{n}(g_{n})")
    lines += [f"  GoldenRef ref_inst ({', '.join(conns)});", "endmodule"]
    return "\n".join(lines) + "\n" + re.sub(r"\bmodule\s+" + name, "module GoldenRef", golden, count=1)


def work(args):
    idx, pid, tb = args
    golden = open(os.path.join(GOLDEN_DIR, pid, "ref.v")).read()
    gdut = golden.replace("RefModule", "TopModule")
    res = {"idx": idx}
    for sim in SIMS:
        fn = run_icarus if sim == "icarus" else run_verilator
        st, out = fn(gdut, tb)
        res[f"{sim}_golden"] = st
        res[f"{sim}_stdout"] = out[-300:]
        if st == "pass":
            res[f"{sim}_inverted"] = fn(inverted_gate(golden), tb)[0]
    return res


if __name__ == "__main__":
    df = pd.read_csv(CSV, keep_default_na=False)
    f = df[df.arm == "freeform"]
    jobs = [(i, r.problem_id, r.test_code) for i, r in f.iterrows()]
    with ProcessPoolExecutor(max_workers=int(os.environ.get("J", "4"))) as ex:
        rows = list(ex.map(work, jobs, chunksize=4))
    pd.DataFrame(rows).set_index("idx").join(f[["problem_id", "condition", "tester_id", "test_compiled",
                                                 "test_contract_valid", "test_passed_golden_rtl", "test_vacuous",
                                                 "false_rejection"]]).to_csv(OUT)
    print("done", len(rows))
