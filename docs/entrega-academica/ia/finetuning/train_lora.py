from __future__ import annotations

import hashlib
import json
import platform
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer


ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset.jsonl"
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
ADAPTER_DIR = ROOT / "output" / "qwen2.5-0.5b-lora"
REPORT = ROOT / "training-results.json"
CLASSES = ("CONTRATADO", "DIVERGENTE", "REVISAR")
SYSTEM = (
    "Classifique cobranças usando somente as evidências estruturadas fornecidas. "
    "Não aprove pagamentos. Se a evidência for insuficiente, responda REVISAR. "
    "Retorne somente JSON: {\"classification\":\"CONTRATADO|DIVERGENTE|REVISAR\"}."
)


def _messages(example: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": example["user"]},
    ]


def _load_rows() -> list[dict[str, str]]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]


def _classification(text: str) -> str:
    match = re.search(r'"classification"\s*:\s*"(CONTRATADO|DIVERGENTE|REVISAR)"', text)
    if match:
        return match.group(1)
    for label in CLASSES:
        if label in text.upper():
            return label
    return "INVALID"


def _evaluate(model, tokenizer, rows: list[dict[str, str]]) -> dict:
    model.eval()
    results = []
    for row in rows:
        prompt = tokenizer.apply_chat_template(
            _messages(row),
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        )["input_ids"].to("cpu")
        with torch.inference_mode():
            generated = model.generate(
                prompt,
                max_new_tokens=40,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        answer = tokenizer.decode(generated[0, prompt.shape[-1]:], skip_special_tokens=True)
        prediction = _classification(answer)
        results.append({
            "id": row["id"],
            "expected": row["classification"],
            "predicted": prediction,
            "correct": prediction == row["classification"],
            "output": answer.strip(),
        })
    confusion = {label: {predicted: 0 for predicted in CLASSES} for label in CLASSES}
    for row in results:
        if row["predicted"] in CLASSES:
            confusion[row["expected"]][row["predicted"]] += 1
    f1_scores = []
    for label in CLASSES:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[other][label] for other in CLASSES if other != label)
        false_negative = sum(confusion[label][other] for other in CLASSES if other != label)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
        f1_scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0)
    return {
        "count": len(results),
        "accuracy": sum(row["correct"] for row in results) / len(results) if results else 0,
        "macro_f1": sum(f1_scores) / len(f1_scores),
        "confusion_matrix": confusion,
        "results": results,
    }


def _training_tensors(tokenizer, row: dict[str, str]) -> tuple[torch.Tensor, torch.Tensor]:
    prompt_ids = tokenizer.apply_chat_template(
        _messages(row),
        tokenize=True,
        add_generation_prompt=True,
    )["input_ids"]
    full_ids = tokenizer.apply_chat_template(
        _messages(row) + [{"role": "assistant", "content": json.dumps(
            {"classification": row["classification"]}, separators=(",", ":")
        )}],
        tokenize=True,
        add_generation_prompt=False,
    )["input_ids"]
    labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids):]
    return torch.tensor([full_ids], dtype=torch.long), torch.tensor([labels], dtype=torch.long)


def main() -> int:
    random.seed(41)
    torch.manual_seed(41)
    torch.set_num_threads(min(torch.get_num_threads(), 8))
    rows = _load_rows()
    counts = Counter(row["split"] for row in rows)
    if counts != {"train": 80, "validation": 20, "test": 20}:
        raise ValueError(f"Unexpected split sizes: {dict(counts)}")
    dataset_hash = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    base = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        dtype=torch.float32,
        low_cpu_mem_usage=True,
    ).to("cpu")
    base.config.use_cache = False

    validation = [row for row in rows if row["split"] == "validation"]
    test = [row for row in rows if row["split"] == "test"]
    started = time.perf_counter()
    baseline = {
        "validation": _evaluate(base, tokenizer, validation),
        "test": _evaluate(base, tokenizer, test),
    }

    model = get_peft_model(base, LoraConfig(
        r=4,
        lora_alpha=8,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    ))
    model.print_trainable_parameters()
    train_rows = [row for row in rows if row["split"] == "train"]
    random.shuffle(train_rows)
    optimizer = torch.optim.AdamW(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=1e-4,
    )
    model.train()
    optimizer.zero_grad(set_to_none=True)
    accumulated = 0
    loss_total = 0.0
    for index, row in enumerate(train_rows, start=1):
        input_ids, labels = _training_tensors(tokenizer, row)
        loss = model(input_ids=input_ids, labels=labels).loss
        (loss / 4).backward()
        loss_total += loss.item()
        accumulated += 1
        if accumulated == 4 or index == len(train_rows):
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            accumulated = 0
        if index % 20 == 0:
            print(f"trained={index}/{len(train_rows)} mean_loss={loss_total / index:.4f}", flush=True)

    model.config.use_cache = True
    tuned = {
        "validation": _evaluate(model, tokenizer, validation),
        "test": _evaluate(model, tokenizer, test),
    }
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(ADAPTER_DIR)
    tokenizer.save_pretrained(ADAPTER_DIR)
    report = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "base_quantization": "none; float32 on CPU",
        "training_method": "LoRA",
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "transformers": version("transformers"),
            "peft": version("peft"),
            "accelerate": version("accelerate"),
            "cpu_threads": torch.get_num_threads(),
            "cuda_available": torch.cuda.is_available(),
        },
        "lora_config": {
            "rank": 4,
            "alpha": 8,
            "dropout": 0.05,
            "target_modules": ["q_proj", "v_proj"],
        },
        "epochs": 1,
        "learning_rate": 1e-4,
        "trainable_examples": len(train_rows),
        "validation_examples": len(validation),
        "test_examples": len(test),
        "dataset_sha256": dataset_hash,
        "training_loss_mean": loss_total / len(train_rows),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "baseline": baseline,
        "finetuned": tuned,
        "artifact_dir": str(ADAPTER_DIR.relative_to(ROOT)),
        "limitations": [
            "Synthetic, small dataset; results are preliminary and not evidence of production readiness.",
            "The 5 API acceptance cases are held out and are not part of this training dataset.",
            "No payment decision or authorization is learned or enabled by this experiment.",
        ],
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(REPORT),
        "elapsed_seconds": report["elapsed_seconds"],
        "baseline_test_accuracy": baseline["test"]["accuracy"],
        "lora_test_accuracy": tuned["test"]["accuracy"],
        "baseline_test_macro_f1": baseline["test"]["macro_f1"],
        "lora_test_macro_f1": tuned["test"]["macro_f1"],
        "artifact_dir": str(ADAPTER_DIR),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
