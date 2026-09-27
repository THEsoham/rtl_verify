"""Execute the notebook cell-by-cell with progress tracking and error reporting."""
import json
import sys
import os
import time
import traceback

sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is on path
project_root = 'd:/rtl-verification'
os.chdir(project_root)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Read notebook
with open('rtl_verification.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

cells = nb['cells']
code_cells = [(i, c) for i, c in enumerate(cells) if c['cell_type'] == 'code']

print(f"Executing {len(code_cells)} code cells out of {len(cells)} total cells")
print("=" * 70)

# Provide a 'display' fallback for non-Jupyter execution
def _display(obj):
    if hasattr(obj, 'to_string'):
        print(obj.to_string())
    else:
        print(obj)

# Create a shared namespace for execution
namespace = {
    "__name__": "__main__",
    "display": _display,
}

failed_cells = []
for cell_idx, (global_idx, cell) in enumerate(code_cells):
    src = ''.join(cell['source'])
    first_line = src.strip().split('\n')[0][:80]
    print(f"\n[{cell_idx+1}/{len(code_cells)}] Cell {global_idx}: {first_line}")

    t0 = time.time()
    try:
        exec(compile(src, f"<cell_{global_idx}>", "exec"), namespace)
        dt = time.time() - t0
        print(f"  OK ({dt:.1f}s)")
    except Exception as e:
        dt = time.time() - t0
        print(f"  FAILED after {dt:.1f}s: {type(e).__name__}: {e}")
        tb = traceback.format_exc()
        # Print only the last 5 lines of traceback to keep it compact
        for line in tb.strip().split('\n')[-3:]:
            print(f"    {line}")
        failed_cells.append((global_idx, str(e)))
        continue

print("\n" + "=" * 70)
if failed_cells:
    print(f"FAILURES: {len(failed_cells)} cell(s) failed:")
    for idx, err in failed_cells:
        print(f"  Cell {idx}: {err[:100]}")
else:
    print("ALL CELLS PASSED")
