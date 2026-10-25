# Audit of `main_new.tex` against the code and data

Input: `main_original.tex` (the uploaded draft), `v2/final/data/final_trials.csv`
(identical in content to `final/data/final_trials.csv` in the uploaded `v2.zip`), the
pipeline source in `v2/src/`, and the VerilogEval golden files in `v2/golden/`.

Every number in the revised `main.tex` is produced by `paper/audit/analysis.py`
(output: `paper/audit/paper_numbers_audited.json`).

```
python paper/audit/analysis.py --verilator paper/audit/resim_both.csv
```

## 1. What was re-run

| Check | Result |
|---|---|
| Golden RTL vs. official VerilogEval testbench (30 problems, Icarus 12.0) | 30/30 pass with 0 mismatches |
| Re-simulate all 1,022 free-form testbenches on golden RTL + inverted mutant (Icarus 12.0, Linux) | **1,022/1,022 verdicts identical** to the archive (`audit/resim_icarus.csv`) |
| Re-simulate with Verilator 5.020 `--binary --timing` | see `audit/resim_both.csv` and Section RQ1 of the paper |
| Each testbench vs. the candidate RTL it was written for | `audit/anchor_results.csv` (new anchoring analysis) |
| Recompute every table/figure number from the CSV | point estimates, Wilson CIs, ICC (0.2665), design effect (9.81), chi-square (4.3566 on 1,022), model comparisons: **all reproduce**; bootstrap CIs differ by ≤0.5 pp (RNG implementation) |

## 2. Errors found in the draft (and fixed)

### Numbers
1. **Gate-1 denominator was 973; it should be 985.** The pipeline overwrites
   `test_contract_valid=False` for the 12 vacuous testbenches, but those testbenches
   compiled, met the contract, and *passed* the golden RTL. Conditional FR is
   596/985 = **60.51%**, not 61.25%. All "conditional" rows of Table I changed.
2. **Fig. 1 counts double-counted the vacuous testbenches.** Correct funnel:
   37 compile/contract failures → 985 pass Gate 1 → 596 FR, 389 pass golden →
   12 vacuous, **377 valid** (draft said 49 / 12 / 365).
3. "95.20% passed Gate 1" → **96.38%** (985/1,022).
4. Template arm: the 15 non-compile-failures *did* pass Gates 1 and 2 (they failed
   the vacuity gate); the draft said none passed Gate 1.
5. Simulation timeout was **30 s** (the `VerilogSimulator` default; the run scripts do
   not pass `timeout_sec`), not 15 s.
6. Manual inspection sample was **25** trials (64% agreement with the rule-based
   taxonomy), not 60.
7. The local-model trials are **qwen2.5-coder:1.5b (generator) + llama3.1:8b (tester)
   on Prob006 (18) and Prob021 (2)**, not Qwen on Prob035/Prob040. The draft named
   Qwen in one place and Llama-8b in another.

### Experimental design described incorrectly
8. **Condition D is not compute-matched.** `pipeline.py` runs D with exactly the same
   prompt and retry budget as A, using `seed+500` (mean tester tokens 1,811 vs 1,812).
   D is reframed as a test–retest replicate of A. That is useful: it measures sampling
   noise (D−A = −1.44 pp).
9. **Condition B is not a different same-family model.** For both cloud pairs
   `generator_prime == generator` in `config.yaml`, so B is the same checkpoint
   with an adversarial prompt.
10. **Seeds are not sent to the APIs.** `_call_openai` and `_call_gemini` ignore the
    seed; it only enters the cache key. The three "seeds" are independent samples.
11. **Local trials are mislabelled.** llama3.1:8b is the tester in *every* condition,
    including the "self-test" A and D. The 20 trials are kept for prevalence and
    excluded from the condition and model analyses (cloud corpus N = 1,002).
12. **Problem selection** was "first 30 of 35 problems with ≥8 non-equivalent
    mutants among the first 122 screened". It was not "trivial single-gate problems
    omitted". The filter biases the suite toward sequential circuits.
