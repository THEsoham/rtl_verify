"""
QLoRA Fine-Tuning Script for Adversarial Verifier on Synthesizable Verilog Testbenches.
Optimized for NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM, Ada Lovelace).
Uses 4-bit NF4 quantization, gradient checkpointing, paged 8-bit AdamW optimizer, and LoRA adapters.
"""

import os
import sys
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VerilogVerifierQLoRA")

BASE_DIR = Path("d:/rtl-verification")
DATASET_PATH = BASE_DIR / "training" / "dataset" / "verilog_verifier_train.json"
OUTPUT_DIR = BASE_DIR / "training" / "output" / "llama-verifier-lora"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_verifier_training(model_id: str = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"):
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

    logger.info("=================================================================")
    logger.info("STARTING QLORA FINE-TUNING FOR ADVERSARIAL VERIFIER (RTX 4050 6GB)")
    logger.info(f"Base Model: {model_id}")
    logger.info("=================================================================")

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available! Training requires NVIDIA GPU.")

    device_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    logger.info(f"Active GPU: {device_name} ({vram_gb:.2f} GB VRAM)")

    # 1. Load Dataset
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found at {DATASET_PATH}")

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    train_dataset = Dataset.from_dict({"text": [item["text"] for item in raw_data]})
    logger.info(f"Loaded {len(train_dataset)} verifier training examples from {DATASET_PATH}")

    # 2. Tokenizer & Model
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    logger.info(f"Loading {model_id} in 4-bit NF4...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    model = prepare_model_for_kbit_training(model)

    # 3. LoRA Configuration
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )

    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 4. Tokenization
    def tokenize_fn(batch):
        res = tokenizer(batch["text"], truncation=True, max_length=1024)
        res["labels"] = [x.copy() for x in res["input_ids"]]
        return res

    tokenized_dataset = train_dataset.map(tokenize_fn, batched=True, remove_columns=["text"])
    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    # 5. Training Arguments tuned for 6 GB VRAM
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        warmup_steps=1,
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

    trainer = Trainer(
        model=model,
        train_dataset=tokenized_dataset,
        data_collator=collator,
        args=training_args,
    )

    logger.info("Executing training loop for Adversarial Verifier on RTX 4050...")
    trainer.train()

    logger.info(f"Saving fine-tuned verifier adapter to {OUTPUT_DIR}...")
    trainer.model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    logger.info("Adversarial Verifier QLoRA fine-tuning completed successfully!")


if __name__ == "__main__":
    run_verifier_training()
