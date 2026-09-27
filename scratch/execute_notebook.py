"""
Script to execute rtl_verification.ipynb cell by cell, capturing outputs and saving in place.
"""

import sys
import time
import nbformat
from nbclient import NotebookClient

nb_path = "rtl_verification.ipynb"
print(f"Reading notebook {nb_path}...")
nb = nbformat.read(nb_path, as_version=4)

client = NotebookClient(nb, timeout=600, kernel_name="python3")

print(f"Starting execution of {len(nb.cells)} cells...")
t0 = time.time()
with client.setup_kernel():
    for idx, cell in enumerate(nb.cells):
        if cell.cell_type == "code":
            first_line = cell.source.splitlines()[0] if cell.source.splitlines() else ""
            print(f"  [{idx+1}/{len(nb.cells)}] Executing code cell: {first_line[:50]}...")
            t_cell = time.time()
            try:
                client.execute_cell(cell, idx)
                print(f"       -> Done in {time.time() - t_cell:.2f}s")
            except Exception as e:
                print(f"ERROR in cell {idx+1}: {e}")
                sys.exit(1)
        else:
            print(f"  [{idx+1}/{len(nb.cells)}] Skipping markdown cell")

elapsed = time.time() - t0
print(f"All cells executed successfully in {elapsed:.1f} seconds!")

print(f"Writing executed notebook back to {nb_path}...")
nbformat.write(nb, nb_path)
print("Notebook updated successfully with all cell outputs!")
