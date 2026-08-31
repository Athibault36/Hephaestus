"""QLoRA fine-tuning on Hephaestus code — budget-friendly, L40S-sized."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"


def train_lora(
    dataset_path: Path,
    output_dir: Path,
    base_model: str = DEFAULT_BASE_MODEL,
    max_steps: int = 60,
    batch_size: int = 1,
    grad_accum: int = 8,
    learning_rate: float = 2e-4,
    max_seq_length: int = 4096,
) -> Path:
    """
    Run a short QLoRA SFT session on a JSONL messages dataset.
    Tuned for ~30-45 min on L40S under credit budget.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    rows = []
    with dataset_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        raise ValueError(f"No training rows in {dataset_path}")

    def format_example(example: dict) -> dict:
        parts = []
        for msg in example["messages"]:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"<|im_start|>system\n{content}")
            elif role == "user":
                parts.append(f"<|im_start|>user\n{content}")
            else:
                parts.append(f"<|im_start|>assistant\n{content}")
        text = "\n".join(parts) + "\n"
        return {"text": text}

    dataset = Dataset.from_list([format_example(r) for r in rows])

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # bf16 LoRA on L40S (48GB) — avoids bitsandbytes/triton compile issues on Brev
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    lora = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)

    training_args = SFTConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=learning_rate,
        max_steps=max_steps,
        logging_steps=5,
        save_steps=max_steps,
        save_total_limit=1,
        bf16=True,
        optim="adamw_torch",
        report_to="none",
        warmup_steps=max(1, max_steps // 20),
        max_length=max_seq_length,
        dataset_text_field="text",
        gradient_checkpointing=False,
        use_liger_kernel=False,
        torch_compile=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    trainer.train()
    adapter_dir = output_dir / "adapter"
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    return adapter_dir


def embed_codebase(
    repo_root: Path,
    output_dir: Path,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> Path:
    """Build a simple embedding index for code RAG (CPU/GPU friendly)."""
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError("Install: pip install sentence-transformers") from e

    from .dataset_builder import _iter_source_files

    output_dir.mkdir(parents=True, exist_ok=True)
    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    model = SentenceTransformer(model_name, device=device)

    records = []
    texts = []
    for path in _iter_source_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        snippet = content[:4000]
        texts.append(f"File: {rel}\n{snippet}")
        records.append({"path": rel, "chars": len(content)})

    if not texts:
        raise ValueError("No source files found for embedding")

    embeddings = model.encode(texts, batch_size=16, show_progress_bar=True, normalize_embeddings=True)
    np.save(output_dir / "embeddings.npy", embeddings)
    (output_dir / "index.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    return output_dir
