# Consolidated Cross-Family RTL Verification Report

## 1. Experiment Overview

- **Benchmarked Problems (n=5 Sequential):** Prob035_count1to10, Prob040_count10, Prob037_review2015_count1k, Prob067_countslow, Prob080_timer
- **Model Pairs Evaluated:** 4 pairs (Local Qwen, Local Llama, Cloud GPT, Cloud Gemini)
- **Conditions per Problem:** 6 (A: Self, B: Same+RTL, B': Same Spec-Only, C: Cross+RTL, C': Cross Spec-Only, D: Compute-Matched Self)
- **Total Trials:** 120
- **Total Elapsed Time:** 3330.9s
- **Methodological Controls Enforced:**
  1. Fixed contract enforcement (self-checking, single status line, $finish).
  2. Non-vacuity gate: valid testbenches must FAIL on a dedicated inverted-output gate design.
  3. Candidate RTL generated once per (problem, generator) and reused across all conditions.
  4. 2000-vector differential equivalence checking with rare reset and exact sentinels.
  5. Minimum 8 non-equivalent mutants per problem.
  6. Contract rule 9 requiring 4-state case inequality (!==).

## 2. Consolidated Results Across All 4 Pairs

| Condition | Trials (n) | Valid Test Rate | Test Compile Fail | Contract Violation | Vacuous Tests | RTL Compile Fail | Escape Rate E(G,T) | Tester Strength | Validator Fooled | 4-State !== Adherence | Avg Runtime (s) | Total Tokens |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **A** | 20 | 20.0% | 25.0% | 0.0% | 0.0% | 5.0% | 100.0% | 94.3% | 100.0% | 75.0% | 17.12s | 62,015 |
| **B** | 20 | 5.0% | 40.0% | 0.0% | 0.0% | 5.0% | 0.0% | 100.0% | 0.0% | 60.0% | 27.04s | 67,735 |
| **B_prime** | 20 | 15.0% | 30.0% | 10.0% | 0.0% | 5.0% | 0.0% | 100.0% | 0.0% | 60.0% | 17.42s | 57,167 |
| **C** | 20 | 15.0% | 35.0% | 10.0% | 10.0% | 5.0% | 100.0% | 100.0% | 100.0% | 55.0% | 47.50s | 69,436 |
| **C_prime** | 20 | 15.0% | 20.0% | 15.0% | 0.0% | 5.0% | 0.0% | 100.0% | 0.0% | 65.0% | 13.95s | 45,301 |
| **D** | 20 | 15.0% | 35.0% | 0.0% | 0.0% | 5.0% | 100.0% | 88.9% | 100.0% | 75.0% | 34.14s | 66,024 |

## 3. Results by Model Pair

### 3.1 Pair 1: Local Qwen
- **Configuration:** G: qwen2.5-coder:1.5b | G': qwen2.5-coder-verilog | T: llama3.1:8b

| Condition | Trials (n) | Valid Test Rate | Test Compile Fail | Contract Violation | Vacuous Tests | RTL Compile Fail | Escape Rate E(G,T) | Tester Strength | Validator Fooled | 4-State !== Adherence | Avg Runtime (s) | Total Tokens |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **A** | 5 | 0.0% | 100.0% | 0.0% | 0.0% | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 28.61s | 34,457 |
| **B** | 5 | 0.0% | 80.0% | 0.0% | 0.0% | 20.0% | 0.0% | 0.0% | 0.0% | 20.0% | 25.77s | 27,797 |
| **B_prime** | 5 | 0.0% | 80.0% | 20.0% | 0.0% | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 21.47s | 25,493 |
| **C** | 5 | 0.0% | 40.0% | 40.0% | 40.0% | 20.0% | 0.0% | 0.0% | 0.0% | 20.0% | 147.97s | 27,061 |
| **C_prime** | 5 | 0.0% | 20.0% | 20.0% | 0.0% | 20.0% | 0.0% | 0.0% | 0.0% | 60.0% | 42.23s | 15,706 |
| **D** | 5 | 0.0% | 100.0% | 0.0% | 0.0% | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 31.00s | 33,088 |

### 3.2 Pair 2: Local Llama
- **Configuration:** G: llama3.1:8b | G': llama-verilog-verifier | T: qwen2.5-coder:1.5b

| Condition | Trials (n) | Valid Test Rate | Test Compile Fail | Contract Violation | Vacuous Tests | RTL Compile Fail | Escape Rate E(G,T) | Tester Strength | Validator Fooled | 4-State !== Adherence | Avg Runtime (s) | Total Tokens |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **A** | 5 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 28.65s | 8,963 |
| **B** | 5 | 0.0% | 80.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 20.0% | 71.23s | 20,343 |
| **B_prime** | 5 | 0.0% | 40.0% | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 40.0% | 36.92s | 13,910 |
| **C** | 5 | 0.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 29.09s | 23,329 |
| **C_prime** | 5 | 0.0% | 60.0% | 40.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 9.16s | 11,831 |
| **D** | 5 | 0.0% | 40.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 94.51s | 14,384 |

### 3.3 Pair 3: Cloud GPT
- **Configuration:** G: gpt-4o-mini | G': gpt-4o-mini | T: gemini-3.5-flash-lite

| Condition | Trials (n) | Valid Test Rate | Test Compile Fail | Contract Violation | Vacuous Tests | RTL Compile Fail | Escape Rate E(G,T) | Tester Strength | Validator Fooled | 4-State !== Adherence | Avg Runtime (s) | Total Tokens |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **A** | 5 | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 84.6% | 100.0% | 100.0% | 6.15s | 8,422 |
| **B** | 5 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 6.37s | 9,124 |
| **B_prime** | 5 | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 100.0% | 10.71s | 8,261 |
| **C** | 5 | 60.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 100.0% | 100.0% | 4.33s | 9,683 |
| **C_prime** | 5 | 40.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 100.0% | 4.07s | 9,455 |
| **D** | 5 | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 84.6% | 100.0% | 100.0% | 6.32s | 8,599 |

### 3.4 Pair 4: Cloud Gemini
- **Configuration:** G: gemini-3.5-flash-lite | G': gemini-3.5-flash-lite | T: gpt-4o-mini

| Condition | Trials (n) | Valid Test Rate | Test Compile Fail | Contract Violation | Vacuous Tests | RTL Compile Fail | Escape Rate E(G,T) | Tester Strength | Validator Fooled | 4-State !== Adherence | Avg Runtime (s) | Total Tokens |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **A** | 5 | 60.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 97.5% | 0.0% | 100.0% | 5.07s | 10,173 |
| **B** | 5 | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 100.0% | 4.79s | 10,471 |
| **B_prime** | 5 | 40.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 100.0% | 0.57s | 9,503 |
| **C** | 5 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 8.59s | 9,363 |
| **C_prime** | 5 | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% | 100.0% | 0.33s | 8,309 |
| **D** | 5 | 40.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 91.3% | 0.0% | 100.0% | 4.72s | 9,953 |

## 4. Anomalies and Verification Audit

- **Vacuous Testbenches Caught by Non-Vacuity Gate:** 2 of 120 trials.
- **4-State Inequality (!==) Violations:** 42 of 120 testbenches used '!=' instead of '!=='.
- **Candidate RTL Compilation Failures:** 6 of 120 trials. (RTL compile status was 100% invariant across conditions due to single-generation reuse).
- **Golden Mutants Evaluated:** 216 total mutant trials; 209 killed by valid testbenches.

> **NOTE ON PILOT SCOPE:** With n=5 problems per cell, this report presents empirical verification numbers and accounting audit only. No scientific effect claims are made.