13. Model versions: 60 trials have no recorded version (the backfill in
    `consolidate_and_checksum.py` was not applied to the final CSV), and 11 Gemini
    calls were served by the fallback `gemini-3.8-flash`. Now disclosed.
14. **Verilator claim was false.** Verilator 5 supports `#` delays, `@(posedge)` and
    `initial` blocks with `--timing`. The audit ran all testbenches on Verilator 5.020.

### Interpretation
15. **RQ4 generator effect is a confound.** The "significant" −10.47 pp generator
    difference arises because the generator is also the tester in 4 of 6 conditions.
    Holding the tester fixed, the generator of the shown RTL changes FR by −0.6 pp
    and −1.5 pp (n.s.). The real effect is **tester identity**: GPT-4o-mini
    74.3% vs Gemini Flash-Lite 42.6%; GEE OR = 4.13 [2.50, 6.81]. This is now the
    headline finding.
16. **Spec defects:** Prob068 and Prob099 have real port-level contradictions.
    Prob088 (one-hot requested, binary used) is internal-only and cannot cause a
    false rejection by itself. The primary exclusion now uses the 2 port-level
    problems, with all 3 as a sensitivity row.
17. **Qualitative section claims that the data contradict:**
    - "Prob085 leaves shift direction unstated": the spec says *"Shift right (q[3]
      becomes zero, q[0] is shifted out)"*. Prob085 has one of the lowest FR rates
      (19.4%). Kept as a contrast with Prob060, which is genuinely under-specified.
    - "Equality operators produce false mismatches with X": all 596 FR testbenches
      use `!==`. In 52 FR logs the golden output was X at the failing check, which is
      checking before reset, not an operator problem.
    - Only 6/596 FR testbenches printed the contracted `MISMATCH` line, so the
      automated first-mismatch taxonomy (`claims_allowed.md` item 4, "over 60%
      off-by-one/reset") is not reliable and is not used.
18. "Clean 6" excluded Prob043, whose spec matches its reference. Now stated as a
    post hoc choice.
19. Abstract/conclusion overclaimed ("current LLMs cannot serve…"). Narrowed to the
    two evaluated models.

## 3. Related work: citation check

| Claim in draft | Verdict |
|---|---|
| AutoChip "uses LLMs ... to generate accompanying testbenches" (Intro) | **Wrong.** AutoChip uses provided testbenches and feeds compile/simulation results back ([arXiv 2311.04887](https://arxiv.org/abs/2311.04887)). Fixed. |
| AutoChip assumes the oracle is correct (Rel. Work) | Correct; the paragraph was out of order (the "However" sentence followed the CorrectBench sentence). Fixed. |
| AutoBench / CorrectBench generate TBs and evaluate against golden RTL and mutants; CorrectBench self-validates and self-corrects | Correct ([arXiv 2411.08510](https://arxiv.org/abs/2411.08510)). |
| Du et al. supports "LLM-synthesized verification harnesses ... presumed reliable oracles" | **Misattributed.** Du et al. is about multi-agent debate for reasoning and factuality. Now cited only for that. |
| "Proposals have suggested pairing GPT with Claude/Gemini to eliminate correlated blind spots" | **No citation given.** Replaced with Kim et al., *Correlated Errors in LLMs*, ICML 2025 ([PMLR v267](https://proceedings.mlr.press/v267/kim25e.html)), plus MAGE (DAC 2025, [arXiv 2412.07822](https://arxiv.org/abs/2412.07822)) as an LLM-testbench multi-agent system. |
| VerilogEval testbenches are "hand-crafted by human authors" | Softened to "fixed, benchmark-supplied testbenches against reference solutions". |
| AssertLLM (ASP-DAC 2025), Chip-Chat, RTLLM, Wilson, Pearson, Cameron & Miller, Efron | Fine. |

`references.bib` was not included in the upload, so a complete one is now in `paper/`.
Check it against your own entries before submission.

## 4. Claims that still stand
- 58.32% FR prevalence (596/1,022) and the cluster CI.
- No condition effect (χ² n.s.; all paired contrasts inside the D−A noise band).
- Sequential ≫ combinational; large per-problem heterogeneity (ICC 0.27).
- FR persists on the simplest combinational problems (12.3%).
