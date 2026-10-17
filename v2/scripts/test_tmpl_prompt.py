import sys, os
sys.path.insert(0, ".")
from v2.src.llm_client import LLMClient

client = LLMClient()
m_gpt = {'id': 'gpt-4o-mini', 'name': 'gpt-4o-mini', 'provider': 'openai', 'temperature': 0.2, 'max_tokens': 1024}
p = """You are an RTL verification engineer writing testbench stimulus for TopModule.
The framework supplies the module shell, clock, reset, and DUT instance.
You must provide ONLY procedural statements for an initial begin ... end block.

RULES:
1. Drive inputs: e.g. in = 8'b00000000; #10;
2. Check outputs: e.g. if (out !== 8'b00000000) begin $display("MISMATCH: cycle=%0d time=%0t signal=out expected=%h actual=%h", cycle_count, $time, 8'h0, out); errors = errors + 1; end
3. Do NOT declare modules or use 'assign'. Do NOT assign to output wires.
4. Output ONLY the procedural stimulus statements enclosed in ```verilog ... ``` block.

SPECIFICATION:
Given an 8-bit input vector [7:0], reverse its bit ordering.
"""
resp = client.generate(m_gpt, p, seed=999)
print("Generated stimulus:\n", resp.verilog_code)
