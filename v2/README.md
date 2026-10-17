# Cross-Family Verilog RTL Generation & Verification Pipeline (v2)

This directory contains the upgraded, rigorous research evaluation framework for studying **cross-family LLM verification** of generated Verilog RTL.

Unlike legacy synthetic benchmarks, this framework executes **real Verilog compilation and simulation** using **Icarus Verilog 12.0** (`-g2012`), without mocked behavioral engines, hardcoded tables, or synthetic coverage constants.

---

## Key Experimental Questions & Conditions

We evaluate whether testing LLM-generated hardware designs with a model from a **different architecture/training family** catches failure modes that same-model or same-family verification overlooks:

| Condition | Role | Generator ($G$) | Tester ($T$) | Tester Context | Compute Match |
|:---|:---|:---:|:---:|:---:|:---:|
| **A** | Self-Verification | Model $G$ | Model $G$ | Spec + Candidate RTL | $1\times$ |
| **B** | Same-Family Adversary | Model $G$ | Model $G'$ (same family) | Spec + Candidate RTL | $1\times$ |
| **B'** | Same-Family Spec-Only | Model $G$ | Model $G'$ (same family) | Spec only | $1\times$ |
| **C** | Cross-Family Adversary | Model $G$ | Model $T$ (different family) | Spec + Candidate RTL | $1\times$ |
| **C'** | Cross-Family Spec-Only | Model $G$ | Model $T$ (different family) | Spec only | $1\times$ |
| **D** | Compute-Matched Control | Model $G$ | Model $G$ | Spec + Candidate RTL | $2\times$ budget ($N$ test suites) |

---

## Architecture & Codebase Layout

```
d:\rtl-verification\v2\
├── config.yaml               # Central experiment configuration (models, simulator flags, seeds)
├── README.md                 # This documentation
├── src/
│   ├── verilog_sim.py        # Native Icarus Verilog execution & regex parsing (zero mocks)
│   ├── mutator.py            # 9 AST-informed mutation operators + equivalence filtering
│   ├── llm_client.py         # Unified client with SHA-256 disk caching & audit logs
│   ├── problems.py           # VerilogEval v2 dataset loader & combinational/sequential classification
│   ├── pipeline.py           # Experiment orchestrator (generation -> validity gate -> fault analysis)
│   ├── metrics.py            # False-rejection rate, mutation score, escape rate, bootstrap CIs
│   └── plots.py              # Publication-ready figures (PNG 300 DPI) & Markdown/LaTeX tables
├── golden/                   # Cached problem specifications, golden RTL, and testbenches
├── results/                  # Structured JSON, CSV, summary reports, and generated charts
├── logs/                     # Full JSON transcripts of every LLM call (prompts, raw outputs, tokens)
├── cache/                    # Content-addressed disk cache for reproducible, deterministic execution
├── scripts/
│   ├── run_pilot.py          # Runs the 20-problem pilot study with incremental checkpoints
│   └── run_full.py           # Scaled runner for the complete benchmark suite
└── tests/                    # Comprehensive unit tests for simulator, mutator, client, and metrics
```

---

## Verification & Validity Guarantees

1. **Native Verilog Simulation:**
   - Every candidate design and testbench is compiled with `iverilog -g2012` and run via `vvp`.
   - Timeout protection ensures runaway simulations are terminated.
2. **Validity Gate:**
   - Every generated testbench is first evaluated against the verified golden design (`RefModule`).
   - If the golden design fails, the testbench is rejected as invalid (preventing false alarms). The False-Rejection Rate (FRR) is recorded as a quality metric.
3. **Equivalence-Filtered Mutation Testing:**
   - Mutants are generated across 9 operators: AOR, ROR, LOR, BIF, OFF, RST, STA, SWP, FSM.
   - Every mutant is compiled. Uncompilable mutants are excluded from the test set.
   - Mutants that pass the golden testbench are flagged as likely equivalent and excluded from the denominator.
4. **Naturally Occurring Bugs:**
   - Candidate designs that fail the golden testbench are evaluated directly against candidate testbenches to measure true Bug Escape Rate $E(G, T)$.
5. **Compute-Matched Control (Condition D):**
   - Directly isolates model diversity from brute-force token budget by comparing cross-family verification against $N$ independent test suites from the self-model.
6. **Information Flow Variants (B' vs B, C' vs C):**
   - Directly isolates whether seeing the candidate RTL anchors or biases the verification agent.

---

## Running the Pipeline

### 1. Run Unit Tests
```powershell
d:\rtl-verification\.venv\Scripts\python.exe -m pytest d:\rtl-verification\v2\tests
```

### 2. Run Pilot Dry Run (1 problem sanity test)
```powershell
d:\rtl-verification\.venv\Scripts\python.exe d:\rtl-verification\v2\scripts\run_pilot.py --dry-run
```

### 3. Run Full 20-Problem Pilot Study
```powershell
d:\rtl-verification\.venv\Scripts\python.exe d:\rtl-verification\v2\scripts\run_pilot.py --count 20
```
