"""
Export and Ollama Registration Script for Fine-Tuned Verilog Model.
1. Merges LoRA adapter with base Qwen2.5-Coder-1.5B weights.
2. Saves merged model in HuggingFace format.
3. Creates a customized Ollama Modelfile with hardware-enforced GPU offload.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path("d:/rtl-verification")
LORA_ADAPTER_DIR = BASE_DIR / "training" / "output" / "qwen1.5b-verilog-lora"
MERGED_MODEL_DIR = BASE_DIR / "training" / "output" / "qwen1.5b-verilog-merged"
MODELFILE_PATH = BASE_DIR / "training" / "output" / "Modelfile"


def merge_lora_model():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    base_model_id = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    print(f"Loading Base Model: {base_model_id} in float16...")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)

    print(f"Loading and merging LoRA adapter from: {LORA_ADAPTER_DIR}...")
    model = PeftModel.from_pretrained(base_model, str(LORA_ADAPTER_DIR))
    merged_model = model.merge_and_unload()

    print(f"Saving merged standalone model to: {MERGED_MODEL_DIR}...")
    merged_model.save_pretrained(str(MERGED_MODEL_DIR))
    tokenizer.save_pretrained(str(MERGED_MODEL_DIR))
    print("Merge complete!")


def generate_ollama_modelfile():
    """Generates Modelfile for Ollama integration."""
    content = f"""# Fine-Tuned Verilog Specialist Model
FROM qwen2.5-coder:1.5b

PARAMETER temperature 0.2
PARAMETER top_p 0.95
PARAMETER num_ctx 2048
PARAMETER num_gpu 99

SYSTEM \"\"\"
You are an expert RTL hardware engineer. Generate robust, synthesizable,
and standards-compliant Verilog HDL code matching the exact specification.
Always ensure valid syntax, correct module/endmodule declarations, and clean signal contracts.
\"\"\"
"""
    with open(MODELFILE_PATH, "w", encoding="utf-8") as f:
        f.write(content.strip())
    print(f"Ollama Modelfile generated at: {MODELFILE_PATH}")


if __name__ == "__main__":
    generate_ollama_modelfile()
