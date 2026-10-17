import sys
import time
sys.path.insert(0, 'd:/rtl-verification')
import core

benchmark_keys = ['fifo_sync', 'traffic_light', 'alu_8bit']
print("Loading FineTunedQwenBackend...", flush=True)
backend = core.FineTunedQwenBackend()
designer = core.DesignerAgent(backend=backend)
simulator = core.HDLSimulator()

print("=== EVALUATING FINE-TUNED DESIGNER ===", flush=True)
for b_key in benchmark_keys:
    spec = core.load_benchmark(b_key)
    print(f"\n[Synthesizing] {b_key}...", flush=True)
    t0 = time.time()
    code = designer.generate_initial_rtl(spec)
    dt = time.time() - t0
    is_valid, errors = simulator.validate_verilog(code, module_name=spec['name'])
    has_end = 'endmodule' in code
    print(f"Done in {dt:.1f}s | Lines: {len(code.splitlines())} | Has endmodule: {has_end} | Valid: {is_valid}", flush=True)
    if not is_valid:
        print("Lint errors/warnings:", errors[:3], flush=True)
    else:
        print("-> Clean Verilator compiler pass!", flush=True)

print("\nAll benchmarks processed successfully!", flush=True)
