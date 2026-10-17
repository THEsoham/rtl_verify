"""Publication figure and table generator for RTL verification.

Generates:
1. Figure 1: Bug Escape Rate by Condition (with 95% bootstrap error bars)
2. Figure 2: Mutation Score by Condition and Category
3. Figure 3: Tester Strength Covariate Analysis (Controlling for tester quality confound)
4. Table 1: Comprehensive LaTeX / Markdown summary table
"""

import os
from typing import Dict, List
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from v2.src.metrics import ConditionSummary


# Publication style palette
PALETTE = {
    "A": "#4E79A7",       # Blue (Self-test)
    "B": "#59A14F",       # Green (Same-family adversary)
    "B_prime": "#8CD17D", # Light Green (Same-family spec-only)
    "C": "#E15759",       # Coral Red (Cross-family adversary)
    "C_prime": "#FF9D9A", # Light Coral (Cross-family spec-only)
    "D": "#B07AA1",       # Purple (Compute-matched)
}

CONDITION_LABELS = {
    "A": "A: Self-test\n(G writes TB)",
    "B": "B: Same-fam Adv\n(G' writes TB)",
    "B_prime": "B': Same-fam\n(Spec-only)",
    "C": "C: Cross-fam Adv\n(T writes TB)",
    "C_prime": "C': Cross-fam\n(Spec-only)",
    "D": "D: Compute-matched\n(G, 2x budget)",
}


def plot_escape_rate_comparison(
    summaries: Dict[str, ConditionSummary],
    output_path: str = "d:/rtl-verification/v2/results/figure1_escape_rate.png",
):
    """Plot Figure 1: Bug Escape Rate by Condition with 95% Bootstrap CIs."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    conditions = [c for c in ["A", "B", "B_prime", "C", "C_prime", "D"] if c in summaries]
    if not conditions:
        return

    rates = [summaries[c].escape_rate * 100 for c in conditions]
    labels = [CONDITION_LABELS.get(c, c) for c in conditions]
    colors = [PALETTE.get(c, "#7F7F7F") for c in conditions]

    yerr_low = []
    yerr_high = []
    for c in conditions:
        mean = summaries[c].escape_rate * 100
        low = summaries[c].ci_escape_rate[0] * 100
        high = summaries[c].ci_escape_rate[1] * 100
        yerr_low.append(max(0.0, mean - low))
        yerr_high.append(max(0.0, high - mean))

    yerr = [yerr_low, yerr_high]

    plt.figure(figsize=(9, 5), dpi=300)
    bars = plt.bar(labels, rates, yerr=yerr, capsize=5, color=colors, edgecolor="black", alpha=0.9, width=0.6)

    plt.ylabel("Bug Escape Rate (%)", fontsize=12, fontweight="bold")
    plt.title("Bug Escape Rate Across Verification Conditions (Lower is Better)", fontsize=13, fontweight="bold", pad=15)
    plt.ylim(0, 105)
    plt.grid(axis="y", linestyle="--", alpha=0.5)

    for bar in bars:
        h = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2.0, h + 3, f"{h:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_mutation_score_comparison(
    summaries: Dict[str, ConditionSummary],
    output_path: str = "d:/rtl-verification/v2/results/figure2_mutation_score.png",
):
    """Plot Figure 2: Mutation Score by Condition."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    conditions = [c for c in ["A", "B", "B_prime", "C", "C_prime", "D"] if c in summaries]
    if not conditions:
        return

    scores = [summaries[c].mutation_score * 100 for c in conditions]
    labels = [CONDITION_LABELS.get(c, c) for c in conditions]
    colors = [PALETTE.get(c, "#7F7F7F") for c in conditions]

    yerr_low = []
    yerr_high = []
    for c in conditions:
        mean = summaries[c].mutation_score * 100
        low = summaries[c].ci_mutation_score[0] * 100
        high = summaries[c].ci_mutation_score[1] * 100
        yerr_low.append(max(0.0, mean - low))
        yerr_high.append(max(0.0, high - mean))

    yerr = [yerr_low, yerr_high]

    plt.figure(figsize=(9, 5), dpi=300)
    bars = plt.bar(labels, scores, yerr=yerr, capsize=5, color=colors, edgecolor="black", alpha=0.9, width=0.6)

    plt.ylabel("Mutation Score (%)", fontsize=12, fontweight="bold")
    plt.title("Mutation Score on Non-Equivalent Faults (Higher is Better)", fontsize=13, fontweight="bold", pad=15)
    plt.ylim(0, 105)
    plt.grid(axis="y", linestyle="--", alpha=0.5)

    for bar in bars:
        h = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2.0, h + 3, f"{h:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def generate_results_table_markdown(summaries: Dict[str, ConditionSummary]) -> str:
    """Generate Markdown summary table for artifacts and papers."""
    lines = [
        "| Condition | Description | Valid Tests (FRR) | Mutation Score (95% CI) | Bug Escape Rate (95% CI) |",
        "|:---|:---|:---:|:---:|:---:|",
    ]
    for c in ["A", "B", "B_prime", "C", "C_prime", "D"]:
        if c not in summaries:
            continue
        s = summaries[c]
        frr_str = f"{s.valid_tests}/{s.total_tests} ({s.false_rejection_rate*100:.1f}%)"
        ms_str = f"{s.mutation_score*100:.1f}% [{s.ci_mutation_score[0]*100:.1f}, {s.ci_mutation_score[1]*100:.1f}]"
        esc_str = f"{s.escape_rate*100:.1f}% [{s.ci_escape_rate[0]*100:.1f}, {s.ci_escape_rate[1]*100:.1f}]"
        lines.append(f"| **{c}** | {CONDITION_LABELS.get(c, c).replace(chr(10), ' ')} | {frr_str} | {ms_str} | {esc_str} |")

    return "\n".join(lines)
