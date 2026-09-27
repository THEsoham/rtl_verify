import json

nb = json.load(open('d:/rtl-verification/rtl_verification.ipynb', 'r', encoding='utf-8'))
cells = nb['cells']

# Show source of cells 2, 6, 22, 24, and 25 (the key code + final findings cells)
for idx in [2, 22, 24, 25]:
    c = cells[idx]
    src = ''.join(c['source'])
    print(f"\n{'='*80}")
    print(f"CELL {idx} ({c['cell_type']})")
    print(f"{'='*80}")
    # Only print first 80 lines
    lines = src.split('\n')
    for ln in lines[:80]:
        print(ln)
    if len(lines) > 80:
        print(f"... ({len(lines) - 80} more lines)")
