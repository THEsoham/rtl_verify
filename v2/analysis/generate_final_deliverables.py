"""Final Deliverables Generation Pipeline for Cross-Family RTL Verification.

Consolidates all experimental results, computes rigorous statistical metrics,
generates all 9 publication-grade figures (PNG @ 300 dpi, SVG, and CSV),
all LaTeX (.tex) and CSV tables, paper_numbers.json, failure analysis,
threats to validity, claims allowed, and the comprehensive final report + PDF.
"""

import csv
import json
import os
import re
import subprocess
import time
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from v2.src.metrics import (
    format_k_of_n,
    bootstrap_ci,
    permutation_test_paired,
    compute_condition_metrics,
    compute_wrong_expectation_agreement,
    compute_first_mismatch_taxonomy,
    ConditionSummary,
)


def load_trials(jsonl_path: str = "d:/rtl-verification/v2/final/data/incremental_trials.jsonl") -> List[Dict[str, Any]]:
    """Load and deduplicate all trial records from incremental JSONL log."""
    if not os.path.isfile(jsonl_path):
        return []
    
    trials_by_key = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
                k = (
                    t.get("arm", "freeform"),
                    t.get("generator_id", ""),
                    t.get("tester_id", ""),
                    t.get("problem_id", ""),
                    t.get("seed", 42),
                    t.get("condition", ""),
                )
                trials_by_key[k] = t
            except Exception:
                continue
    return list(trials_by_key.values())


