import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import re
from v2.src.verilog_sim import VerilogSimulator

with open('v2/final/data/incremental_trials.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        t = json.loads(line)
        if t.get('test_compiled') and not t.get('test_passed_golden_rtl'):
            tb = t['test_code']
            golden = t['designs_used']['golden_rtl'].replace('RefModule', 'TopModule')
            
            inst_tb = tb
            # Add cycle tracking
            if 'cycle_count' not in inst_tb:
                inst_tb = re.sub(r'(integer\s+errors\s*=\s*0\s*;)', r'\1\n    integer cycle_count = 0;', inst_tb)
                inst_tb = re.sub(r'(#\d+\s*;)', r'\1 cycle_count = cycle_count + 1;', inst_tb)
            
            # Inject standardized mismatch display before errors = errors + 1
            def repl(m):
                sig = m.group(1)
                exp = m.group(2)
                return f'if ({sig} !== {exp}) begin $display("MISMATCH: cycle=%0d time=%0t signal={sig} expected=%h actual=%h", cycle_count, $time, {exp}, {sig}); errors = errors + 1; end'
            
            inst_tb = re.sub(r'if\s*\(\s*(\w+)\s*!==\s*([^)]+)\)\s*(?:begin\s*)?errors\s*=\s*errors\s*\+\s*1\s*;?', repl, inst_tb)
            
            sim = VerilogSimulator()
            res = sim.compile_and_run(dut_code=golden, tb_code=inst_tb, enforce_contract=True)
            print("SIMULATOR STDOUT:")
            print(res.sim_stdout)
            break
