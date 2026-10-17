"""
QLoRA Fine-Tuning Script for Qwen2.5-Coder-1.5B on Synthesizable Verilog.
Optimized for NVIDIA GeForce RTX 4050 (6 GB VRAM).
Uses 4-bit NF4 quantization, gradient checkpointing, and LoRA adapters.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VerilogQLoRA")

BASE_DIR = Path("d:/rtl-verification")
DATASET_PATH = BASE_DIR / "training" / "dataset" / "verilog_train.json"
OUTPUT_DIR = BASE_DIR / "training" / "output" / "qwen1.5b-verilog-lora"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def format_chatml_prompt(instruction: str, output: str = "") -> str:
    """Formats sample into Qwen ChatML template."""
    system_msg = (
        "You are an expert RTL hardware engineer. Generate robust, synthesizable, "
        "and standards-compliant Verilog HDL code matching the exact specification. "
        "Always ensure valid syntax, correct module/endmodule declarations, and clean signal contracts."
    )
    prompt = f"<|im_start|>system\n{system_msg}<|im_end|>\n<|im_start|>user\n{instruction}<|im_end|>\n<|im_start|>assistant\n"
    if output:
        prompt += f"{output}<|im_end|>"
    return prompt


def run_training():
    import torch
    from datasets import Dataset
    from transformers import (
        AutoTokenizer,
        AutoModelForCausalLM,
        BitsAndBytesConfig,
        TrainingArguments,
        Trainer,
        DataCollatorForLanguageModeling,
    )
    from peft import (
        LoraConfig,
        get_peft_model,
        prepare_model_for_kbit_training,
        TaskType,
    )
    from trl import SFTTrainer, SFTConfig

    logger.info("=================================================================")
    logger.info("STARTING QLORA FINE-TUNING FOR QWEN2.5-CODER-1.5B (RTX 4050 6GB)")
    logger.info("=================================================================")

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available! Training requires an active NVIDIA GPU.")

    device_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    logger.info(f"Target GPU: {device_name} ({vram_gb:.2f} GB VRAM)")

    # 1. Load Dataset
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found at {DATASET_PATH}")

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    formatted_texts = [
        format_chatml_prompt(item["instruction"], item["output"])
        for item in raw_data
    ]
    train_dataset = Dataset.from_dict({"text": formatted_texts})
    logger.info(f"Loaded {len(train_dataset)} training examples from {DATASET_PATH}")

    # 2. Configure 4-bit Quantization (NF4)
    model_id = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    logger.info(f"Loading Base Model: {model_id} in 4-bit NF4...")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    model = prepare_model_for_kbit_training(model)

    # 3. Configure LoRA (Target all linear layers)
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj"
        ],
    )

    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 4. Tokenize Dataset with Causal LM labels
    def tokenize_fn(batch):
        res = tokenizer(batch["text"], truncation=True, max_length=1024)
        res["labels"] = [x.copy() for x in res["input_ids"]]
        return res

    tokenized_dataset = train_dataset.map(tokenize_fn, batched=True, remove_columns=["text"])
    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    # 5. Training Arguments optimized for RTX 4050 6GB VRAM (Ada Lovelace)
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        warmup_steps=2,
        num_train_epochs=3,
        learning_rate=2e-4,
        bf16=True,
        fp16=False,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=1,
        optim="paged_adamw_8bit",
        save_strategy="epoch",
        report_to="none",
    )

    # 6. Initialize HuggingFace Trainer
    trainer = Trainer(
        model=model,
        train_dataset=tokenized_dataset,
        data_collator=collator,
        args=training_args,
    )

    logger.info("Executing training loop on NVIDIA RTX 4050...")
    trainer.train()

    # 6. Save Adapter & Tokenizer
    logger.info(f"Saving fine-tuned LoRA adapter to {OUTPUT_DIR}...")
    trainer.model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    logger.info("QLoRA fine-tuning completed successfully!")


if __name__ == "__main__":
    run_training()
