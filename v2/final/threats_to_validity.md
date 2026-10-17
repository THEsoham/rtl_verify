# Threats to Validity: Cross-Family Verilog Verification Study

This document details the internal, construct, and external threats to validity for the empirical study on cross-family LLM RTL verification ($N = 1112$ trials evaluated across 30 benchmark problems, 6 conditions, and 2 experimental arms).

---

## 1. Internal Validity

### 1.1 Training Data Contamination
- **Risk:** Fine-tuned local checkpoints (`qwen2.5-coder-verilog`, `llama-verilog-verifier`) or base pre-trained models might have memorized benchmark problems from VerilogEval (derived from HDLBits).
- **Audit & Mitigation:** We inspected the fine-tuning training datasets (`training/dataset/verilog_train.json` containing 8 modules, and `verilog_verifier_train.json` containing 4 modules). None of the 12 training targets overlap with the 30 screened VerilogEval benchmark problems. Pre-trained weights from cloud providers (OpenAI, Google) remain closed; however, high failure rates on golden testbenches (40–70% across conditions) indicate that benchmark testbench memorization did not occur.

### 1.2 Mutant Equivalence and Triviality
- **Risk:** Synthetically generated mutants may be semantically equivalent to the golden specification, artificially deflating mutation scores, or trivial syntax mutations that compile-fail.
- **Audit & Mitigation:** We enforced Phase A1 and A7: every candidate mutant underwent 2,000-vector differential simulation against golden RTL with rare-reset sequences (1% reset probability) and exact sentinel output verification (`EQUIV_RESULT: SAME` vs `EQUIV_RESULT: DIFFERENT`). Problems with fewer than 8 non-equivalent mutants were rejected. Verified non-equivalent mutants were admitted into the scoring suites with zero equivalent mutants admitted.

### 1.3 Non-Vacuous Testbench Gate
- **Risk:** LLM-generated testbenches may emit unconditional `$display("*** TEST RESULT: PASS ***");` without actually asserting DUT outputs, producing false-positive valid tests.
- **Audit & Mitigation:** Every candidate testbench was evaluated against a dedicated inverted-output gate module (`build_inverted_gate`) that inverts all output ports of the golden RTL. Any testbench that reported PASS on the inverted design was flagged as vacuous and rejected (`valid=False`).

### 1.4 Cache Determinism and Timing Confounders
- **Risk:** Disk-cached LLM responses could mask runtime variability or create false impressions of execution speed.
- **Audit & Mitigation:** All cache hits are tracked with explicit boolean flags (`cached=True`). In reporting runtime metrics, cached executions are excluded from throughput and latency benchmarks.

---

## 2. Construct Validity

### 2.1 Selection Effect of Valid Tests (Survival Bias)
- **Risk:** Mutation scores and escape rates are computed exclusively on *valid* testbenches (those that pass compilation, satisfy contract requirements, pass golden RTL, and fail the non-vacuity gate). If a condition produces very few valid tests, its mutation score reflects only an extreme tail of conservative testbenches.
- **Audit & Mitigation:** We report test outcome breakdowns alongside every mutation score. We present both valid-test mutation score ($MS$) and global tester strength ($TS = \text{kills} / \text{available mutants}$) across all tests to expose survival bias.

### 2.2 Mutation Score Ceiling Effects
- **Risk:** Standard AST mutations (arithmetic, relational, bit-flip, stuck-at) may be easily killed by any testbench that provides minimal clock cycles, creating a ceiling effect that obscures differences between test generation strategies.
- **Audit & Mitigation:** We introduced harder mutation operators (off-by-one counter wrap boundaries, wrong reset priority, and FSM illegal transition redirections). Nevertheless, high mutation scores among valid tests indicate that testbench validity—not mutant-killing power—is the primary bottleneck in LLM verification.

### 2.3 Tester-Strength Confounder
- **Risk:** If Model $T$ is inherently stronger than Model $G$ at Verilog coding, Condition C (Cross-Family $T$ testing $G$) may outperform Condition A (Self-Test $G$ testing $G$) simply because $T$ writes better code, not because cross-family diversity mitigates shared cognitive bias.
- **Audit & Mitigation:** We evaluated bidirectional model pairs ($G_1 \to T_2$ and $G_2 \to T_1$), compute-matched self-testing (Condition D), and conducted paired comparisons matched by tester strength.

### 2.4 Testbench Contract and 4-State Comparison
- **Risk:** Standard Verilog equality (`==` or `!=`) treats floating unknown states (`'x'` or `'z'`) as indeterminate, which in `if` statements evaluates to false, causing tests to pass erroneously.
- **Audit & Mitigation:** We mandated 4-state case inequality (`!==`) in all prompt contracts and verified that testbenches use strict 4-state matching.

---

## 3. External Validity

### 3.1 Problem Set Scope
- **Risk:** Findings on unit-level benchmark modules (counters, shift registers, FSMs, arithmetic, combinational) may not generalize to large industrial SoCs with complex AXI/PCIe bus protocols.
- **Context:** The benchmark focuses on unit-level module verification where spec-to-RTL translation is cleanly bounded.

### 3.2 Natural Bug Pool Size
- **Risk:** High design pass rates on simple modules mean relatively few candidate designs contain natural bugs, yielding small sample sizes ($n < 20$) for natural bug escape rate $E(G,T)$.
- **Audit & Mitigation:** As mandated by Phase C7, whenever $n < 20$, we report $E(G,T)$ with explicit $k$ of $n$ warnings and refrain from drawing sweeping conclusions regarding natural bug escape.

### 3.3 Voiding of Legacy v1 Results
- **Explicit Statement:** All results and numbers from the earlier v1 pilot pipeline are VOID and were completely discarded because the legacy simulator harness failed to execute LLM-generated testbenches against designs. No v1 data is used in this report.
