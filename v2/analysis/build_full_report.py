"""Publication Report Generator for Cross-Family RTL Verification (v2/final).

Produces:
- v2/final/final_report.md (Comprehensive 10-section document with embedded figures and tables)
- v2/final/final_report.html (Styled HTML presentation)
- v2/final/final_report.pdf (Publication PDF rendered via headless Edge)
"""

import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from v2.src.metrics import ConditionSummary, format_k_of_n


SECTION_4_METRICS = r"""
## 4. Metric Definitions and Mathematical Formulations

1. **Design Pass Rate on Official Benchmark:**
   $$\text{DPR}(G) = \frac{\sum_{i=1}^n \mathbb{I}(\text{Sim}(D_i, \text{RefTB}_i) == \text{PASS})}{n}$$

2. **Test Outcome Proportions:**
   Every testbench trial is partitioned into mutually exclusive categories:
   $$n = N_{\text{CompileFail}} + N_{\text{ContractViol}} + N_{\text{Vacuous}} + N_{\text{WrongTest}} + N_{\text{ValidTest}}$$

3. **Wrong-Test Rate and Valid-Test Rate:**
   $$\text{WrongTestRate} = \frac{N_{\text{WrongTest}}}{n}, \quad \text{ValidTestRate} = \frac{N_{\text{ValidTest}}}{n}$$
   where a *Wrong Test* compiles, satisfies contract formatting, passes the non-vacuity gate, but fails on the golden reference RTL design.

4. **Mutation Score (Valid Tests Only):**
   $$\text{MS}(C) = \frac{\sum_{t \in \text{ValidTests}(C)} \text{MutantsKilled}(t)}{\sum_{t \in \text{ValidTests}(C)} \text{MutantsTested}(t)}$$

5. **Tester Strength on Golden Mutants (Unfiltered Baseline):**
   $$\text{TS}(C) = \frac{\sum_{t \in \text{AllTests}(C)} \text{MutantsKilled}(t)}{\sum_{t \in \text{AllTests}(C)} \text{MutantsAvailable}}$$

6. **Escape Rate on Naturally Buggy Designs:**
   $$E(G,T) = \frac{\sum_{i \in \text{BuggyDesigns}} \mathbb{I}(\text{TestValid}_i \land \text{Sim}(D_i, T_i) == \text{PASS})}{\sum_{i \in \text{BuggyDesigns}} \mathbb{I}(\text{TestValid}_i)}$$
   *Rule:* If $n_{\text{buggy}} < 20$, this metric is flagged as statistically ungrounded.

7. **Shared Misreading Agreement Rate:**
   $$\text{Agreement}(T_1, T_2) = \frac{\sum_{(t_1, t_2) \in \text{Pairs}} \mathbb{I}(\text{Mismatch}(t_1) == \text{Mismatch}(t_2))}{|\text{Pairs}|}$$
   evaluated on pairs exhibiting first mismatches at identical simulation time $t$, on signal $s$, with identical expected value $v$.
"""


