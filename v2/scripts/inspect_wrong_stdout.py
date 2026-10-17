import json

with open('v2/final/data/incremental_trials.jsonl', 'r', encoding='utf-8') as f:
    wrong_samples = []
    for line in f:
        t = json.loads(line)
        if t.get('test_compiled') and not t.get('test_passed_golden_rtl'):
            wrong_samples.append(t)
            if len(wrong_samples) >= 8:
                break

for idx, s in enumerate(wrong_samples):
    print(f"=== Sample {idx+1}: {s['problem_id']} (cond {s['condition']}, gen {s['generator_id']}, tester {s['tester_id']}) ===")
    stdout = s.get('golden_sim_stdout', '')
    print("STDOUT:")
    print(stdout if stdout else "[EMPTY STDOUT]")
    print("-" * 50)
