"""Reproduces every number in paper/main.tex from v2/final/data/final_trials.csv.

Usage (from repo root):
    python paper/audit/analysis.py [--verilator paper/audit/resim_both.csv]

Definitions
-----------
Gate 1 (G1): testbench compiles and its simulation on the golden RTL satisfies the
    output contract. Vacuous testbenches satisfy this (they PASS the golden RTL); the
    archived `test_contract_valid` flag is overwritten to False for them by the
    pipeline, so G1 = test_compiled & (test_contract_valid | test_vacuous).
False rejection (FR): G1 & testbench reports FAIL on golden RTL (archived flag).
Cloud corpus: trials whose generator and tester are both gpt-4o-mini or gemini-flash.
    The 20 local trials (qwen-1.5b generator, llama-8b tester in every condition,
    including the nominal self-test A/D) are excluded from condition/model analyses.
"""
import argparse
import json

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

B = 10000
SEED = 42
COMB = ["Prob006_vectorr", "Prob021_mux256to1v", "Prob033_ece241_2014_q1c", "Prob043_vector5",
        "Prob091_2012_q2b", "Prob099_m2014_q6c", "Prob100_fsm3comb", "Prob114_bugs_case"]
INCON_IO = ["Prob068_countbcd", "Prob099_m2014_q6c"]          # port-level spec/ref contradictions
INCON_ALL = INCON_IO + ["Prob088_ece241_2014_q5b"]             # + internal-encoding-only mismatch
CLEAN6 = ["Prob006_vectorr", "Prob021_mux256to1v", "Prob033_ece241_2014_q1c", "Prob091_2012_q2b",
          "Prob100_fsm3comb", "Prob114_bugs_case"]
SIMPLE4 = ["Prob006_vectorr", "Prob021_mux256to1v", "Prob033_ece241_2014_q1c", "Prob114_bugs_case"]
CONDS = ["A", "B", "B_prime", "C", "C_prime", "D"]
OUT = {}


def wilson(k, n, z=1.959964):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 2), round(100 * (c + h), 2)]


def cluster_boot(sub, col="fr"):
    rng = np.random.default_rng(SEED)
    g = sub.groupby("problem_id")[col].agg(["sum", "count"])
    s, c = g["sum"].values, g["count"].values
    idx = rng.integers(0, len(g), size=(B, len(g)))
    r = s[idx].sum(1) / c[idx].sum(1)
    return [round(100 * np.percentile(r, 2.5), 2), round(100 * np.percentile(r, 97.5), 2)]


def rate_row(sub):
    k, n = int(sub.fr.sum()), len(sub)
    return {"problems": int(sub.problem_id.nunique()), "n": n, "k": k, "rate": round(100 * k / n, 2),
            "wilson": wilson(k, n), "cluster_boot": cluster_boot(sub)}


