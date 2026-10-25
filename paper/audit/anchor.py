"""Run every free-form testbench against the candidate RTL it was written for."""
import sys, os
from concurrent.futures import ProcessPoolExecutor
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resim import run_icarus

def work(a):
    i, dut, tb = a
    if not dut.strip():
        return i, "no_design"
    return i, run_icarus(dut, tb)[0]

if __name__ == "__main__":
    df = pd.read_csv(sys.argv[1], keep_default_na=False)
    f = df[df.arm == "freeform"]
    with ProcessPoolExecutor(4) as ex:
        res = dict(ex.map(work, [(i, r.design_code, r.test_code) for i, r in f.iterrows()], chunksize=8))
    f = f.assign(tb_on_candidate=pd.Series(res))
    f[["problem_id", "condition", "generator_id", "tester_id", "seed", "design_passed_golden_tb", "test_compiled",
       "test_contract_valid", "test_vacuous", "test_passed_golden_rtl", "false_rejection", "tb_on_candidate"]].to_csv(sys.argv[2])
