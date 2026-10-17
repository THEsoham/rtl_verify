"""
End-to-End Execution Script for Local LLM RTL Verification Notebook.
Executes all cells in rtl_verification_local_llms.ipynb sequentially on GPU.
Captures stdout and matplotlib plot outputs, updating the .ipynb file directly.
"""
import sys, os, time, json, io, base64, traceback
from pathlib import Path

# Ensure working directory and environment
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.chdir(r'd:\rtl-verification')
sys.path.insert(0, r'd:\rtl-verification')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

nb_path = Path(r'd:\rtl-verification\rtl_verification_local_llms.ipynb')
print(f"Loading notebook: {nb_path}...")
nb = json.loads(nb_path.read_text(encoding='utf-8'))

# 1. Update Cell 2 to use fine-tuned Qwen model
for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        src = "".join(cell.get('source', []))
        if 'b_qwen = core.OllamaBackend' in src:
            src_updated = src.replace('qwen2.5-coder:1.5b', 'qwen2.5-coder-verilog')
            cell['source'] = [l + '\n' for l in src_updated.splitlines()]
            if cell['source']:
                cell['source'][-1] = cell['source'][-1].rstrip('\n')
            print("Updated Cell 2 to use qwen2.5-coder-verilog for Designer.")
            break

# Shared execution namespace
ns = {"__name__": "__main__"}

exec_counter = 1
total_code_cells = sum(1 for c in nb['cells'] if c['cell_type'] == 'code')
print(f"Total code cells to execute: {total_code_cells}")

for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] != 'code':
        continue

    src = "".join(cell.get('source', []))
    print(f"\n{'='*70}", flush=True)
    print(f"EXECUTING CODE CELL {exec_counter}/{total_code_cells} (Notebook Cell {i})", flush=True)
    print(f"{'='*70}", flush=True)
    first_line = src.strip().splitlines()[0] if src.strip().splitlines() else ""
    print(f"Line 1: {first_line[:90]}...", flush=True)

    # Capture stdout
    old_stdout = sys.stdout
    captured_stdout = io.StringIO()
    sys.stdout = captured_stdout

    # Clear previous figures
    plt.close('all')

    cell_error = None
    t0 = time.time()
    try:
        compiled = compile(src, f"<cell_{i}>", "exec")
        exec(compiled, ns)
    except Exception as e:
        cell_error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout

    elapsed = time.time() - t0
    stdout_text = captured_stdout.getvalue()
    if stdout_text.strip():
        print(f"[Output ({elapsed:.1f}s)]:\n{stdout_text.rstrip()}", flush=True)
    else:
        print(f"[Completed in {elapsed:.1f}s with no text output]", flush=True)

    if cell_error:
        print(f"[ERROR in cell {exec_counter}]:\n{cell_error}", flush=True)
        # Record error in cell outputs
        cell['outputs'] = [{
            "ename": "Exception",
            "evalue": "Cell execution error",
            "output_type": "error",
            "traceback": cell_error.splitlines()
        }]
        cell['execution_count'] = exec_counter
        # Save notebook even on error
        nb_path.write_text(json.dumps(nb, indent=1), encoding='utf-8')
        sys.exit(1)

    # Process outputs
    outputs = []
    if stdout_text:
        outputs.append({
            "name": "stdout",
            "output_type": "stream",
            "text": [l + "\n" for l in stdout_text.splitlines()]
        })

    # Capture any matplotlib figures created
    fig_nums = plt.get_fignums()
    if fig_nums:
        for fnum in fig_nums:
            fig = plt.figure(fnum)
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight', dpi=150, facecolor=fig.get_facecolor(), edgecolor='none')
            buf.seek(0)
            img_b64 = base64.b64encode(buf.read()).decode('utf-8')
            outputs.append({
                "data": {
                    "image/png": img_b64,
                    "text/plain": [f"<Figure size {fig.get_size_inches()[0]*100:.0f}x{fig.get_size_inches()[1]*100:.0f} with {len(fig.axes)} Axes>"]
                },
                "metadata": {},
                "output_type": "display_data"
            })
            print(f"  Captured plot {fnum} as PNG ({len(img_b64)} b64 bytes)", flush=True)
        plt.close('all')

    cell['outputs'] = outputs
    cell['execution_count'] = exec_counter
    exec_counter += 1

    # Checkpoint save notebook after each cell
    nb_path.write_text(json.dumps(nb, indent=1), encoding='utf-8')

print(f"\n{'='*70}", flush=True)
print("ALL CODE CELLS EXECUTED SUCCESSFULLY AND NOTEBOOK SAVED!", flush=True)
print(f"{'='*70}", flush=True)