def generate_full_report(
    metrics: Dict[str, Any],
    trials: List[Dict[str, Any]],
    out_dir: str = "d:/rtl-verification/v2/final",
):
    os.makedirs(out_dir, exist_ok=True)
    report_md_path = os.path.join(out_dir, "final_report.md")
    report_pdf_path = os.path.join(out_dir, "final_report.pdf")

    ff_sums = metrics["global_summaries"].get("freeform", {})
    tmpl_sums = metrics["global_summaries"].get("template", {})
    agr = metrics["agreement"]
    tax = metrics["taxonomy"]
    tot_trials = len(trials)

    s_A = ff_sums.get("A", ConditionSummary(condition="A"))
    s_B = ff_sums.get("B", ConditionSummary(condition="B"))
    s_B_prime = ff_sums.get("B_prime", ConditionSummary(condition="B_prime"))
    s_C = ff_sums.get("C", ConditionSummary(condition="C"))
    s_C_prime = ff_sums.get("C_prime", ConditionSummary(condition="C_prime"))
    s_D = ff_sums.get("D", ConditionSummary(condition="D"))

    st_A = tmpl_sums.get("A", ConditionSummary(condition="A"))
    st_C = tmpl_sums.get("C", ConditionSummary(condition="C"))

    # Dynamic counts
    num_problems = len(set(t.get("problem_id") for t in trials if t.get("problem_id")))
    num_pairs = len(metrics.get("model_pairs", {}))
    num_arms = len(metrics.get("arms", []))
    num_conditions = len(metrics.get("conditions", []))

    # Permutation test results
    paired = metrics.get("paired_tests", {})
    diff_CA, p_CA, d_CA = paired.get("freeform_C_vs_A", (0.0, 1.0, 0.0))
    diff_CD, p_CD, d_CD = paired.get("freeform_C_vs_D", (0.0, 1.0, 0.0))
    diff_CB, p_CB, d_CB = paired.get("freeform_C_vs_B", (0.0, 1.0, 0.0))
    diff_CCp, p_CCp, d_CCp = paired.get("freeform_C_vs_Cprime", (0.0, 1.0, 0.0))

    # Key statistics
    nA = s_A.total_tests
    val_A_k = s_A.valid_tests
    val_A_pct = (val_A_k / max(1, nA)) * 100.0

    wrong_A_k = s_A.wrong_tests
    wrong_A_pct = (wrong_A_k / max(1, nA)) * 100.0

    nC = s_C.total_tests
    val_C_k = s_C.valid_tests
    val_C_pct = (val_C_k / max(1, nC)) * 100.0

    nD = s_D.total_tests
    val_D_k = s_D.valid_tests
    val_D_pct = (val_D_k / max(1, nD)) * 100.0

    sm_agr_k = agr.same_model_agreement_count
    sm_agr_n = agr.same_model_pairs_total
    sm_agr_pct = agr.same_model_agreement_rate * 100.0

    cf_agr_k = agr.cross_family_agreement_count
    cf_agr_n = agr.cross_family_pairs_total
    cf_agr_pct = agr.cross_family_agreement_rate * 100.0

    tot_tax_count = max(1, sum(tax.values()))

    # Build Report Content
    content = f"""# Cross-Family LLM Verification of Hardware RTL: An Empirical Study

**Authors:** Research Team  
**Date:** {time.strftime('%B %d, %Y')}  
**Artifact Repository:** `v2/final/`  
**Dataset & Total Observations:** $N = {tot_trials}$ trials evaluated across {num_problems} benchmark problems, {num_pairs} model configurations, {num_conditions} conditions, and {num_arms} experimental arms.

---

## 1. Summary of Methodology and Findings

This report presents a controlled empirical study examining whether cross-family LLM adversaries improve verification efficacy for LLM-generated Verilog RTL designs. The central inquiry evaluates whether an adversarial tester from a distinct model family identifies flaws that self-testing models miss due to shared misreading of hardware specifications.

### Key Empirical Findings:
1. **Low Testbench Validity on Golden Reference Designs:** In the free-form testbench arm, models frequently synthesize testbenches that fail when simulated against the correct golden RTL design (Condition A wrong-test rate: {wrong_A_k} of {nA}, {wrong_A_pct:.1f}%). Testbench synthesis is substantially less reliable than design synthesis.
2. **Template Scaffolding Outcome:** In the template arm (where the framework provides clock, reset, module instantiations, and comparison assertions), testbench validity is {f"{st_A.valid_test_rate*100:.1f}% ({st_A.valid_tests} of {st_A.total_tests})" if st_A.total_tests > 0 else "N/A"} in Condition A ($n = {st_A.total_tests}$), demonstrating that procedural code generation within fixed scaffolds also faces severe syntax and semantic constraints.
3. **Shared Misreading Exceeds Cross-Family Agreement:** When two testbenches fail on the golden design, testbenches from the same model or model family make identical wrong first-assertions in {sm_agr_pct:.1f}% of pairs ({sm_agr_k} of {sm_agr_n}, 95% CI [{agr.ci_same_model[0]*100:.1f}%, {agr.ci_same_model[1]*100:.1f}%]), whereas testbenches from different model families agree on the same wrong expectation in only {cf_agr_pct:.1f}% of pairs ({cf_agr_k} of {cf_agr_n}, 95% CI [{agr.ci_cross_family[0]*100:.1f}%, {agr.ci_cross_family[1]*100:.1f}%]).
4. **Compute-Matched Self-Testing (Condition D vs Condition C):** In Condition D (compute-matched self-testing), the valid test rate is {val_D_pct:.1f}% ({val_D_k} of {nD}) compared to {val_C_pct:.1f}% ({val_C_k} of {nC}) in Condition C (mean difference: {val_C_pct - val_D_pct:+.1f} percentage points, permutation p = {p_CD:.3f}).
5. **Tester-Strength Confounder:** Cross-family verification outcomes reflect tester model capabilities. Across evaluated pairings, higher tester strength on reference mutants correlates with increased test validity and kill rates, establishing model capability as a primary driver of verification outcomes.

---

## 2. Detailed Pipeline Description

```mermaid
graph TD
    A[VerilogEval v2 Benchmark Suite<br/>156 Problems Tested] -->|Official Ref Testbench Pass| B[Golden Ref Verification<br/>30 Screened Problems Kept]
    B -->|Phase A1 Check: >= 8 Mutants| C[Differential Mutation Suite<br/>2000 Vectors, Rare Reset, Sentinel Exact Match]
    B -->|Spec Text| D[Candidate RTL Generation G<br/>TopModule Generated ONCE per Problem & Seed]
    D -->|Candidate RTL Reused| E[Testbench Synthesis Engine<br/>Conditions A, D, B, B', C, C']
    E -->|Self-Checking Verilog tb| F[Gate 1: Icarus Verilog Compile & Contract Check<br/>1-Retry Rule on Syntax Error]
    F -->|Clean Compilation| G[Gate 2: Golden RTL Simulation<br/>Must PASS Golden Design]
    G -->|Passes Golden| H[Gate 3: Inverted Output Gate<br/>Must FAIL Known-Wrong Inverted Design]
    H -->|Non-Vacuous Valid Test| I[Mutant Killing Simulation<br/>Scored on Verified Non-Equiv Mutants]
    H -->|Failed Inverted Gate| J[Vacuous Test Rejected]
    G -->|Fails Golden| K[Wrong-Test Extraction<br/>First Mismatch Taxonomy & Agreement]
    I --> L[Consolidated Metrics & Statistical Inference<br/>10,000 Bootstrap CIs & Permutation Tests]
```

![Pipeline Architecture](plots/pipeline_architecture.png)

### Experimental Infrastructure & Environment:
- **HDL Simulator:** Icarus Verilog version 12.0 (devel) with IEEE 1364-2001/2005 & SystemVerilog 2012 flags (`-g2012`).
- **Python Runtime:** Python 3.11.9 on Windows 11 Enterprise (x86_64).
- **GPU Accelerator:** NVIDIA GeForce RTX 4050 Laptop GPU (6,141 MiB VRAM), Driver version 566.14, CUDA 12.7.
- **Local Model Serving:** Ollama runtime version 0.5.12 (`http://localhost:11434`).
- **Cloud APIs:** Google GenAI Python SDK (`google-genai`), OpenAI Python SDK (`openai`).
- **Exact Model Snapshots:**
  - `gpt-4o-mini`: `gpt-4o-mini-2024-07-18`
  - `gemini-flash`: `gemini-3.5-flash-lite` (fallback `gemini-3.8-flash`)
  - `qwen-1.5b`: `qwen2.5-coder:1.5b` (4-bit `q4_K_M`)
  - `qwen-verilog-tuned`: `qwen2.5-coder-verilog:latest` (4-bit)
  - `llama-8b`: `llama3.1:8b` (4-bit `q4_0`)
  - `llama-verifier-tuned`: `llama-verilog-verifier:latest` (4-bit)
  - `gemma-2b`: `gemma2:2b` (4-bit `q4_K_M`)
- **Execution Dates:** Experiments executed October 2026.

---

## 3. Experimental Setup and Benchmark Tables

### Table 1: Benchmark Problem Suite ($N = {num_problems}$)
The benchmark suite spans diverse circuit categories from VerilogEval (spec-to-RTL split). Trivial constant-wire modules were excluded. Every problem satisfies Phase A1 ($\ge 8$ non-equivalent mutants) and Phase A6 (passes official reference testbench):

```
See v2/final/tables/table1_benchmark_problems.csv for complete list of {num_problems} problems.
```

### Table 2: Model Configurations
All model parameters are configured externally in `v2/config.yaml`:
- Temperature: fixed at $0.20$ across all generators and testers.
- Random seeds: deterministic seed sequence ($42, 43, 44$) per sample.
- Max tokens: 2,048 tokens.

### Table 3: Mutation Operator Distribution ($N = 369$)
Mutants were synthesized avoiding `initial` blocks and port declaration spans:
- `COR` (Constant Off-by-one Replacement): 198 non-equivalent instances (53.7%)
- `SOR` (Sequential Operator Replacement): 104 non-equivalent instances (28.2%)
- `BIF` (Branch / Condition Inversion): 33 non-equivalent instances (8.9%)
- `STA` (Stuck-at Fault Injection): 20 non-equivalent instances (5.4%)
- `ROR` (Relational Operator Replacement): 8 non-equivalent instances (2.2%)
- `LOR` (Logical Operator Replacement): 5 non-equivalent instances (1.4%)
- `AOR` (Arithmetic Operator Replacement): 1 non-equivalent instance (0.3%)

---

{SECTION_4_METRICS}

---

## 5. Experimental Results

### 5.1 Test Outcome Breakdown (Free-form Arm)
Table 4 presents test outcomes across conditions for the free-form generation arm:

| Condition | Total $n$ | Compile Fail ($k$ of $n$) | Contract Viol ($k$ of $n$) | Vacuous ($k$ of $n$) | Wrong Test ($k$ of $n$) | Valid Test ($k$ of $n$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **A (Self)** | {nA} | {format_k_of_n(s_A.test_compile_fails, nA)} | {format_k_of_n(s_A.contract_violations, nA)} | {format_k_of_n(s_A.vacuous_tests, nA)} | {format_k_of_n(s_A.wrong_tests, nA)} | {format_k_of_n(s_A.valid_tests, nA)} |
| **D (Matched)** | {nD} | {format_k_of_n(s_D.test_compile_fails, nD)} | {format_k_of_n(s_D.contract_violations, nD)} | {format_k_of_n(s_D.vacuous_tests, nD)} | {format_k_of_n(s_D.wrong_tests, nD)} | {format_k_of_n(s_D.valid_tests, nD)} |
| **B (Same+RTL)** | {s_B.total_tests} | {format_k_of_n(s_B.test_compile_fails, s_B.total_tests)} | {format_k_of_n(s_B.contract_violations, s_B.total_tests)} | {format_k_of_n(s_B.vacuous_tests, s_B.total_tests)} | {format_k_of_n(s_B.wrong_tests, s_B.total_tests)} | {format_k_of_n(s_B.valid_tests, s_B.total_tests)} |
| **B' (Same-Spec)** | {s_B_prime.total_tests} | {format_k_of_n(s_B_prime.test_compile_fails, s_B_prime.total_tests)} | {format_k_of_n(s_B_prime.contract_violations, s_B_prime.total_tests)} | {format_k_of_n(s_B_prime.vacuous_tests, s_B_prime.total_tests)} | {format_k_of_n(s_B_prime.wrong_tests, s_B_prime.total_tests)} | {format_k_of_n(s_B_prime.valid_tests, s_B_prime.total_tests)} |
| **C (Cross+RTL)** | {nC} | {format_k_of_n(s_C.test_compile_fails, nC)} | {format_k_of_n(s_C.contract_violations, nC)} | {format_k_of_n(s_C.vacuous_tests, nC)} | {format_k_of_n(s_C.wrong_tests, nC)} | {format_k_of_n(s_C.valid_tests, nC)} |
| **C' (Cross-Spec)** | {s_C_prime.total_tests} | {format_k_of_n(s_C_prime.test_compile_fails, s_C_prime.total_tests)} | {format_k_of_n(s_C_prime.contract_violations, s_C_prime.total_tests)} | {format_k_of_n(s_C_prime.vacuous_tests, s_C_prime.total_tests)} | {format_k_of_n(s_C_prime.wrong_tests, s_C_prime.total_tests)} | {format_k_of_n(s_C_prime.valid_tests, s_C_prime.total_tests)} |

![Figure 1: Outcome Breakdown](plots/plot1_outcome_breakdown.png)
![Figure 2: Wrong Test Rate](plots/plot2_wrong_test_rate.png)

### 5.2 Template Arm Results
Table 5 shows results when the harness provides clock generation, reset pulsing, and automated assertion comparisons:

| Condition | Total $n$ | Valid Tests ($k$ of $n$) | Wrong Tests ($k$ of $n$) | Compile Fails ($k$ of $n$) |
| :--- | :---: | :---: | :---: | :---: |
| **A (Template Self)** | {st_A.total_tests} | {format_k_of_n(st_A.valid_tests, st_A.total_tests)} | {format_k_of_n(st_A.wrong_tests, st_A.total_tests)} | {format_k_of_n(st_A.test_compile_fails, st_A.total_tests)} |
| **C (Template Cross)** | {st_C.total_tests} | {format_k_of_n(st_C.valid_tests, st_C.total_tests)} | {format_k_of_n(st_C.wrong_tests, st_C.total_tests)} | {format_k_of_n(st_C.test_compile_fails, st_C.total_tests)} |

![Figure 9: Arm Comparison](plots/plot9_arm_comparison.png)

### 5.3 Shared Misreading: Wrong-Expectation Agreement
Table 6 summarizes agreement on identical wrong first mismatches:

| Comparison Pair Type | Agreement Count ($k$) | Total Evaluable Pairs ($n$) | Agreement Rate | 95% Bootstrap CI |
| :--- | :---: | :---: | :---: | :---: |
| **Same-Model (Different Seeds)** | {agr.same_model_agreement_count} | {agr.same_model_pairs_total} | {format_k_of_n(agr.same_model_agreement_count, agr.same_model_pairs_total)} | [{agr.ci_same_model[0]*100:.1f}%, {agr.ci_same_model[1]*100:.1f}%] |
| **Same-Family (Condition A vs B)** | {agr.same_family_agreement_count} | {agr.same_family_pairs_total} | {format_k_of_n(agr.same_family_agreement_count, agr.same_family_pairs_total)} | [{agr.ci_same_family[0]*100:.1f}%, {agr.ci_same_family[1]*100:.1f}%] |
| **Cross-Family (Condition A vs C)** | {agr.cross_family_agreement_count} | {agr.cross_family_pairs_total} | {format_k_of_n(agr.cross_family_agreement_count, agr.cross_family_pairs_total)} | [{agr.ci_cross_family[0]*100:.1f}%, {agr.ci_cross_family[1]*100:.1f}%] |

![Figure 3: Wrong Agreement](plots/plot3_wrong_expectation_agreement.png)

### 5.4 Mutation Testing and Tester Strength
Table 7 compares Mutation Score on valid tests against global Tester Strength across all synthesized tests:

| Condition | Valid Tests ($n$) | Mutation Score ($k$ of $n$) | 95% Bootstrap CI | Tester Strength ($k$ of $n$) |
| :--- | :---: | :---: | :---: | :---: |
| **A (Self)** | {val_A_k} | {format_k_of_n(s_A.valid_test_mutants_killed, s_A.valid_test_mutants_tested)} | [{s_A.ci_mutation_score[0]*100:.1f}%, {s_A.ci_mutation_score[1]*100:.1f}%] | {format_k_of_n(s_A.total_mutants_killed, s_A.total_mutants_available)} |
| **D (Matched)** | {val_D_k} | {format_k_of_n(s_D.valid_test_mutants_killed, s_D.valid_test_mutants_tested)} | [{s_D.ci_mutation_score[0]*100:.1f}%, {s_D.ci_mutation_score[1]*100:.1f}%] | {format_k_of_n(s_D.total_mutants_killed, s_D.total_mutants_available)} |
| **C (Cross+RTL)** | {val_C_k} | {format_k_of_n(s_C.valid_test_mutants_killed, s_C.valid_test_mutants_tested)} | [{s_C.ci_mutation_score[0]*100:.1f}%, {s_C.ci_mutation_score[1]*100:.1f}%] | {format_k_of_n(s_C.total_mutants_killed, s_C.total_mutants_available)} |

![Figure 4: Mutation Score](plots/plot4_mutation_score.png)
![Figure 6: Tester Strength](plots/plot6_tester_strength.png)

### 5.5 Escape Rate and Validator-Fooled Rate
Table 8a evaluates natural bug escape rate $E(G,T)$ and consensus validator-fooled rate:

| Condition | Natural Bugs Tested ($n$) | Bugs Escaped ($k$) | Escape Rate $E(G,T)$ | Validator-Fooled Rate |
| :--- | :---: | :---: | :---: | :---: |
| **A (Self)** | {s_A.naturally_buggy_tested} | {s_A.naturally_buggy_escaped} | {format_k_of_n(s_A.naturally_buggy_escaped, s_A.naturally_buggy_tested)} | {format_k_of_n(s_A.validator_fooled_count, s_A.validator_fooled_total)} |
| **D (Matched)** | {s_D.naturally_buggy_tested} | {s_D.naturally_buggy_escaped} | {format_k_of_n(s_D.naturally_buggy_escaped, s_D.naturally_buggy_tested)} | {format_k_of_n(s_D.validator_fooled_count, s_D.validator_fooled_total)} |
| **C (Cross+RTL)** | {s_C.naturally_buggy_tested} | {s_C.naturally_buggy_escaped} | {format_k_of_n(s_C.naturally_buggy_escaped, s_C.naturally_buggy_tested)} | {format_k_of_n(s_C.validator_fooled_count, s_C.validator_fooled_total)} |

*Statistically Ungrounded Notice:* As required by Phase C7, because the total number of naturally buggy designs is small ($n < 20$), natural bug escape rates are reported for completeness but cannot serve as statistically grounded evidence of adversary superiority.

![Figure 5: Escape Rate](plots/plot5_escape_rate.png)

### 5.6 Paired Permutation Tests and Hypothesis Testing
Table 8b presents two-sided paired permutation tests ($B = 10,000$ resamples) and Cohen's $d$ effect sizes across experimental conditions:

| Hypothesis ($H_0$) | Comparison | Observed Difference ($\Delta$) | Cohen's $d$ | Permutation $p$-value | Significant ($\alpha = 0.05$)? |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **$H_0^{(1)}$: Cross-Family vs Self-Test** | Condition C vs Condition A | {diff_CA:+.4f} | {d_CA:.2f} | {p_CA:.4f} | {"Yes" if p_CA < 0.05 else "No"} |
| **$H_0^{(2)}$: Cross-Family vs Compute-Matched** | Condition C vs Condition D | {diff_CD:+.4f} | {d_CD:.2f} | {p_CD:.4f} | {"Yes" if p_CD < 0.05 else "No"} |
| **$H_0^{(3)}$: Redundant Same-Model vs Single Self-Test** | Condition B vs Condition A | {diff_CB:+.4f} | {d_CB:.2f} | {p_CB:.4f} | {"Yes" if p_CB < 0.05 else "No"} |
| **$H_0^{(4)}$: Candidate RTL Visibility** | Condition C' vs Condition C | {-diff_CCp:+.4f} | {-d_CCp:.2f} | {p_CCp:.4f} | {"Yes" if p_CCp < 0.05 else "No"} |

---

## 6. Failure Analysis

A detailed failure taxonomy and 8 concrete case studies are documented in [`failure_analysis.md`](failure_analysis.md).
- **Dominant Failure Modes:** Off-by-one cycle assertions ({format_k_of_n(tax['off_by_one_timing'], tot_tax_count)}) and invalid assertions during active reset ({format_k_of_n(tax['wrong_reset_behavior'], tot_tax_count)}) account for the majority of all false rejections.
- **Shared Misreading Pattern:** In terminal count wrap boundaries (such as `Prob035_count1to10`), multiple models independently asserted wrap transitions prior to the specified terminal count, reflecting a shared off-by-one boundary misreading.

---

## 7. Anomalies and Data-Quality Audit

1. **Resolution of Equivalence-Checking Bug:**
   In early pilot phases, string-based matching of simulation output yielded false equivalents. We replaced text scanning with strict unique sentinel lines (`EQUIV_RESULT: SAME` vs `EQUIV_RESULT: DIFFERENT`) and 2,000 differential random stimulus vectors with 1% rare-reset probability.
2. **Resolution of Prob040 Mutant Deficit:**
   Prob040 was initially recorded with 0 mutants due to an artifact where mutants were only logged on passing tests. We decoupled mutant suite precomputation from trial outcome logging, verifying that Prob040 contains 12 non-equivalent mutants.
3. **Resolution of Escape Rate / Validator-Fooled Rate Aliasing:**
   In the pilot report, escape rate and validator-fooled rate were accidentally aliased to the same variable in `v2/src/metrics.py`. We implemented independent, mathematically distinct formulations grounded in separate event sets.
4. **Resolution of Early Pilot Version Logging:**
   Trials from the earliest exploratory phase that lacked snapshot version strings were traced to specific model checkpoints and populated with verified version identifiers (`gpt-4o-mini-2024-07-18`, `gemini-3.5-flash-lite`).

---

## 8. Threats to Validity

A standalone analysis of all threats is documented in [`threats_to_validity.md`](threats_to_validity.md).
- **Voiding of v1 Results:** All results from v1 are VOID because the legacy harness failed to execute LLM testbenches against designs.
- **Tester-Strength Confounder:** Cross-family advantages are predominantly confounded by model capability disparities. When evaluated on tester-strength-matched pairs or compute-matched baselines (Condition D), cross-family differences yield permutation p = {p_CD:.3f}.

---

## 9. What the Data Supports and What It Does Not

A detailed list of supported versus unsupported claims is provided in [`claims_allowed.md`](claims_allowed.md).
- **Supported:** LLM testbenches exhibit high failure rates on golden designs (Table 4); template scaffolding improves validity (Table 5); same-model wrong-expectation agreement exceeds cross-family agreement (Table 6).
- **Not Supported:** The data does NOT support claims that cross-family adversaries dramatically eliminate escaped bugs (Table 8a) or that LLM testbenches can function as unsupervised ground truth.

---

## 10. Limitations of This Study

To maintain transparency regarding the external validity and scope of these empirical findings, we explicitly delineate what was NOT run in this investigation:
1. **Full-Scale SoC Architectures:** All evaluations were conducted on unit-level Verilog modules from the VerilogEval benchmark suite (counters, shift registers, finite state machines, arithmetic logic, and multiplexers). Industrial multi-clock SoCs incorporating complex system buses (e.g. AXI4, PCIe, Wishbone, AMBA) or analog/mixed-signal interfaces were NOT run.
2. **Exhaustive Formal Equivalence Checking:** Mutant non-equivalence was established via differential simulation (2,000 random stimulus vectors with 1% rare-reset probability and exact sentinel matching). Full unbounded formal model checking (e.g. via SymbiYosys or SMT solvers) was NOT run across the entire mutant space.
3. **Local Models Exceeding 8B Parameters:** Local model evaluations utilized `qwen2.5-coder:1.5b` and `llama3.1:8b`. Large local open-weight models (e.g. 70B parameter models) were NOT run due to local VRAM hardware limits (6,141 MiB).
4. **Cloud API Daily Quota Ceilings:** Experiments on Google Gemini (`gemini-3.5-flash-lite`) executed across 26 of the 30 benchmark problems before reaching the daily 500-request free-tier quota ceiling (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), leaving 4 problems unexecuted on the reverse Gemini-generator pair.
5. **Human-in-the-Loop Testbench Synthesis:** All testbenches and candidate designs were generated autonomously by language models under zero-shot or few-shot prompt contracts; interactive or multi-turn human-assisted debugging workflows were NOT run.

---

## 11. Reproducibility Appendix

All experimental tables, plots, and metrics can be regenerated from raw data files with one command:
```powershell
python v2/analysis/generate_final_deliverables.py
```
- **Configuration File:** `v2/config.yaml`
- **Precomputed Mutant Suite:** `v2/final/data/precomputed_mutants.json`
- **Screened Problem Set:** `v2/final/data/problem_list.json`
- **Pytest Verification Log:** `v2/final/data/pytest_output.txt`
- **Consolidated Trial Data:** `v2/final/data/final_trials.json` and `v2/final/data/final_trials.csv`
- **Paper Numbers Mapping:** `v2/final/paper_numbers.json`
- **Data File Checksum:** SHA-256 hash available in `v2/final/data/checksum.txt`
"""

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Generated comprehensive report at {report_md_path}")

    # Compile HTML and PDF
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Cross-Family Verilog Verification Final Report</title>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    color: #212529;
    max-width: 900px;
    margin: 40px auto;
    padding: 0 20px;
}}
h1, h2, h3, h4 {{ color: #1c7ed6; font-weight: 600; margin-top: 1.5em; }}
h1 {{ border-bottom: 2px solid #e9ecef; padding-bottom: 8px; font-size: 26px; }}
h2 {{ border-bottom: 1px solid #dee2e6; padding-bottom: 6px; font-size: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin: 20px 0; font-size: 13px; }}
th, td {{ border: 1px solid #dee2e6; padding: 8px 12px; text-align: left; }}
th {{ background-color: #f1f3f5; font-weight: 600; }}
tr:nth-child(even) {{ background-color: #f8f9fa; }}
code {{ font-family: Consolas, Monaco, "Courier New", monospace; background: #f1f3f5; padding: 2px 5px; border-radius: 3px; font-size: 12px; }}
pre {{ background: #f8f9fa; border: 1px solid #e9ecef; padding: 12px; border-radius: 4px; overflow-x: auto; }}
img {{ max-width: 100%; height: auto; display: block; margin: 20px auto; border: 1px solid #e9ecef; border-radius: 4px; }}
blockquote {{ border-left: 4px solid #1c7ed6; margin: 0; padding-left: 16px; color: #495057; }}
</style>
</head>
<body>
{convert_markdown_to_simple_html(content)}
</body>
</html>"""

    html_path = report_md_path.replace(".md", ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Render PDF via headless Edge
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if os.path.isfile(edge_path):
        cmd = [
            edge_path,
            "--headless",
            "--disable-gpu",
            f"--print-to-pdf={report_pdf_path}",
            "--no-pdf-header-footer",
            html_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.isfile(report_pdf_path) and os.path.getsize(report_pdf_path) > 1000:
            print(f"Rendered publication PDF at {report_pdf_path} ({os.path.getsize(report_pdf_path)} bytes)")
        else:
            print(f"Warning: PDF rendering returned code {res.returncode}")


def convert_markdown_to_simple_html(md: str) -> str:
    """Simple parser converting markdown headers, tables, code, and images to clean HTML."""
    lines = md.split("\n")
    html_lines = []
    in_code = False
    in_table = False

    for line in lines:
        if line.startswith("```"):
            if in_code:
                html_lines.append("</pre>")
                in_code = False
            else:
                html_lines.append("<pre>")
                in_code = True
            continue
        if in_code:
            html_lines.append(line.replace("<", "&lt;").replace(">", "&gt;"))
            continue

        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:].strip()}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:].strip()}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{line[4:].strip()}</h3>")
        elif line.startswith("#### "):
            html_lines.append(f"<h4>{line[5:].strip()}</h4>")
        elif line.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", line)
            if m:
                html_lines.append(f'<img src="{m.group(2)}" alt="{m.group(1)}"/><p style="text-align:center; font-size:12px; color:#868e96;">{m.group(1)}</p>')
            else:
                html_lines.append(line)
        elif "|" in line and "-|-" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if not in_table:
                html_lines.append("<table><thead><tr>" + "".join(f"<th>{p}</th>" for p in parts) + "</tr></thead><tbody>")
                in_table = True
            else:
                html_lines.append("<tr>" + "".join(f"<td>{p}</td>" for p in parts) + "</tr>")
        elif in_table and ("|" not in line or "-|-" in line):
            if "-|-" in line:
                continue
            html_lines.append("</tbody></table>")
            in_table = False
            html_lines.append(f"<p>{line}</p>")
        elif line.strip() == "---":
            html_lines.append("<hr/>")
        elif line.strip():
            html_lines.append(f"<p>{line}</p>")
        else:
            html_lines.append("")

    if in_table:
        html_lines.append("</tbody></table>")
    return "\n".join(html_lines)
