from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge the SIGp LoRA adapter into its pinned base model.")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    adapter_dir = args.adapter.resolve(strict=True)
    output_dir = args.output.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    adapter_config = json.loads((adapter_dir / "adapter_config.json").read_text(encoding="utf-8"))
    if adapter_config.get("base_model_name_or_path") != MODEL_ID:
        raise ValueError("Adapter base model does not match the pinned Qwen checkpoint.")

    output_dir.mkdir(parents=True)
    try:
        base_model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            revision=MODEL_REVISION,
            dtype=torch.float32,
            low_cpu_mem_usage=True,
        )
        adapted_model = PeftModel.from_pretrained(base_model, adapter_dir, is_trainable=False)
        merged_model = adapted_model.merge_and_unload(safe_merge=True)
        merged_model.save_pretrained(output_dir, safe_serialization=True, max_shard_size="2GB")
        AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION).save_pretrained(output_dir)
    except Exception:
        shutil.rmtree(output_dir)
        raise

    print(f"Merged model written to {output_dir}")


if __name__ == "__main__":
    main()