def export_consolidated_data(trials: List[Dict[str, Any]], data_dir: str = "d:/rtl-verification/v2/final/data"):
    """Export clean final_trials.json and final_trials.csv without truncated fields."""
    os.makedirs(data_dir, exist_ok=True)
    json_path = os.path.join(data_dir, "final_trials.json")
    csv_path = os.path.join(data_dir, "final_trials.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(trials, f, indent=2)

    if trials:
        fieldnames = list(trials[0].keys())
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in trials:
                row = dict(t)
                for k, v in row.items():
                    if isinstance(v, (list, dict)):
                        row[k] = json.dumps(v)
                writer.writerow(row)
    print(f"Exported {len(trials)} consolidated trials to {json_path} and {csv_path}")


def compute_comprehensive_metrics(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute all statistical metrics across model pairs, conditions, and arms."""
    from v2.src.pipeline import TrialResult

    # Reconstruct TrialResult objects
    trial_objs = []
    for t in trials:
        try:
            trial_objs.append(TrialResult(**t))
        except Exception:
            pass

    arms = sorted(list(set(t.arm for t in trial_objs)))
    conditions = ["A", "D", "B", "B_prime", "C", "C_prime"]

    # Model Pairs
    model_pairs = {}
    for t in trial_objs:
        pair_key = f"{t.generator_id}_vs_{t.tester_id}"
        if pair_key not in model_pairs:
            model_pairs[pair_key] = {
                "generator_id": t.generator_id,
                "tester_id": t.tester_id,
                "name": f"{t.generator_id} vs {t.tester_id}",
            }

    # 1. Condition Summaries per Arm and Model Pair
    summaries_by_arm_pair: Dict[str, Dict[str, Dict[str, ConditionSummary]]] = defaultdict(lambda: defaultdict(dict))
    for arm in arms:
        arm_trials = [t for t in trial_objs if t.arm == arm]
        for pair_key in model_pairs:
            p_gen = model_pairs[pair_key]["generator_id"]
            for cond in conditions:
                c_pair_trials = [t for t in arm_trials if t.generator_id == p_gen and t.condition == cond]
                if c_pair_trials:
                    summaries_by_arm_pair[arm][pair_key][cond] = compute_condition_metrics(c_pair_trials)

    # Global summaries per arm, indexed by condition
    global_summaries: Dict[str, Dict[str, ConditionSummary]] = defaultdict(dict)
    for arm in arms:
        arm_trials = [t for t in trial_objs if t.arm == arm]
        for cond in conditions:
            c_trials = [t for t in arm_trials if t.condition == cond]
            global_summaries[arm][cond] = compute_condition_metrics(c_trials)

    # 2. First Mismatch Taxonomy (Phase C4)
    taxonomy = compute_first_mismatch_taxonomy(trial_objs)

    # 3. Wrong Expectation Agreement (Phase C5)
    agreement = compute_wrong_expectation_agreement(trial_objs)

    # 4. Paired Comparisons & Permutation Tests (Phase C)
    paired_tests = {}
    for arm in arms:
        arm_trials = [t for t in trial_objs if t.arm == arm]
        prob_ids = sorted(list(set(t.problem_id for t in arm_trials)))
        
        diffs_C_A = []
        diffs_C_D = []
        diffs_C_B = []
        diffs_C_Cprime = []

        for pid in prob_ids:
            p_trials = [t for t in arm_trials if t.problem_id == pid]
            c_val = [1.0 if t.test_passed_golden_rtl else 0.0 for t in p_trials if t.condition == "C"]
            a_val = [1.0 if t.test_passed_golden_rtl else 0.0 for t in p_trials if t.condition == "A"]
            d_val = [1.0 if t.test_passed_golden_rtl else 0.0 for t in p_trials if t.condition == "D"]
            b_val = [1.0 if t.test_passed_golden_rtl else 0.0 for t in p_trials if t.condition == "B"]
            cp_val = [1.0 if t.test_passed_golden_rtl else 0.0 for t in p_trials if t.condition == "C_prime"]

            if c_val and a_val:
                diffs_C_A.append(np.mean(c_val) - np.mean(a_val))
            if c_val and d_val:
                diffs_C_D.append(np.mean(c_val) - np.mean(d_val))
            if c_val and b_val:
                diffs_C_B.append(np.mean(c_val) - np.mean(b_val))
            if c_val and cp_val:
                diffs_C_Cprime.append(np.mean(c_val) - np.mean(cp_val))

        paired_tests[f"{arm}_C_vs_A"] = permutation_test_paired(diffs_C_A)
        paired_tests[f"{arm}_C_vs_D"] = permutation_test_paired(diffs_C_D)
        paired_tests[f"{arm}_C_vs_B"] = permutation_test_paired(diffs_C_B)
        paired_tests[f"{arm}_C_vs_Cprime"] = permutation_test_paired(diffs_C_Cprime)

    return {
        "trials_total": len(trial_objs),
        "arms": arms,
        "conditions": conditions,
        "model_pairs": model_pairs,
        "summaries_by_arm_pair": summaries_by_arm_pair,
        "global_summaries": global_summaries,
        "taxonomy": taxonomy,
        "agreement": agreement,
        "paired_tests": paired_tests,
    }


def generate_publication_plots(metrics: Dict[str, Any], trials: List[Dict[str, Any]], plot_dir: str = "d:/rtl-verification/v2/final/plots"):
    """Generate all 9 required figures at 300 dpi (PNG + SVG) and export each plot's backing CSV."""
    os.makedirs(plot_dir, exist_ok=True)
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.titlesize": 14,
        "figure.dpi": 300,
    })

    conditions = ["A", "D", "B", "B_prime", "C", "C_prime"]
    cond_labels = ["A (Self)", "D (Matched)", "B (Same+RTL)", "B' (Same-Spec)", "C (Cross+RTL)", "C' (Cross-Spec)"]

    freeform_sums = metrics["global_summaries"].get("freeform", {})
    categories = ["Valid", "Wrong Test", "Vacuous", "Contract Error", "Compile Fail"]
    colors = ["#2b8a3e", "#e03131", "#f08c00", "#7950f2", "#868e96"]
    
    bottoms = np.zeros(len(conditions))
    valid_counts = [freeform_sums[c].valid_tests if c in freeform_sums else 0 for c in conditions]
    wrong_counts = [freeform_sums[c].wrong_tests if c in freeform_sums else 0 for c in conditions]
    vac_counts = [freeform_sums[c].vacuous_tests if c in freeform_sums else 0 for c in conditions]
    contract_counts = [freeform_sums[c].contract_violations if c in freeform_sums else 0 for c in conditions]
    compile_counts = [freeform_sums[c].test_compile_fails if c in freeform_sums else 0 for c in conditions]
    totals = [freeform_sums[c].total_tests if c in freeform_sums else 1 for c in conditions]

    data_matrix = [
        np.array(valid_counts) / np.maximum(totals, 1) * 100.0,
        np.array(wrong_counts) / np.maximum(totals, 1) * 100.0,
        np.array(vac_counts) / np.maximum(totals, 1) * 100.0,
        np.array(contract_counts) / np.maximum(totals, 1) * 100.0,
        np.array(compile_counts) / np.maximum(totals, 1) * 100.0,
    ]

    # Plot 1: Outcome Breakdown
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for cat_idx, cat_name in enumerate(categories):
        vals = data_matrix[cat_idx]
        ax.bar(cond_labels, vals, bottom=bottoms, label=cat_name, color=colors[cat_idx], edgecolor="black", width=0.6)
        bottoms += vals

    ax.set_ylabel("Proportion of Tests (%)")
    ax.set_title("Figure 1: Test Outcome Breakdown Across Verification Conditions (Free-form Arm)")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", frameon=True)
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot1_outcome_breakdown.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot1_outcome_breakdown.svg"))
    plt.close(fig)

    df_p1 = pd.DataFrame({
        "Condition": conditions,
        "Label": cond_labels,
        "Total_n": totals,
        "Valid_pct": data_matrix[0],
        "Wrong_Test_pct": data_matrix[1],
        "Vacuous_pct": data_matrix[2],
        "Contract_Error_pct": data_matrix[3],
        "Compile_Fail_pct": data_matrix[4],
    })
    df_p1.to_csv(os.path.join(plot_dir, "plot1_outcome_breakdown.csv"), index=False)

    # Plot 2: Wrong-Test Rate
    fig, ax = plt.subplots(figsize=(8, 5))
    rates = []
    ci_err_low = []
    ci_err_high = []

    for c in conditions:
        summ = freeform_sums.get(c)
        r = (summ.wrong_test_rate * 100.0) if summ else 0.0
        ci = (summ.ci_wrong_test[0] * 100.0, summ.ci_wrong_test[1] * 100.0) if summ else (0.0, 0.0)
        rates.append(r)
        ci_err_low.append(max(0.0, r - ci[0]))
        ci_err_high.append(max(0.0, ci[1] - r))

    x = np.arange(len(conditions))
    ax.bar(x, rates, yerr=[ci_err_low, ci_err_high], capsize=5, color="#e03131", edgecolor="black", alpha=0.85, width=0.55)
    ax.set_xticks(x)
    ax.set_xticklabels(cond_labels, rotation=15)
    ax.set_ylabel("Wrong-Test Rate (%)")
    ax.set_title("Figure 2: Wrong-Test Rate Across Conditions with 95% Bootstrap CIs")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot2_wrong_test_rate.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot2_wrong_test_rate.svg"))
    plt.close(fig)

    df_p2 = pd.DataFrame({
        "Condition": conditions,
        "Wrong_Test_Rate_pct": rates,
        "CI_Low_pct": [r - el for r, el in zip(rates, ci_err_low)],
        "CI_High_pct": [r + eh for r, eh in zip(rates, ci_err_high)],
        "n": totals,
    })
    df_p2.to_csv(os.path.join(plot_dir, "plot2_wrong_test_rate.csv"), index=False)

    # Plot 3: Wrong Expectation Agreement
    fig, ax = plt.subplots(figsize=(7.5, 5))
    agr = metrics["agreement"]
    pairs_types = ["Same-Model\n(Different Samples)", "Same-Family\n(Condition A vs B)", "Cross-Family\n(Condition A vs C)"]
    agr_rates = [
        agr.same_model_agreement_rate * 100.0,
        agr.same_family_agreement_rate * 100.0,
        agr.cross_family_agreement_rate * 100.0,
    ]
    agr_cis = [
        (agr.ci_same_model[0] * 100.0, agr.ci_same_model[1] * 100.0),
        (agr.ci_same_family[0] * 100.0, agr.ci_same_family[1] * 100.0),
        (agr.ci_cross_family[0] * 100.0, agr.ci_cross_family[1] * 100.0),
    ]
    yerr_low = [max(0.0, r - ci[0]) for r, ci in zip(agr_rates, agr_cis)]
    yerr_high = [max(0.0, ci[1] - r) for r, ci in zip(agr_rates, agr_cis)]

    x3 = np.arange(len(pairs_types))
    colors3 = ["#1971c2", "#099268", "#f08c00"]
    ax.bar(x3, agr_rates, yerr=[yerr_low, yerr_high], capsize=6, color=colors3, edgecolor="black", width=0.5)
    ax.set_xticks(x3)
    ax.set_xticklabels(pairs_types)
    ax.set_ylabel("Agreement on Wrong Expectation (%)")
    ax.set_title("Figure 3: Shared Misreading Agreement on First Mismatch")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot3_wrong_expectation_agreement.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot3_wrong_expectation_agreement.svg"))
    plt.close(fig)

    df_p3 = pd.DataFrame({
        "Pair_Type": ["Same-Model", "Same-Family", "Cross-Family"],
        "Agreement_k": [agr.same_model_agreement_count, agr.same_family_agreement_count, agr.cross_family_agreement_count],
        "Total_Pairs_n": [agr.same_model_pairs_total, agr.same_family_pairs_total, agr.cross_family_pairs_total],
        "Agreement_Rate_pct": agr_rates,
        "CI_Low_pct": [ci[0] for ci in agr_cis],
        "CI_High_pct": [ci[1] for ci in agr_cis],
    })
    df_p3.to_csv(os.path.join(plot_dir, "plot3_wrong_expectation_agreement.csv"), index=False)

    # Plot 4: Mutation Score
    fig, ax = plt.subplots(figsize=(8, 5))
    ms_means = []
    ms_cis_low = []
    ms_cis_high = []

    for c in conditions:
        summ = freeform_sums.get(c)
        m = (summ.mutation_score * 100.0) if summ else 0.0
        ci = (summ.ci_mutation_score[0] * 100.0, summ.ci_mutation_score[1] * 100.0) if summ else (0.0, 0.0)
        ms_means.append(m)
        ms_cis_low.append(max(0.0, m - ci[0]))
        ms_cis_high.append(max(0.0, ci[1] - m))

    ax.bar(x, ms_means, yerr=[ms_cis_low, ms_cis_high], capsize=5, color="#2b8a3e", edgecolor="black", alpha=0.85, width=0.55)
    ax.set_xticks(x)
    ax.set_xticklabels(cond_labels, rotation=15)
    ax.set_ylabel("Mutation Score (%)")
    ax.set_title("Figure 4: Mutation Score (Valid Tests Only) with 95% CIs")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot4_mutation_score.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot4_mutation_score.svg"))
    plt.close(fig)

    df_p4 = pd.DataFrame({
        "Condition": conditions,
        "Mutation_Score_pct": ms_means,
        "CI_Low_pct": [m - el for m, el in zip(ms_means, ms_cis_low)],
        "CI_High_pct": [m + eh for m, eh in zip(ms_means, ms_cis_high)],
        "Mutants_Tested": [freeform_sums[c].valid_test_mutants_tested if c in freeform_sums else 0 for c in conditions],
        "Mutants_Killed": [freeform_sums[c].valid_test_mutants_killed if c in freeform_sums else 0 for c in conditions],
    })
    df_p4.to_csv(os.path.join(plot_dir, "plot4_mutation_score.csv"), index=False)

    # Plot 5: Escape Rate
    fig, ax = plt.subplots(figsize=(8, 5))
    esc_rates = []
    esc_n = []
    for c in conditions:
        summ = freeform_sums.get(c)
        r = (summ.escape_rate * 100.0) if (summ and summ.naturally_buggy_tested > 0 and summ.escape_rate is not None) else 0.0
        n_bugs = summ.naturally_buggy_tested if summ else 0
        esc_rates.append(r)
        esc_n.append(n_bugs)

    ax.bar(x, esc_rates, color="#d6336c", edgecolor="black", alpha=0.85, width=0.55)
    for idx, (r, n_b) in enumerate(zip(esc_rates, esc_n)):
        label = f"{r:.1f}%\n(n={n_b})" if n_b > 0 else "N/A\n(n=0)"
        ax.text(idx, r + 1.0, label, ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(cond_labels, rotation=15)
    ax.set_ylabel("Escape Rate E(G,T) (%)")
    ax.set_title("Figure 5: Natural Bug Escape Rate Across Conditions (Free-form Arm)")
    ax.set_ylim(0, max(25.0, max(esc_rates) * 1.3 if esc_rates else 25.0))
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot5_escape_rate.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot5_escape_rate.svg"))
    plt.close(fig)

    df_p5 = pd.DataFrame({
        "Condition": conditions,
        "Escape_Rate_pct": esc_rates,
        "Naturally_Buggy_Designs_n": esc_n,
    })
    df_p5.to_csv(os.path.join(plot_dir, "plot5_escape_rate.csv"), index=False)

    # Plot 6: Tester Strength (Confound Verification)
    fig, ax = plt.subplots(figsize=(8, 5))
    ts_rates = [(freeform_sums[c].tester_strength * 100.0) if c in freeform_sums else 0.0 for c in conditions]
    
    ax.bar(x, ts_rates, color="#495057", edgecolor="black", alpha=0.85, width=0.55)
    ax.set_xticks(x)
    ax.set_xticklabels(cond_labels, rotation=15)
    ax.set_ylabel("Tester Strength on Golden Mutants (%)")
    ax.set_title("Figure 6: Tester Strength Across Conditions (Confound Verification)")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot6_tester_strength.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot6_tester_strength.svg"))
    plt.close(fig)

    df_p6 = pd.DataFrame({
        "Condition": conditions,
        "Tester_Strength_pct": ts_rates,
        "Total_Mutants_Available": [freeform_sums[c].total_mutants_available if c in freeform_sums else 0 for c in conditions],
        "Total_Mutants_Killed": [freeform_sums[c].total_mutants_killed if c in freeform_sums else 0 for c in conditions],
    })
    df_p6.to_csv(os.path.join(plot_dir, "plot6_tester_strength.csv"), index=False)

    # Plot 7: Tokens Cost
    fig, ax = plt.subplots(figsize=(8.5, 5))
    gen_tokens = [freeform_sums[c].mean_generator_tokens if c in freeform_sums else 0.0 for c in conditions]
    tst_tokens = [freeform_sums[c].mean_tester_tokens if c in freeform_sums else 0.0 for c in conditions]

    ax.bar(cond_labels, gen_tokens, label="Generator Tokens", color="#4dabf7", edgecolor="black", width=0.55)
    ax.bar(cond_labels, tst_tokens, bottom=gen_tokens, label="Tester Tokens", color="#ffa94d", edgecolor="black", width=0.55)
    ax.set_ylabel("Mean Tokens per Trial")
    ax.set_title("Figure 7: Computational Cost Breakdown (Generator vs Tester Tokens)")
    ax.legend(loc="upper left")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot7_tokens_cost.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot7_tokens_cost.svg"))
    plt.close(fig)

    df_p7 = pd.DataFrame({
        "Condition": conditions,
        "Mean_Generator_Tokens": gen_tokens,
        "Mean_Tester_Tokens": tst_tokens,
        "Total_Mean_Tokens": [g + t for g, t in zip(gen_tokens, tst_tokens)],
    })
    df_p7.to_csv(os.path.join(plot_dir, "plot7_tokens_cost.csv"), index=False)

    # Plot 8: Problem Heatmap
    prob_piv = {}
    pids = sorted(list(set(t["problem_id"] for t in trials)))[:25]
    for pid in pids:
        prob_piv[pid] = []
        for c in conditions:
            c_trials = [t for t in trials if t.get("problem_id") == pid and t.get("condition") == c and t.get("arm") == "freeform"]
            if c_trials:
                valid_rate = np.mean([1.0 if t.get("test_passed_golden_rtl") else 0.0 for t in c_trials])
            else:
                valid_rate = np.nan
            prob_piv[pid].append(valid_rate)

    df_heat = pd.DataFrame(prob_piv, index=conditions).T
    fig, ax = plt.subplots(figsize=(8, max(6, len(pids) * 0.28)))
    cax = ax.matshow(df_heat.values, cmap="RdYlGn", vmin=0, vmax=1)
    fig.colorbar(cax, ax=ax, label="Valid Test Rate")
    ax.set_xticks(range(len(conditions)))
    ax.set_xticklabels(conditions)
    ax.set_yticks(range(len(pids)))
    ax.set_yticklabels(pids, fontsize=8)
    ax.set_title("Figure 8: Problem-Level Valid Test Rate Across Conditions", pad=20)
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot8_problem_heatmap.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot8_problem_heatmap.svg"))
    plt.close(fig)

    df_heat.to_csv(os.path.join(plot_dir, "plot8_problem_heatmap.csv"))

    # Plot 9: Arm Comparison
    fig, ax = plt.subplots(figsize=(8.5, 5))
    tmpl_sums = metrics["global_summaries"].get("template", {})
    ff_valid = [freeform_sums[c].valid_test_rate * 100.0 if c in freeform_sums else 0.0 for c in conditions]
    tmpl_valid = [tmpl_sums[c].valid_test_rate * 100.0 if c in tmpl_sums else 0.0 for c in conditions]

    x9 = np.arange(len(conditions))
    w = 0.35
    ax.bar(x9 - w/2, ff_valid, width=w, label="Free-form Arm", color="#4c6ef5", edgecolor="black")
    ax.bar(x9 + w/2, tmpl_valid, width=w, label="Template Arm", color="#12b886", edgecolor="black")
    ax.set_xticks(x9)
    ax.set_xticklabels(cond_labels, rotation=15)
    ax.set_ylabel("Valid Test Rate (%)")
    ax.set_title("Figure 9: Valid Test Rate Comparison: Free-form Arm vs Template Arm")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right")
    plt.tight_layout()

    fig.savefig(os.path.join(plot_dir, "plot9_arm_comparison.png"), dpi=300)
    fig.savefig(os.path.join(plot_dir, "plot9_arm_comparison.svg"))
    plt.close(fig)

    df_p9 = pd.DataFrame({
        "Condition": conditions,
        "Freeform_Valid_pct": ff_valid,
        "Template_Valid_pct": tmpl_valid,
    })
    df_p9.to_csv(os.path.join(plot_dir, "plot9_arm_comparison.csv"), index=False)
    print(f"Generated all 9 publication figures and backing CSVs in {plot_dir}")


def generate_tables(metrics: Dict[str, Any], trials: List[Dict[str, Any]], table_dir: str = "d:/rtl-verification/v2/final/tables"):
    """Generate all LaTeX (.tex) and CSV tables."""
    os.makedirs(table_dir, exist_ok=True)
    conditions = ["A", "D", "B", "B_prime", "C", "C_prime"]
    cond_labels = {"A": "A (Self)", "D": "D (Matched)", "B": "B (Same+RTL)", "B_prime": "B' (Same-Spec)", "C": "C (Cross+RTL)", "C_prime": "C' (Cross-Spec)"}

    # Table 4: Test Outcomes (Free-form Arm)
    ff_sums = metrics["global_summaries"].get("freeform", {})
    rows_t4 = []
    for c in conditions:
        s = ff_sums.get(c, ConditionSummary(condition=c))
        rows_t4.append({
            "Condition": cond_labels[c],
            "Total_n": s.total_tests,
            "Compile_Fail": format_k_of_n(s.test_compile_fails, s.total_tests),
            "Contract_Viol": format_k_of_n(s.contract_violations, s.total_tests),
            "Vacuous": format_k_of_n(s.vacuous_tests, s.total_tests),
            "Wrong_Test": format_k_of_n(s.wrong_tests, s.total_tests),
            "Valid_Test": format_k_of_n(s.valid_tests, s.total_tests),
        })
    df_t4 = pd.DataFrame(rows_t4)
    df_t4.to_csv(os.path.join(table_dir, "table4_test_outcomes_freeform.csv"), index=False)

    tex_t4 = df_t4.to_latex(index=False, caption="Test Outcome Breakdown (Free-form Arm)", label="tab:outcomes_freeform")
    with open(os.path.join(table_dir, "table4_test_outcomes_freeform.tex"), "w", encoding="utf-8") as f:
        f.write(tex_t4)

    # Table 5: Test Outcomes (Template Arm)
    tmpl_sums = metrics["global_summaries"].get("template", {})
    rows_t5 = []
    for c in conditions:
        s = tmpl_sums.get(c, ConditionSummary(condition=c))
        rows_t5.append({
            "Condition": cond_labels[c],
            "Total_n": s.total_tests,
            "Compile_Fail": format_k_of_n(s.test_compile_fails, s.total_tests),
            "Contract_Viol": format_k_of_n(s.contract_violations, s.total_tests),
            "Vacuous": format_k_of_n(s.vacuous_tests, s.total_tests),
            "Wrong_Test": format_k_of_n(s.wrong_tests, s.total_tests),
            "Valid_Test": format_k_of_n(s.valid_tests, s.total_tests),
        })
    df_t5 = pd.DataFrame(rows_t5)
    df_t5.to_csv(os.path.join(table_dir, "table5_test_outcomes_template.csv"), index=False)

    tex_t5 = df_t5.to_latex(index=False, caption="Test Outcome Breakdown (Template Arm)", label="tab:outcomes_template")
    with open(os.path.join(table_dir, "table5_test_outcomes_template.tex"), "w", encoding="utf-8") as f:
        f.write(tex_t5)

    # Table 6: Wrong-Expectation Agreement
    agr = metrics["agreement"]
    rows_t6 = [
        {
            "Comparison": "Same-Model (Different Seeds)",
            "Agreement_Count": agr.same_model_agreement_count,
            "Total_Pairs": agr.same_model_pairs_total,
            "Rate": format_k_of_n(agr.same_model_agreement_count, agr.same_model_pairs_total),
            "95_CI": f"[{agr.ci_same_model[0]*100:.1f}%, {agr.ci_same_model[1]*100:.1f}%]",
        },
        {
            "Comparison": "Same-Family (Condition A vs B)",
            "Agreement_Count": agr.same_family_agreement_count,
            "Total_Pairs": agr.same_family_pairs_total,
            "Rate": format_k_of_n(agr.same_family_agreement_count, agr.same_family_pairs_total),
            "95_CI": f"[{agr.ci_same_family[0]*100:.1f}%, {agr.ci_same_family[1]*100:.1f}%]",
        },
        {
            "Comparison": "Cross-Family (Condition A vs C)",
            "Agreement_Count": agr.cross_family_agreement_count,
            "Total_Pairs": agr.cross_family_pairs_total,
            "Rate": format_k_of_n(agr.cross_family_agreement_count, agr.cross_family_pairs_total),
            "95_CI": f"[{agr.ci_cross_family[0]*100:.1f}%, {agr.ci_cross_family[1]*100:.1f}%]",
        },
    ]
    df_t6 = pd.DataFrame(rows_t6)
    df_t6.to_csv(os.path.join(table_dir, "table6_wrong_expectation_agreement.csv"), index=False)
    with open(os.path.join(table_dir, "table6_wrong_expectation_agreement.tex"), "w", encoding="utf-8") as f:
        f.write(df_t6.to_latex(index=False, caption="Shared Misreading Agreement Rates on First Mismatch", label="tab:wrong_agreement"))

    # Table 7: Mutation Score and Tester Strength
    rows_t7 = []
    for c in conditions:
        s = ff_sums.get(c, ConditionSummary(condition=c))
        rows_t7.append({
            "Condition": cond_labels[c],
            "Valid_Tests_n": s.valid_tests,
            "Mutation_Score": format_k_of_n(s.valid_test_mutants_killed, s.valid_test_mutants_tested),
            "Mutation_Score_95_CI": f"[{s.ci_mutation_score[0]*100:.1f}%, {s.ci_mutation_score[1]*100:.1f}%]",
            "Tester_Strength_All": format_k_of_n(s.total_mutants_killed, s.total_mutants_available),
        })
    df_t7 = pd.DataFrame(rows_t7)
    df_t7.to_csv(os.path.join(table_dir, "table7_mutation_and_tester_strength.csv"), index=False)
    with open(os.path.join(table_dir, "table7_mutation_and_tester_strength.tex"), "w", encoding="utf-8") as f:
        f.write(df_t7.to_latex(index=False, caption="Mutation Score on Valid Tests vs Global Tester Strength", label="tab:mutation_strength"))

    # Table 8: Escape Rate & Validator-Fooled Rate
    rows_t8 = []
    for c in conditions:
        s = ff_sums.get(c, ConditionSummary(condition=c))
        rows_t8.append({
            "Condition": cond_labels[c],
            "Natural_Bugs_Tested_n": s.naturally_buggy_tested,
            "Bugs_Escaped_k": s.naturally_buggy_escaped,
            "Escape_Rate": format_k_of_n(s.naturally_buggy_escaped, s.naturally_buggy_tested),
            "Validator_Fooled_Rate": format_k_of_n(s.validator_fooled_count, s.validator_fooled_total),
        })
    df_t8 = pd.DataFrame(rows_t8)
    df_t8.to_csv(os.path.join(table_dir, "table8_escape_and_validator_fooled.csv"), index=False)
    with open(os.path.join(table_dir, "table8_escape_and_validator_fooled.tex"), "w", encoding="utf-8") as f:
        f.write(df_t8.to_latex(index=False, caption="Escape Rate and CorrectBench-Style Validator-Fooled Rate", label="tab:escape_vfr"))

    # Table 9: Computational Cost & Tokens
    rows_t9 = []
    for c in conditions:
        s = ff_sums.get(c, ConditionSummary(condition=c))
        rows_t9.append({
            "Condition": cond_labels[c],
            "Generator_Tokens_Mean": f"{s.mean_generator_tokens:.1f}",
            "Tester_Tokens_Mean": f"{s.mean_tester_tokens:.1f}",
            "Retries_Total": s.total_retries,
            "Wall_Time_sec_Mean": f"{s.mean_duration_sec:.2f}",
        })
    df_t9 = pd.DataFrame(rows_t9)
    df_t9.to_csv(os.path.join(table_dir, "table9_cost_and_tokens.csv"), index=False)
    with open(os.path.join(table_dir, "table9_cost_and_tokens.tex"), "w", encoding="utf-8") as f:
        f.write(df_t9.to_latex(index=False, caption="Computational Token Cost and Retries per Condition", label="tab:cost_tokens"))

    # Table 10: First Mismatch Taxonomy
    tax = metrics["taxonomy"]
    tot_tax = sum(tax.values())
    rows_t10 = [
        {"Category": "Off-by-one Timing", "Count": tax["off_by_one_timing"], "Proportion": format_k_of_n(tax["off_by_one_timing"], tot_tax)},
        {"Category": "Wrong Reset Behavior", "Count": tax["wrong_reset_behavior"], "Proportion": format_k_of_n(tax["wrong_reset_behavior"], tot_tax)},
        {"Category": "Wrong Wrap Value", "Count": tax["wrong_wrap_value"], "Proportion": format_k_of_n(tax["wrong_wrap_value"], tot_tax)},
        {"Category": "Wrong Initial Value", "Count": tax["wrong_initial_value"], "Proportion": format_k_of_n(tax["wrong_initial_value"], tot_tax)},
        {"Category": "Other Functional Mismatch", "Count": tax["other"], "Proportion": format_k_of_n(tax["other"], tot_tax)},
    ]
    df_t10 = pd.DataFrame(rows_t10)
    df_t10.to_csv(os.path.join(table_dir, "table10_first_mismatch_taxonomy.csv"), index=False)
    with open(os.path.join(table_dir, "table10_first_mismatch_taxonomy.tex"), "w", encoding="utf-8") as f:
        f.write(df_t10.to_latex(index=False, caption="Rule-Based Classification of First Mismatches on Golden RTL", label="tab:taxonomy"))

    print(f"Generated all LaTeX and CSV summary tables in {table_dir}")


def build_paper_numbers_json(metrics: Dict[str, Any], out_path: str = "d:/rtl-verification/v2/final/paper_numbers.json"):
    """Map every single number cited in the report directly to its backing file and field."""
    ff_sums = metrics["global_summaries"].get("freeform", {})
    agr = metrics["agreement"]
    tax = metrics["taxonomy"]

    numbers = {
        "metadata": {
            "generated_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_experiment": "Cross-Family Verilog Verification (v2/final)",
            "total_trials": metrics["trials_total"],
        },
        "table4_freeform_outcomes": {
            c: {
                "file": "v2/final/tables/table4_test_outcomes_freeform.csv",
                "total_n": ff_sums[c].total_tests if c in ff_sums else 0,
                "valid_tests_k": ff_sums[c].valid_tests if c in ff_sums else 0,
                "valid_test_rate_pct": round(ff_sums[c].valid_test_rate * 100.0, 2) if c in ff_sums else 0.0,
                "wrong_tests_k": ff_sums[c].wrong_tests if c in ff_sums else 0,
                "wrong_test_rate_pct": round(ff_sums[c].wrong_test_rate * 100.0, 2) if c in ff_sums else 0.0,
                "vacuous_tests_k": ff_sums[c].vacuous_tests if c in ff_sums else 0,
                "vacuous_test_rate_pct": round(ff_sums[c].vacuous_test_rate * 100.0, 2) if c in ff_sums else 0.0,
                "contract_violations_k": ff_sums[c].contract_violations if c in ff_sums else 0,
                "compile_fails_k": ff_sums[c].test_compile_fails if c in ff_sums else 0,
            }
            for c in ["A", "D", "B", "B_prime", "C", "C_prime"]
        },
        "table6_wrong_agreement": {
            "file": "v2/final/tables/table6_wrong_expectation_agreement.csv",
            "same_model": {
                "k": agr.same_model_agreement_count,
                "n": agr.same_model_pairs_total,
                "rate_pct": round(agr.same_model_agreement_rate * 100.0, 2),
                "ci_95": [round(agr.ci_same_model[0] * 100.0, 2), round(agr.ci_same_model[1] * 100.0, 2)],
            },
            "same_family": {
                "k": agr.same_family_agreement_count,
                "n": agr.same_family_pairs_total,
                "rate_pct": round(agr.same_family_agreement_rate * 100.0, 2),
                "ci_95": [round(agr.ci_same_family[0] * 100.0, 2), round(agr.ci_same_family[1] * 100.0, 2)],
            },
            "cross_family": {
                "k": agr.cross_family_agreement_count,
                "n": agr.cross_family_pairs_total,
                "rate_pct": round(agr.cross_family_agreement_rate * 100.0, 2),
                "ci_95": [round(agr.ci_cross_family[0] * 100.0, 2), round(agr.ci_cross_family[1] * 100.0, 2)],
            },
        },
        "table7_mutation": {
            c: {
                "file": "v2/final/tables/table7_mutation_and_tester_strength.csv",
                "mutation_score_pct": round(ff_sums[c].mutation_score * 100.0, 2) if c in ff_sums else 0.0,
                "mutants_killed_k": ff_sums[c].valid_test_mutants_killed if c in ff_sums else 0,
                "mutants_tested_n": ff_sums[c].valid_test_mutants_tested if c in ff_sums else 0,
                "tester_strength_pct": round(ff_sums[c].tester_strength * 100.0, 2) if c in ff_sums else 0.0,
            }
            for c in ["A", "D", "B", "B_prime", "C", "C_prime"]
        },
        "table8_escape": {
            c: {
                "file": "v2/final/tables/table8_escape_and_validator_fooled.csv",
                "natural_bugs_tested_n": ff_sums[c].naturally_buggy_tested if c in ff_sums else 0,
                "bugs_escaped_k": ff_sums[c].naturally_buggy_escaped if c in ff_sums else 0,
                "escape_rate_pct": round(ff_sums[c].escape_rate * 100.0, 2) if (c in ff_sums and ff_sums[c].escape_rate is not None and ff_sums[c].naturally_buggy_tested > 0) else "N/A",
                "validator_fooled_rate_pct": round(ff_sums[c].validator_fooled_rate * 100.0, 2) if (c in ff_sums and ff_sums[c].validator_fooled_rate is not None) else "N/A",
            }
            for c in ["A", "D", "B", "B_prime", "C", "C_prime"]
        },
        "table10_taxonomy": {
            "file": "v2/final/tables/table10_first_mismatch_taxonomy.csv",
            "off_by_one_timing": tax["off_by_one_timing"],
            "wrong_reset_behavior": tax["wrong_reset_behavior"],
            "wrong_wrap_value": tax["wrong_wrap_value"],
            "wrong_initial_value": tax["wrong_initial_value"],
            "other": tax["other"],
            "total_wrong_tests": sum(tax.values()),
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(numbers, f, indent=2)
    print(f"Exported paper_numbers.json to {out_path}")


def main():
    print("=" * 70)
    print("CROSS-FAMILY VERIFICATION: FINAL DELIVERABLES GENERATION PIPELINE")
    print("=" * 70)

    # 1. Load trials from incremental log
    trials = load_trials()
    if not trials:
        print("No trials found in incremental log. Exiting.")
        return

    print(f"Loaded {len(trials)} unique experimental trials.")

    # 2. Export final_trials.json and final_trials.csv (Phase D4)
    export_consolidated_data(trials)

    # 3. Compute Comprehensive Metrics (Phase C)
    print("Computing metrics, bootstrap confidence intervals, and paired permutation tests...")
    metrics = compute_comprehensive_metrics(trials)

    # 4. Generate all 9 publication figures (PNG @ 300 dpi, SVG, and CSV) (Phase D2)
    print("Generating publication plots and backing CSV files...")
    generate_publication_plots(metrics, trials)

    # 5. Generate all LaTeX (.tex) and CSV tables (Phase D3)
    print("Generating LaTeX (.tex) and CSV summary tables...")
    generate_tables(metrics, trials)

    # 6. Generate paper_numbers.json (Phase D5)
    print("Generating paper_numbers.json...")
    build_paper_numbers_json(metrics)

    # 7. Generate threats_to_validity.md, claims_allowed.md, failure_analysis.md (Phase D6, D7)
    from v2.analysis.deliverables_text import (
        build_threats_to_validity_md,
        build_claims_allowed_md,
        build_failure_analysis_md,
    )
    final_dir = "d:/rtl-verification/v2/final"
    with open(os.path.join(final_dir, "threats_to_validity.md"), "w", encoding="utf-8") as f:
        f.write(build_threats_to_validity_md(metrics, trials))
    print("Exported threats_to_validity.md")

    with open(os.path.join(final_dir, "claims_allowed.md"), "w", encoding="utf-8") as f:
        f.write(build_claims_allowed_md(metrics, trials))
    print("Exported claims_allowed.md")

    with open(os.path.join(final_dir, "failure_analysis.md"), "w", encoding="utf-8") as f:
        f.write(build_failure_analysis_md(metrics, trials))
    print("Exported failure_analysis.md")

    # Compute SHA-256 Checksum of final data file (Requirement 10)
    import hashlib
    final_json_path = os.path.join(final_dir, "data", "final_trials.json")
    if os.path.isfile(final_json_path):
        with open(final_json_path, "rb") as f_chk:
            sha256_hash = hashlib.sha256(f_chk.read()).hexdigest()
        chk_path = os.path.join(final_dir, "data", "checksum.txt")
        with open(chk_path, "w", encoding="utf-8") as f_chk_out:
            f_chk_out.write(sha256_hash + "\n")
        print(f"Computed SHA-256 checksum for {final_json_path}: {sha256_hash}")

    # 8. Generate final_report.md and compile final_report.pdf (Phase D1)
    from v2.analysis.build_full_report import generate_full_report
    print("Generating comprehensive final report and rendering publication PDF...")
    generate_full_report(metrics, trials)

    print("=" * 70)
    print("ALL PHASE D DELIVERABLES SUCCESSFULLY GENERATED IN v2/final/")
    print("=" * 70)


if __name__ == "__main__":
    main()

