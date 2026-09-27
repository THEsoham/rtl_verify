import json, sys
sys.stdout.reconfigure(encoding='utf-8')

nb = json.load(open('d:/rtl-verification/rtl_verification.ipynb', 'r', encoding='utf-8'))
cells = nb['cells']
print(f"Total cells: {len(cells)}")
for i, c in enumerate(cells):
    ct = c['cell_type']
    src = ''.join(c['source'])
    first_line = src.split('\n')[0][:100] if src.strip() else '(empty)'
    has_output = bool(c.get('outputs'))
    print(f"Cell {i:2d} [{ct:8s}] out={str(has_output):5s} | {first_line}")
