# LLM-Driven RTL Design and Verification Framework

Investigating whether an independent LLM-based verification agent can improve
the correctness of LLM-generated RTL through iterative, executable feedback.

## Architecture

```
Hardware Spec → Designer LLM → Generated RTL → Verifier LLM → Verification Env
     ↑                                                              │
     └──────────────── Feedback (failures, coverage) ←──────────────┘
```

**Designer Agent**: Generates Verilog/SystemVerilog RTL from natural-language specs.
Accepts verification failure feedback to produce corrected designs.

**Verifier Agent**: Independently generates testbenches, assertions, and stimulus
to challenge the Designer's RTL. Its goal is adversarial — find bugs.

**Verification Environment**: iverilog (behavioral sim) + Verilator (lint, coverage).
Provides objective, executable results that neither LLM determines.

## Quick Start

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Set up WSL2 verification tools
wsl bash scripts/setup_wsl.sh

# 3. Pull an LLM model via Ollama
ollama pull qwen2.5-coder:7b

# 4. Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# 5. Launch the web application
rtl-verify
```

## Project Structure

```
rtl_verify/
├── agents/          # Designer + Verifier LLM agents
├── pipeline/        # Iterative design-verify-feedback orchestration
├── verification/    # iverilog/Verilator wrappers, coverage, mutation testing
├── benchmarks/      # Hardware specification benchmarks (YAML)
├── metrics/         # Metrics collection, comparison, analysis
└── web/             # NiceGUI web application (EDA-like interface)
```

## Experimental Configurations

| Config | Description |
|--------|-------------|
| Baseline | Single LLM generates RTL, no verification loop |
| Self-verify | Single LLM generates RTL + testbench |
| Designer+Verifier | Separate Designer and Verifier agents (iterative) |
| Fine-tuned D+V | Fine-tuned Designer and Verifier (stretch goal) |

## License

Research project — not for redistribution.
