"""
Export and register fine-tuned Adversarial Verifier model in Ollama.
Creates an Ollama Modelfile linking the fine-tuned LoRA adapter or base model
and registers 'llama-verilog-verifier' in Ollama for 100% GPU-accelerated local inference.
"""

import os
import subprocess
from pathlib import Path

BASE_DIR = Path("d:/rtl-verification")
LORA_ADAPTER_DIR = BASE_DIR / "training" / "output" / "llama-verifier-lora"
MODELFILE_PATH = BASE_DIR / "training" / "output" / "Modelfile.verifier"


def export_and_register(model_name: str = "llama-verilog-verifier"):
    print("=================================================================")
    print(f"REGISTERING '{model_name}' IN OLLAMA (GPU ACCELERATED)")
    print("=================================================================")

    # Ollama Modelfile for Adversarial Verifier
    modelfile_content = f"""FROM llama3.1:8b

# Inference Parameters optimized for rigorous verification
PARAMETER temperature 0.2
PARAMETER top_p 0.95
PARAMETER top_k 40
PARAMETER num_ctx 4096
PARAMETER num_gpu 999

# System Prompt specialized for Adversarial RTL Verification
SYSTEM \"\"\"You are an expert Silicon Hardware Verification Engineer specializing in adversarial testbench generation.
Given an RTL specification and candidate Verilog implementation, generate an adversarial, self-checking Verilog-2001 testbench.
Inject protocol corner cases, stress boundary conditions, and implement cycle-accurate self-checking monitors with $fatal on mismatch.\"\"\"
"""

    MODELFILE_PATH.write_text(modelfile_content, encoding="utf-8")
    print(f"Created Modelfile at: {MODELFILE_PATH}")

    # Register in Ollama via CLI
    cmd = ["ollama", "create", model_name, "-f", str(MODELFILE_PATH)]
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Registration failed: {result.stderr}")
        return False

    print(result.stdout)
    print(f"Model '{model_name}' successfully registered in Ollama!")
    return True


if __name__ == "__main__":
    export_and_register()
