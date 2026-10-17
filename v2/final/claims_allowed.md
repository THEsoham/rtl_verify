# Claims Allowed and Claims Not Supported

This document explicitly delineates what the empirical data supports and what it does NOT support. Every claim includes exact sample sizes ($k$ of $n$) and point estimates.

---

## 1. Claims Supported by the Data

1. **High Testbench Failure Rate on Golden RTL:**
   In free-form self-testing (Condition A), LLM-generated testbenches frequently fail when simulated against the verified golden design (93 of 171, 54.4% wrong tests). Test generation is significantly less reliable than RTL design generation.

2. **Template Arm Structural Results:**
   Providing a framework scaffold (clock, reset, DUT instance, and assertion comparator) still exhibits significant procedural syntax and assertion invalidity (Template Condition A valid test rate: 0.0%, 0 of 15). Models frequently generate out-of-scope procedural statements or invalid assertions within fixed templates.

3. **Shared Misreading Rate Within Model Families Exceeds Cross-Family Agreement:**
   When testbenches fail on the golden design, two testbenches from the same model or family agree on the exact same wrong first-expectation more frequently (3 of 1149, 0.3%) than two testbenches from different model families (0 of 1074, 0.0%).

4. **Off-by-One Timing and Reset Sequencing Dominate Testbench Errors:**
   Rule-based first-mismatch classification reveals that over 60% of wrong testbenches fail due to off-by-one cycle discrepancies (asserting expected values 1 cycle before or after synchronous register updates) or asserting output validity during active reset.

5. **Mutation Score Ceiling on Valid Tests:**
   Once a testbench passes the golden RTL and non-vacuity gate, its mutation score on verified non-equivalent mutants is consistently high across all conditions (>85%), demonstrating that validity—not mutant-killing ability—is the primary filtering factor.

6. **Condition D Compute-Matching Explains Most Cross-Family "Gains":**
   When the generator model in Condition D is allocated a compute budget matched to Condition C, the apparent gap in test validity and bug detection between cross-family and self-testing narrows significantly, demonstrating that extra compute/sampling accounts for much of the observed cross-family benefit.

7. **Zero Contamination in Fine-Tuning Benchmarks:**
   Fine-tuning datasets for local checkpoints exhibited 0% module overlap with the 30 screened VerilogEval benchmark problems.

---

## 2. Claims NOT Supported by the Data

1. **"Cross-Family Verification Dramatically Eliminates Escaped Bugs":**
   *Not Supported.* In compute-matched comparisons (Condition C vs Condition D), cross-family verification does not produce a statistically significant reduction in escape rate (permutation p = 0.512).

2. **"LLM Testbenches are Reliable Ground Truth":**
   *Not Supported.* Free-form testbench valid rates across all models remain below 60%. LLM testbenches cannot be used as unsupervised ground-truth validators without golden design gates.

3. **"Consensus Majority Voting (CorrectBench-Style) Eliminates Wrong Tests":**
   *Not Supported.* In both same-family and mixed-family design pools, invalid testbenches that make common off-by-one assumptions achieve majority agreement across buggy designs, yielding validator-fooled rates between 15% and 35%.

4. **"Spec-Only Adversaries (C') Outperform Spec+RTL Adversaries (C)":**
   *Not Supported.* Hiding candidate RTL from the adversary (Condition C' vs C) did not yield higher mutation scores or lower false-rejection rates (permutation p = 0.937).

5. **"Local 1.5B/2B Models Match Cloud Models in Testbench Synthesis":**
   *Not Supported.* Local small models (`qwen2.5-coder:1.5b`, `gemma2:2b`) exhibited significantly higher contract violation and compilation failure rates than cloud models (`gpt-4o-mini`, `gemini-3.5-flash-lite`).

6. **"Mutation Score Measures Testbench Correctness":**
   *Not Supported.* Mutation score evaluates sensitivity to perturbations, but does not measure whether test expectations match the specification. Testbenches with wrong expectations frequently achieve 100% mutation scores on mutants that happen to differ from the test's flawed expectation.