def paired_diff(r, a, b):
    """Problem-level paired difference r[b]-r[a]: bootstrap CI and sign-flip permutation p."""
    d = (r[b] - r[a]).dropna().values
    rng = np.random.default_rng(SEED)
    bs = d[rng.integers(0, len(d), size=(B, len(d)))].mean(1)
    null = (rng.choice([-1, 1], size=(B, len(d))) * d).mean(1)
    return {"problems": len(d), "mean_a": round(100 * r[a].loc[r[b].dropna().index].mean(), 2),
            "mean_b": round(100 * r[b].dropna().mean(), 2), "diff_pp": round(100 * d.mean(), 2),
            "boot_ci": [round(100 * np.percentile(bs, 2.5), 2), round(100 * np.percentile(bs, 97.5), 2)],
            "perm_p": round(float((np.abs(null) >= abs(d.mean()) - 1e-12).mean()), 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="v2/final/data/final_trials.csv")
    ap.add_argument("--verilator", default=None)
    ap.add_argument("--anchor", default="paper/audit/anchor_results.csv")
    ap.add_argument("--out", default="paper/audit/paper_numbers_audited.json")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, keep_default_na=False)
    f = df[df.arm == "freeform"].copy()
    f["g1"] = f.test_compiled & (f.test_contract_valid | f.test_vacuous)
    f["fr"] = f.false_rejection.astype(int)
    cloud_ids = {"gpt-4o-mini", "gemini-flash"}
    f["cloud"] = f.generator_id.isin(cloud_ids) & f.tester_id.isin(cloud_ids)

    # ---- Gate funnel -------------------------------------------------------------
    OUT["funnel"] = {
        "trials": len(f), "compile_fail": int((~f.test_compiled).sum()),
        "contract_fail": int((f.test_compiled & ~f.g1).sum()), "pass_gate1": int(f.g1.sum()),
        "false_rejection": int(f.fr.sum()), "pass_golden": int((f.g1 & (f.fr == 0)).sum()),
        "vacuous": int(f.test_vacuous.sum()), "valid": int(f.test_passed_golden_rtl.sum()),
        "tester_retry_used": int((f.tester_retries > 0).sum()),
    }
    t = df[df.arm == "template"]
    OUT["template_arm"] = {"trials": len(t), "compile_fail": int((~t.test_compiled).sum()),
                           "vacuous": int(t.test_vacuous.sum()), "valid": int(t.test_passed_golden_rtl.sum())}

    # ---- Table I -----------------------------------------------------------------
    g1 = f[f.g1]
    subsets = {
        "all": f, "cond": g1,
        "excl_io_incon": f[~f.problem_id.isin(INCON_IO)], "excl_io_incon_cond": g1[~g1.problem_id.isin(INCON_IO)],
        "excl_all_incon": f[~f.problem_id.isin(INCON_ALL)], "excl_all_incon_cond": g1[~g1.problem_id.isin(INCON_ALL)],
        "comb": f[f.problem_id.isin(COMB)], "comb_cond": g1[g1.problem_id.isin(COMB)],
        "seq": f[~f.problem_id.isin(COMB)], "seq_cond": g1[~g1.problem_id.isin(COMB)],
        "clean6": f[f.problem_id.isin(CLEAN6)], "clean6_cond": g1[g1.problem_id.isin(CLEAN6)],
        "simple4": f[f.problem_id.isin(SIMPLE4)], "simple4_cond": g1[g1.problem_id.isin(SIMPLE4)],
        "cloud": f[f.cloud], "cloud_cond": g1[g1.cloud],
    }
    OUT["table1"] = {k: rate_row(v) for k, v in subsets.items()}
    OUT["incon_trials"] = {"io": rate_row(f[f.problem_id.isin(INCON_IO)]),
                           "all3": rate_row(f[f.problem_id.isin(INCON_ALL)])}
    per_prob = f.groupby("problem_id").fr.mean().mul(100).round(2)
    OUT["per_problem_rate"] = per_prob.sort_values().to_dict()

    # ---- Clustering --------------------------------------------------------------
    g = f.groupby("problem_id").fr.agg(["sum", "count"])
    k, N = len(g), int(g["count"].sum())
    m0 = (N - (g["count"] ** 2).sum() / N) / (k - 1)
    p, pi = f.fr.mean(), g["sum"] / g["count"]
    msb = (g["count"] * (pi - p) ** 2).sum() / (k - 1)
    msw = (g["count"] * pi * (1 - pi)).sum() / (N - k)
    icc = (msb - msw) / (msb + (m0 - 1) * msw)
    deff = 1 + (N / k - 1) * icc
    OUT["clustering"] = {"icc": round(icc, 4), "mbar": round(N / k, 2), "deff": round(deff, 2),
                         "n_eff": round(N / deff, 1)}

    # ---- Conditions (cloud corpus) -------------------------------------------------
    c = f[f.cloud]
    cg = c[c.g1]
    tab = {}
    ct = []
    for cond in CONDS:
        s = c[c.condition == cond]
        kk, n = int(s.fr.sum()), len(s)
        ct.append([kk, n - kk])
        tab[cond] = {"n": n, "g1": int(s.g1.sum()), "k": kk, "rate": round(100 * kk / n, 2), "wilson": wilson(kk, n),
                     "cond_rate": round(100 * kk / s.g1.sum(), 2), "valid": int(s.test_passed_golden_rtl.sum()),
                     "mean_tester_tokens": int(round(s.tester_tokens.mean())),
                     "testers": s.tester_id.value_counts().to_dict()}
    chi2, pv, dof, _ = stats.chi2_contingency(np.array(ct), correction=False)
    OUT["conditions"] = {"table": tab, "chi2": round(chi2, 3), "df": int(dof), "p": round(pv, 4)}
    r = c.groupby(["problem_id", "condition"]).fr.mean().unstack()
    OUT["condition_pairs"] = {f"{b}-{a}": paired_diff(r, a, b) for a, b in
                              [("A", "D"), ("A", "B"), ("B", "B_prime"), ("B", "C"), ("C", "C_prime"),
                               ("A", "C")]}

    # ---- Factor re-coding: tester identity x prompt x RTL visibility ---------------
    c = c.assign(
        tester=np.where(c.tester_id == "gpt-4o-mini", "gpt", "gemini"),
        self_test=(c.tester_id == c.generator_id).astype(int),
        prompt=c.condition.map({"A": "self", "D": "self", "B": "adv_rtl", "C": "adv_rtl",
                                "B_prime": "adv_spec", "C_prime": "adv_spec"}),
    )
    tr = {}
    for (tst, pr), s in c.groupby(["tester", "prompt"]):
        tr[f"{tst}|{pr}"] = {"n": len(s), "k": int(s.fr.sum()), "rate": round(100 * s.fr.mean(), 2)}
    OUT["tester_by_prompt"] = tr
    for tst, s in c.groupby("tester"):
        OUT[f"tester_rate_{tst}"] = {"n": len(s), "k": int(s.fr.sum()), "rate": round(100 * s.fr.mean(), 2),
                                     "wilson": wilson(int(s.fr.sum()), len(s))}
    # GEE logistic regression, problem-clustered, exchangeable working correlation
    gee = smf.gee("fr ~ C(tester, Treatment('gemini')) + C(prompt, Treatment('self')) + self_test",
                  groups="problem_id", data=c, family=sm.families.Binomial(),
                  cov_struct=sm.cov_struct.Exchangeable()).fit()
    ci = gee.conf_int()
    OUT["gee"] = {name: {"OR": round(float(np.exp(gee.params[name])), 3),
                         "ci": [round(float(np.exp(ci.loc[name, 0])), 3), round(float(np.exp(ci.loc[name, 1])), 3)],
                         "p": round(float(gee.pvalues[name]), 4)} for name in gee.params.index}
    # Paired model comparisons
    rt = c.groupby(["problem_id", "tester_id"]).fr.mean().unstack()
    rgn = c.groupby(["problem_id", "generator_id"]).fr.mean().unstack()
    OUT["model_tester"] = paired_diff(rt, "gpt-4o-mini", "gemini-flash")
    OUT["model_tester_excl_io"] = paired_diff(rt.drop(INCON_IO), "gpt-4o-mini", "gemini-flash")
    OUT["model_generator"] = paired_diff(rgn, "gpt-4o-mini", "gemini-flash")
    # Same tester, different generator (does whose RTL is shown matter?)  Only RTL-visible prompts.
    vis = c[c.prompt != "adv_spec"]
    gen_eff = {}
    for tst, s in vis.groupby("tester_id"):
        rr = s.groupby(["problem_id", "generator_id"]).fr.mean().unstack()
        gen_eff[tst] = paired_diff(rr, "gpt-4o-mini", "gemini-flash")
    OUT["generator_effect_within_tester"] = gen_eff
    OUT["model_versions"] = {"generator": c.generator_model_version.value_counts().to_dict(),
                             "tester": c.tester_model_version.value_counts().to_dict()}

    # ---- Anchoring on candidate RTL -------------------------------------------------
    a = pd.read_csv(args.anchor, index_col=0)
    a = a.loc[c.index]
    a["vis"] = a.condition.isin(["A", "B", "C", "D"])
    afr = a[a.false_rejection]
    anch = {}
    for (vis_, corr), s in afr.groupby(["vis", "design_passed_golden_tb"]):
        anch[f"vis={vis_}|cand_correct={corr}"] = {"fr": len(s), "pass_on_candidate": int((s.tb_on_candidate == "pass").sum())}
    OUT["anchoring"] = anch
    bug = a[(~a.design_passed_golden_tb) & a.test_compiled & (a.test_contract_valid | a.test_vacuous)]
    OUT["anchoring_buggy_g1"] = {
        f"vis={v}": {"n": len(s), "fr": int(s.false_rejection.sum()),
                     "fr_and_accepts_bug": int((s.false_rejection & (s.tb_on_candidate == "pass")).sum())}
        for v, s in bug.groupby("vis")}
    # within-problem: FR when candidate buggy vs correct, RTL-visible prompts only (GEE)
    cc = c.copy()
    cc["cand_bug"] = (~cc.design_passed_golden_tb).astype(int)
    cc["vis"] = (cc.prompt != "adv_spec").astype(int)
    gee2 = smf.gee("fr ~ cand_bug * vis + C(tester)", groups="problem_id", data=cc,
                   family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable()).fit()
    ci2 = gee2.conf_int()
    OUT["gee_anchor"] = {n: {"OR": round(float(np.exp(gee2.params[n])), 3),
                             "ci": [round(float(np.exp(ci2.loc[n, 0])), 3), round(float(np.exp(ci2.loc[n, 1])), 3)],
                             "p": round(float(gee2.pvalues[n]), 4)} for n in gee2.params.index}

    # ---- Simulator cross-check ------------------------------------------------------
    if args.verilator:
        v = pd.read_csv(args.verilator, index_col=0)
        v = v[f.loc[v.index, "g1"]]
        ok = v.verilator_golden.isin(["pass", "fail"])
        agree = (v.icarus_golden == v.verilator_golden)
        fr_v = v[v.false_rejection]
        OUT["verilator"] = {
            "g1_testbenches": len(v), "verilator_ran": int(ok.sum()),
            "verilator_build_fail": int((v.verilator_golden == "compile_fail").sum()),
            "verilator_contract_violation": int((v.verilator_golden == "contract_violation").sum()),
            "verdict_agreement_where_ran": int(agree[ok].sum()),
            "fr_ran": int(fr_v.verilator_golden.isin(["pass", "fail"]).sum()),
            "fr_confirmed": int((fr_v.verilator_golden == "fail").sum()),
            "fr_flipped_to_pass": int((fr_v.verilator_golden == "pass").sum()),
            "pass_ran": int(v[~v.false_rejection].verilator_golden.isin(["pass", "fail"]).sum()),
            "pass_flipped_to_fail": int((v[~v.false_rejection].verilator_golden == "fail").sum()),
        }
        conf = v[ok]
        both_fr = int(((conf.icarus_golden == "fail") & (conf.verilator_golden == "fail")).sum())
        OUT["verilator"]["fr_rate_among_ran_icarus"] = round(100 * (conf.icarus_golden == "fail").mean(), 2)
        OUT["verilator"]["fr_rate_among_ran_both_agree"] = round(100 * both_fr / len(conf), 2)

    with open(args.out, "w") as fh:
        json.dump(OUT, fh, indent=1, default=str)
    print(json.dumps(OUT, indent=1, default=str))


if __name__ == "__main__":
    main()
