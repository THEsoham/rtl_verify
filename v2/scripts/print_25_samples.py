import json

with open("d:/rtl-verification/v2/final/data/manual_inspection_25_tests.json", "r", encoding="utf-8") as f:
    samples = json.load(f)

print(f"{'#':<3} | {'Problem':<25} | {'Cond':<5} | {'Cycle':<5} | {'Sig':<6} | {'Exp':<5} | {'Act':<5} | {'Rule Cat':<22}")
print("-" * 85)
for s in samples:
    print(f"{s['sample_id']:<3} | {s['problem_id']:<25} | {s['condition']:<5} | {str(s['cycle']):<5} | {str(s['signal']):<6} | {str(s['expected']):<5} | {str(s['actual']):<5} | {s['rule_category']:<22}")
