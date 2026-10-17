"""Render Publication-Grade Pipeline Architecture Diagram (PNG @ 300 dpi and SVG)."""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches


def render_pipeline_diagram(out_dir: str = "d:/rtl-verification/v2/final/plots"):
    os.makedirs(out_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 8), dpi=300)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.axis("off")

    # Colors
    c_blue = "#e7f5ff"
    c_blue_b = "#1971c2"
    c_green = "#ebfbee"
    c_green_b = "#2f9e44"
    c_orange = "#fff4e6"
    c_orange_b = "#e8590c"
    c_purple = "#f3f0ff"
    c_purple_b = "#7950f2"
    c_red = "#fff5f5"
    c_red_b = "#e03131"
    c_gray = "#f8f9fa"
    c_gray_b = "#495057"

    def draw_box(x, y, w, h, title, subtitle, bg_color, border_color):
        rect = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.1,rounding_size=0.15",
            facecolor=bg_color,
            edgecolor=border_color,
            linewidth=1.8,
        )
        ax.add_patch(rect)
        ax.text(x + w/2, y + h - 0.35, title, ha="center", va="top", fontsize=11, fontweight="bold", color=border_color)
        ax.text(x + w/2, y + h/2 - 0.15, subtitle, ha="center", va="center", fontsize=8.5, color="#212529", wrap=True)

    def draw_arrow(x1, y1, x2, y2, label=""):
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="->", color="#343a40", lw=1.8, shrinkA=3, shrinkB=3)
        )
        if label:
            mx, my = (x1 + x2)/2, (y1 + y2)/2
            ax.text(mx, my + 0.15, label, ha="center", va="bottom", fontsize=8, fontweight="semibold", color="#343a40")

    # Title
    ax.text(7, 7.6, "Cross-Family LLM RTL Verification Architecture (v2 Pipeline)", ha="center", va="center", fontsize=15, fontweight="bold", color="#1c7ed6")

    # Stage 1: Problem Screening & Golden Checks
    draw_box(0.5, 5.0, 3.8, 2.0, "Stage 1: Problem Screening",
             "• 156 VerilogEval problems tested\n• Official Ref Testbench in Icarus Verilog\n• 30 Diverse Circuits Kept (counters, FSMs)\n• Hard requirement: >= 8 non-equiv mutants",
             c_blue, c_blue_b)

    # Stage 2: Mutant Generation & Equiv Checking
    draw_box(0.5, 1.8, 3.8, 2.4, "Stage 2: Mutation Suite",
             "• AST/Regex Operators (AOR, ROR, LOR, OFF, RST)\n• Span Protection: no initial block mutations\n• 2,000 Differential Random Vectors\n• 1% Rare-Reset Sequence\n• Exact Sentinels: SAME vs DIFFERENT\n• 411 Non-equivalent mutants precomputed",
             c_orange, c_orange_b)

    # Stage 3: Candidate RTL Generation
    draw_box(5.1, 5.0, 3.8, 2.0, "Stage 3: RTL Generation (G)",
             "• Generator G writes 'TopModule'\n• Generated ONCE per (Problem, Sample)\n• Reused across all 6 conditions\n• 1-Retry Rule on compile syntax errors\n• Tested against official golden testbench",
             c_purple, c_purple_b)

    # Stage 4: Testbench Generation
    draw_box(5.1, 1.8, 3.8, 2.4, "Stage 4: Testbench Synthesis",
             "• 6 Conditions: A, D (Self), B, B' (Same), C, C' (Cross)\n• 2 Arms: Free-form vs Template Scaffold\n• Strict Contract: self-checking, 1 PASS/FAIL line\n• $finish clean exit, '!==' 4-state checks\n• Condition D: compute-matched to C",
             c_green, c_green_b)

    # Stage 5: Validity & Non-Vacuity Gates
    draw_box(9.7, 5.0, 3.8, 2.0, "Stage 5: Dual Validity Gates",
             "• Gate 1: Compile & Contract Validation\n• Gate 2: Must PASS on Golden RTL\n• Gate 3: Must FAIL on Inverted Gate\n  (Rejects trivial always-pass vacuous tests)\n• Extract first mismatch if failed",
             c_red, c_red_b)

    # Stage 6: Scoring & Statistical Inference
    draw_box(9.7, 1.8, 3.8, 2.4, "Stage 6: Metrics & Statistics",
             "• Mutation Score on Valid Tests\n• Global Tester Strength (Confound Audit)\n• Natural Bug Escape Rate E(G,T)\n• Shared Misreading Agreement Analysis\n• CorrectBench Validator-Fooled Rate\n• 10,000 Bootstrap CIs & Permutation Tests",
             c_gray, c_gray_b)

    # Connecting Arrows
    draw_arrow(4.3, 6.0, 5.1, 6.0, "Screened Probs")
    draw_arrow(7.0, 5.0, 7.0, 4.2, "Reused RTL")
    draw_arrow(2.4, 5.0, 2.4, 4.2, "Golden RTL")
    draw_arrow(4.3, 3.0, 5.1, 3.0, "Mutant Suites")
    draw_arrow(8.9, 3.0, 9.7, 3.0, "Candidate Tests")
    draw_arrow(11.6, 5.0, 11.6, 4.2, "Valid Tests Only")

    plt.tight_layout()
    png_path = os.path.join(out_dir, "pipeline_architecture.png")
    svg_path = os.path.join(out_dir, "pipeline_architecture.svg")
    fig.savefig(png_path, dpi=300)
    fig.savefig(svg_path)
    plt.close(fig)
    print(f"Rendered pipeline architecture diagram to {png_path} and {svg_path}")


if __name__ == "__main__":
    render_pipeline_diagram()
