"""Entrega final: latência e custo por 1.000 usos do sistema como está no ar (API -> SQL Server/RLS -> RAG -> Qwen
0,5B no Ollama -> regra -> auditoria), com faturas DIFERENTES a cada chamada.

O medir_latencia.py (parte 2, removido na limpeza final; está no histórico do Git) repetia a mesma fatura; o Ollama reaproveita o prompt já processado (cache de prefixo) e
o tempo sai otimista. Aqui cada chamada é um dos 16 casos finais (casos-finais.json). O Ollama guarda os últimos 16
prompts em cache, então repetir as mesmas faturas também sairia otimista: cada fatura recebe um vencimento único desta
rodada (o vencimento entra no começo do prompt e não muda nenhuma regra), e o prompt é novo a cada chamada, como no
uso real. Com SIGP_LATENCIA_CACHE=1 as faturas vão sem mudança (mede o caso do prompt já em cache).
Uma chamada de aquecimento não entra na conta. A carga de CPU da máquina é medida antes e depois.

Custo: sem cobrança por token (modelo local). Tempo de CPU e energia do processador a 15 W e 55 W na tarifa da Coelba
(mesmos parâmetros e fontes de finetuning/comparar_finetuning.py).
Saída: sqlserver/evidence/parte3/latencia-custo-final.json (ou SIGP_LATENCIA_SAIDA).
Uso, na raiz:  .venv-1\\Scripts\\python.exe -u docs/entrega-academica/ia/medir_latencia_final.py
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DIR = Path(__file__).resolve().parent
SAIDA = Path(os.environ.get("SIGP_LATENCIA_SAIDA") or (DIR.parent / "sqlserver" / "evidence" / "parte3" / "latencia-custo-final.json"))
BASE = "http://127.0.0.1:5010"
W_BASE, W_TURBO, TARIFA = 15, 55, 1.2418


def chave() -> str:
    for linha in (DIR.parent / "sqlserver" / ".env.academic").read_text(encoding="utf-8").splitlines():
        if linha.startswith("SIGP_AI_API_KEY="):
            return linha.split("=", 1)[1].strip()
    sys.exit("SIGP_AI_API_KEY não encontrada no .env.academic.")


def cpu_maquina() -> float | None:
    """Uso de CPU do Windows (média de 3 amostras), pelo contador do sistema."""
    # O nome do contador depende do idioma do Windows; descarta as amostras vazias antes de trocar de nome.
    # O nome do contador depende do idioma do Windows; descarta as amostras vazias antes de trocar de nome.
    comando = ("$v = @(1..3 | % { (Get-Counter '\\Processador(_Total)\\% Tempo de Processador' -ErrorAction SilentlyContinue).CounterSamples.CookedValue } | ? { $_ -ne $null });"
               "if ($v.Count -eq 0) { $v = @(1..3 | % { (Get-Counter '\\Processor(_Total)\\% Processor Time' -ErrorAction SilentlyContinue).CounterSamples.CookedValue } | ? { $_ -ne $null }) };"
               "if ($v.Count -eq 0) { 'NA' } else { [math]::Round(($v | Measure-Object -Average).Average, 1) }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip().replace(",", "."))
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return None


def chamar(k: str, invoice: dict) -> dict:
    dados = json.dumps({"invoice": invoice}, ensure_ascii=False).encode("utf-8")
    pedido = Request(f"{BASE}/api/analyze", data=dados, method="POST", headers={"Content-Type": "application/json", "X-API-Key": k})
    inicio = time.perf_counter()
    try:
        with urlopen(pedido, timeout=300) as r:
            corpo = json.loads(r.read().decode("utf-8"))
            status = r.status
    except HTTPError as e:
        status, corpo = e.code, {}
    except (URLError, TimeoutError):
        status, corpo = 0, {}
    return {"http": status, "cliente_ms": round((time.perf_counter() - inicio) * 1000, 1), "servidor_ms": corpo.get("latency_ms")}


def resumo(v: list[float]) -> dict:
    s = sorted(v)
    return {"n": len(v), "media": round(statistics.fmean(v), 1), "mediana": round(statistics.median(v), 1),
            "p95": round(s[max(0, min(len(s) - 1, round(0.95 * (len(s) - 1))))], 1), "min": round(s[0], 1), "max": round(s[-1], 1)}


def custo(media_ms: float) -> dict:
    horas = media_ms / 1000 * 1000 / 3600
    return {"tempo_cpu_min": round(media_ms / 1000 * 1000 / 60, 1),
            "energia_kwh_15w": round(W_BASE * horas / 1000, 4), "energia_kwh_55w": round(W_TURBO * horas / 1000, 4),
            "reais_15w": round(W_BASE * horas / 1000 * TARIFA, 4), "reais_55w": round(W_TURBO * horas / 1000 * TARIFA, 4)}


def main() -> int:
    k = chave()
    casos = json.loads((DIR / "casos-finais.json").read_text(encoding="utf-8"))["casos"]
    cpu_antes = cpu_maquina()
    chamar(k, {"provider": "Conecta Alfa Fictícia", "description": "aquecimento latência", "amount": "1.00"})
    medidas = []
    usar_cache = os.environ.get("SIGP_LATENCIA_CACHE") == "1"
    # Vencimento único por rodada e por caso: o prompt nunca está no cache do Ollama.
    rodada = int(time.time()) % 100_000
    for i, c in enumerate(casos):
        invoice = dict(c["invoice"])
        if not usar_cache:
            invoice["due_date"] = (date(2026, 1, 1) + timedelta(days=(rodada * 17 + i) % 3650)).isoformat()
        r = chamar(k, invoice)
        medidas.append({"id": c["id"], **r})
        print(f"  {c['id']} HTTP {r['http']} servidor {r['servidor_ms']} ms", flush=True)
    cpu_depois = cpu_maquina()
    ok = [m for m in medidas if m["http"] == 200 and isinstance(m["servidor_ms"], (int, float))]
    serv = resumo([m["servidor_ms"] for m in ok])
    resultado = {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "caminho": "API -> SQL Server (RLS) -> RAG lexical -> qwen2.5:0.5b (Ollama, CPU) -> regra -> auditoria",
        "metodo": (f"1 aquecimento + {len(casos)} faturas diferentes (casos-finais.json), uma chamada cada; "
                   + ("faturas sem mudança (prompt já em cache no Ollama)" if usar_cache
                      else "vencimento único por rodada: prompt novo a cada chamada (sem cache)")),
        "prompt_em_cache": usar_cache,
        "cpu_maquina_percent": {"antes": cpu_antes, "depois": cpu_depois},
        "respostas_200": f"{len(ok)}/{len(medidas)}",
        "latencia_servidor_ms": serv,
        "latencia_cliente_ms": resumo([m["cliente_ms"] for m in ok]),
        "custo_por_1000_usos": {**custo(serv["media"]), "cobranca_por_token": 0,
                                "parametros": {"potencia_w": [W_BASE, W_TURBO], "tarifa_r_kwh": TARIFA},
                                "observacao": "Energia só do processador, estimada a partir do tempo medido."},
        "medidas": medidas,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    c = resultado["custo_por_1000_usos"]
    print(f"\nCPU da máquina: antes {cpu_antes}% · depois {cpu_depois}% · respostas {resultado['respostas_200']}")
    print(f"Latência (servidor): média {serv['media']} ms · mediana {serv['mediana']} · p95 {serv['p95']}")
    print(f"1.000 usos: {c['tempo_cpu_min']} min de CPU · R$ {c['reais_15w']} (15 W) a R$ {c['reais_55w']} (55 W)")
    print(f"Resultado: {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
