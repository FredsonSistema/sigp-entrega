from __future__ import annotations

import os
import threading
import time

import torch
from flask import Flask, jsonify, request
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
ADAPTER_PATH = os.environ.get("SIGP_LORA_ADAPTER_PATH", "/models/adapter")
MODEL_NAME = "Qwen2.5-0.5B-Instruct+SIGp-LoRA"
MAX_INPUT_CHARS = 100_000
CPU_THREADS = int(os.environ.get("MODEL_CPU_THREADS", "6"))

torch.set_num_threads(max(1, CPU_THREADS))
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
base_model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    revision=MODEL_REVISION,
    dtype=torch.float32,
    low_cpu_mem_usage=True,
)
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH, is_trainable=False)
model.eval()
model.config.use_cache = True
generation_lock = threading.Lock()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": MODEL_NAME,
        "base_model": MODEL_ID,
        "base_revision": MODEL_REVISION,
        "adapter": "sigp-lora",
    })


@app.post("/classify")
def classify():
    payload = request.get_json(silent=True)
    # "adapter" é opcional (padrão: ligado). Desligado, responde o modelo base com os mesmos pesos e a mesma geração,
    # para a comparação base x ajustado (comparar_finetuning.py). A API acadêmica não envia o campo.
    if not isinstance(payload, dict) or not {"system", "prompt"} <= set(payload) <= {"system", "prompt", "adapter"}:
        return jsonify({"ok": False, "error": "Envie somente system, prompt e, opcionalmente, adapter."}), 400
    use_adapter = payload.get("adapter", True)
    if not isinstance(use_adapter, bool):
        return jsonify({"ok": False, "error": "adapter deve ser true ou false."}), 400
    system = payload["system"]
    prompt = payload["prompt"]
    if not isinstance(system, str) or not isinstance(prompt, str):
        return jsonify({"ok": False, "error": "system e prompt devem ser texto."}), 400
    if not system.strip() or not prompt.strip() or len(system) + len(prompt) > MAX_INPUT_CHARS:
        return jsonify({"ok": False, "error": "Prompt vazio ou excede o limite permitido."}), 400

    encoded = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
    )
    input_ids = encoded["input_ids"]
    with generation_lock, torch.inference_mode():
        started = time.perf_counter()
        if use_adapter:
            generated = model.generate(input_ids, max_new_tokens=160, do_sample=False, pad_token_id=tokenizer.eos_token_id)
        else:
            with model.disable_adapter():
                generated = model.generate(input_ids, max_new_tokens=160, do_sample=False, pad_token_id=tokenizer.eos_token_id)
        elapsed_ms = (time.perf_counter() - started) * 1000
    output_ids = generated[0, input_ids.shape[-1]:]
    response = tokenizer.decode(output_ids, skip_special_tokens=True)
    return jsonify({
        "response": response,
        "model": MODEL_NAME if use_adapter else f"{MODEL_ID} (sem adaptador)",
        "adapter": use_adapter,
        "input_tokens": int(input_ids.shape[-1]),
        "output_tokens": int(output_ids.shape[-1]),
        "generation_ms": round(elapsed_ms, 1),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5011, threaded=True)
