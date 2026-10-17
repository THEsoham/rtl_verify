import sys, os, time
sys.path.insert(0, r'd:\rtl-verification')
import core

print("1. Loading ALU spec...", flush=True)
spec = core.load_benchmark('alu_8bit')

print("2. Generating ALU RTL...", flush=True)
b_designer = core.OllamaBackend(model_name='qwen2.5-coder-verilog')
designer = core.DesignerAgent(backend=b_designer)
rtl = designer.generate_initial_rtl(spec)
with open(r'd:\rtl-verification\rtl_alu_candidate.v', 'w', encoding='utf-8') as f:
    f.write(rtl)
print(f"RTL saved to rtl_alu_candidate.v ({len(rtl.splitlines())} lines)", flush=True)


print("3. Validating unmutated RTL...", flush=True)
sim = core.HDLSimulator()
ok, errs = sim.validate_verilog(rtl, module_name='alu_8bit')
print(f"Valid: {ok}, errs: {errs}", flush=True)

print("4. Generating mutants...", flush=True)
mutator = core.RTLMutator(simulator=sim)
mutants = mutator.generate_benchmark_mutants('alu_8bit', rtl)
valid_count = sum(1 for m in mutants if m.is_valid_compile)
print(f"Valid mutants: {valid_count}/{len(mutants)}", flush=True)
for m in mutants:
    print(f"  {m.mutant_id}: line={m.line_number} valid={m.is_valid_compile} err={m.compile_error}", flush=True)
