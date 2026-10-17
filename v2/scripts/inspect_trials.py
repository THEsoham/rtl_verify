import json
from collections import Counter

problems = set()
models = Counter()
conditions = Counter()
arms = Counter()
null_versions = []
prob_gen_counts = Counter()

with open('v2/final/data/incremental_trials.jsonl', 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if not line.strip():
            continue
        t = json.loads(line)
        prob = t.get('problem_id')
        problems.add(prob)
        gen = t.get('generator_id')
        test = t.get('tester_id')
        pair = f"{gen} -> {test}"
        models[pair] += 1
        cond = t.get('condition')
        conditions[cond] += 1
        arm = t.get('arm')
        arms[arm] += 1
        prob_gen_counts[(prob, gen)] += 1
        
        gv = t.get('generator_model_version')
        tv = t.get('tester_model_version')
        if not gv or not tv or gv == "null" or tv == "null":
            null_versions.append({
                'idx': idx,
                'problem_id': prob,
                'seed': t.get('seed'),
                'condition': cond,
                'gen': gen,
                'gv': gv,
                'tv': tv
            })

print(f"Total trials: {sum(models.values())}")
print(f"Unique problems ({len(problems)}): {sorted(list(problems))}")
print(f"Model pairs count: {dict(models)}")
print(f"Conditions count: {dict(conditions)}")
print(f"Arms count: {dict(arms)}")
print(f"Null versions count: {len(null_versions)}")
from collections import defaultdict
null_by_prob_seed = defaultdict(int)
for nv in null_versions:
    null_by_prob_seed[(nv['problem_id'], nv['seed'], nv['gen'])] += 1
print(f"Null versions by (problem, seed, gen): {dict(null_by_prob_seed)}")

# Check per generator how many problems and trials
gen_prob_count = defaultdict(set)
for (p, g), cnt in prob_gen_counts.items():
    gen_prob_count[g].add(p)
for g, p_set in gen_prob_count.items():
    print(f"Generator {g}: {len(p_set)} problems")
