"""Pior caso da latência: a primeira análise depois que o Ollama descarrega o modelo (30 min sem uso ou reinício).
Descarrega o modelo (ollama stop), manda uma fatura com vencimento único (sem cache de prompt) e, em seguida, outra.
Uso, na raiz do projeto:  python docs/entrega-academica/ia/medir_partida_fria.py
Saída: sqlserver/evidence/parte3/latencia-partida-fria.json
"""
import json
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DIR = Path(__file__).resolve().parent
EV = DIR.parent / "sqlserver" / "evidence" / "parte3"
BASE = "http://127.0.0.1:5010"
OLLAMA_CONTAINER = "sigp_ollama"


def chave() -> str:
    for linha in (DIR.parent / "sqlserver" / ".env.academic").read_text(encoding="utf-8").splitlines():
        if linha.startswith("SIGP_AI_API_KEY="):
            return linha.split("=", 1)[1].strip()
    raise SystemExit("SIGP_AI_API_KEY não está no .env.academic")


def analisar(fatura: dict, api_key: str) -> dict:
    fatura = {**fatura, "due_date": f"2027-{secrets.randbelow(12) + 1:02d}-{secrets.randbelow(28) + 1:02d}"}
    pedido = Request(f"{BASE}/api/analyze", data=json.dumps({"invoice": fatura}).encode("utf-8"),
                     headers={"Content-Type": "application/json", "X-API-Key": api_key}, method="POST")
    inicio = time.perf_counter()
    with urlopen(pedido, timeout=300) as r:
        corpo = json.loads(r.read().decode("utf-8"))
    return {"cliente_ms": round((time.perf_counter() - inicio) * 1000, 1), "http": 200,
            "classification": corpo.get("classification"), "model_classification": corpo.get("model_classification")}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    api_key = chave()
    with urlopen(f"{BASE}/health", timeout=10) as r:
        saude = json.loads(r.read().decode("utf-8"))
    caso = json.loads((DIR / "casos-finais.json").read_text(encoding="utf-8"))["casos"][0]
    subprocess.run(["docker", "exec", OLLAMA_CONTAINER, "ollama", "stop", saude["model"]], check=True, capture_output=True)
    time.sleep(3)
    frio = analisar(caso["invoice"], api_key)
    quente = analisar(caso["invoice"], api_key)
    resultado = {"executado_em_utc": datetime.now(timezone.utc).isoformat(), "caso": caso["id"], "modelo": saude["model"],
                 "prompt_version": saude["prompt_version"], "metodo": "ollama stop + vencimento único por pedido",
                 "primeira_apos_descarregar": frio, "logo_depois": quente}
    (EV / "latencia-partida-fria.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prompt {saude['prompt_version']}: modelo descarregado {frio['cliente_ms'] / 1000:.1f} s · logo depois {quente['cliente_ms'] / 1000:.1f} s")


if __name__ == "__main__":
    main()
