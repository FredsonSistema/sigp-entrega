"""Entrega final: comparação do fine-tuning em quatro configurações, com acerto, custo e latência medidos.

  1. modelo base (Qwen2.5-0.5B-Instruct, sem adaptador), sem RAG
  2. modelo base com RAG
  3. modelo ajustado (o mesmo base + adaptador LoRA do SIGp), sem RAG
  4. modelo ajustado com RAG

Base e ajustado rodam no mesmo servidor Transformers (finetuning/server.py), com os mesmos pesos float32, a mesma
geração determinística (sem amostragem) e o mesmo prompt do treino; só muda o adaptador (ligado ou desligado).
Aqui se mede o MODELO sozinho: a decisão da regra (evidence_assessment) não entra no prompt.

Conjuntos:
  A. Os 16 casos finais (casos-finais.json), fora da distribuição do treino. "Com RAG" põe na Evidência os documentos
     que a busca da API (retrieve_documents, filtrada por local e provedor) recupera; "sem RAG", "nenhuma evidência
     recuperada".
  B. Os 20 casos de teste do treino (dataset.jsonl, split test), na distribuição do treino. "Com evidência" é o texto
     original; "sem evidência" troca a Evidência pelo mesmo texto vazio.

Custo por 1.000 usos: o modelo é local, não há cobrança por token. O custo vem do tempo de geração medido:
tempo de CPU e energia do processador a 15 W (potência base do i5-1345U) e a 55 W (turbo máximo), na tarifa
residencial B1 da Coelba. Os parâmetros e as fontes vão no resultado.

Pré-requisito: o servidor do LoRA em http://127.0.0.1:5014 (container temporário; ver comparacao-final.md).
Saída: sqlserver/evidence/parte3/finetuning-comparacao.json
Uso, na raiz do projeto:  .venv-1\\Scripts\\python.exe -u docs/entrega-academica/ia/finetuning/comparar_finetuning.py
"""
from __future__ import annotations

import importlib.util
import json
import platform
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DIR = Path(__file__).resolve().parent
IA = DIR.parent
SAIDA = IA.parent / "sqlserver" / "evidence" / "parte3" / "finetuning-comparacao.json"
SERVIDOR = "http://127.0.0.1:5014"
CLASSES = ("CONTRATADO", "DIVERGENTE", "REVISAR")
LOCAL, UNIDADE = "LOC-001", "Agência Centro"
SEM_EVIDENCIA = "nenhuma evidência recuperada"
# Mesmo prompt de sistema do treino (train_lora.py / generate_dataset.py).
SYSTEM = (
    "Classifique cobranças usando somente as evidências estruturadas fornecidas. "
    "Não aprove pagamentos. Se a evidência for insuficiente, responda REVISAR. "
    "Retorne somente JSON: {\"classification\":\"CONTRATADO|DIVERGENTE|REVISAR\"}."
)
CONFIGS = [
    ("base", False, False), ("base_rag", False, True), ("ajustado", True, False), ("ajustado_rag", True, True),
]
NOMES = {"base": "Modelo base", "base_rag": "Base com RAG", "ajustado": "Modelo ajustado (LoRA)", "ajustado_rag": "Ajustado com RAG"}
CUSTO = {
    "potencia_base_w": 15, "potencia_turbo_w": 55,
    "fonte_potencia": "Intel Core i5-1345U: potência base 15 W, turbo máximo 55 W (ficha da Intel, via cpu-monkey.com/en/benchmark-intel_core_i5_1345u-cpu_performance_per_watt)",
    "tarifa_r_kwh": 1.2418,
    "fonte_tarifa": "Coelba, residencial B1 com impostos, vigência desde 22/04/2026 (ANEEL, Resolução Homologatória nº 3.578/2026; valor em apontasol.com.br/tarifa/coelba)",
    "observacao": "Energia só do processador, estimada a partir do tempo de geração medido; tela, memória e o resto da máquina não entram. Não há cobrança por token (modelo local).",
}


def carregar_app():
    spec = importlib.util.spec_from_file_location("sigp_academic_ai", IA / "app.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def classificar(user: str, adapter: bool) -> dict:
    corpo = json.dumps({"system": SYSTEM, "prompt": user, "adapter": adapter}, ensure_ascii=False).encode("utf-8")
    pedido = Request(f"{SERVIDOR}/classify", data=corpo, method="POST", headers={"Content-Type": "application/json"})
    inicio = time.perf_counter()
    try:
        with urlopen(pedido, timeout=600) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as e:
        return {"erro": str(e), "ms_cliente": round((time.perf_counter() - inicio) * 1000, 1)}
    dados["ms_cliente"] = round((time.perf_counter() - inicio) * 1000, 1)
    return dados


def rotulo(texto: str) -> str:
    # Mesmo leitor do treino (train_lora._classification).
    m = re.search(r'"classification"\s*:\s*"(CONTRATADO|DIVERGENTE|REVISAR)"', texto or "")
    if m:
        return m.group(1)
    for c in CLASSES:
        if c in (texto or "").upper():
            return c
    return "INVALIDO"


def conjunto_a(app) -> list[dict]:
    casos = json.loads((IA / "casos-finais.json").read_text(encoding="utf-8"))["casos"]
    itens = []
    for c in casos:
        inv = app._normalize_invoice(c["invoice"])
        valor = app._parse_amount(inv["amount"])
        provider_id = app.PROVIDER_IDS.get(app._provider_key(inv["provider"]), "PROV-UNKNOWN")
        consulta = " ".join((inv["provider"], inv["description"], str(inv["amount"]), str(inv.get("due_date", ""))))
        docs = app.retrieve_documents(consulta, LOCAL, provider_id)
        evidencia = " | ".join(f"[{d['id']}] {d['title']}: {d['text']}" for d in docs) or SEM_EVIDENCIA
        base = f"Cobrança: {inv['description']}, R$ {valor:.2f}. Provedor: {inv['provider']}. Unidade: {UNIDADE}. Evidência: "
        itens.append({"id": c["id"], "esperado": c["esperado"]["classification"], "fontes": [d["id"] for d in docs],
                      "sem": f"{base}{SEM_EVIDENCIA}. Qual é a classificação?",
                      "com": f"{base}{evidencia}. Qual é a classificação?"})
    return itens


def conjunto_b() -> list[dict]:
    linhas = [json.loads(l) for l in (DIR / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    itens = []
    for r in linhas:
        if r["split"] != "test":
            continue
        sem = re.sub(r"Evidência: .*?(?= Qual é a classificação\?)", f"Evidência: {SEM_EVIDENCIA}.", r["user"])
        if sem == r["user"]:
            raise RuntimeError(f"Não achei a Evidência em {r['id']}.")
        itens.append({"id": r["id"], "esperado": r["classification"], "sem": sem, "com": r["user"]})
    return itens


def pct(valores: list[float], p: float):
    if not valores:
        return None
    v = sorted(valores)
    return round(v[max(0, min(len(v) - 1, round(p * (len(v) - 1))))], 1)


def metricas(linhas: list[dict]) -> dict:
    matriz = {e: {o: 0 for o in (*CLASSES, "INVALIDO")} for e in CLASSES}
    for l in linhas:
        matriz[l["esperado"]][l["obtido"]] += 1
    f1s, por_classe = [], {}
    for c in CLASSES:
        vp = matriz[c][c]
        fp = sum(matriz[e][c] for e in CLASSES if e != c)
        fn = sum(v for o, v in matriz[c].items() if o != c)
        p = vp / (vp + fp) if vp + fp else 0.0
        r = vp / (vp + fn) if vp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        f1s.append(f1)
        por_classe[c] = {"precisao": round(p, 3), "revocacao": round(r, 3), "f1": round(f1, 3)}
    gen = [l["generation_ms"] for l in linhas if isinstance(l.get("generation_ms"), (int, float))]
    tin = [l["input_tokens"] for l in linhas if isinstance(l.get("input_tokens"), int)]
    tout = [l["output_tokens"] for l in linhas if isinstance(l.get("output_tokens"), int)]
    media_s = statistics.fmean(gen) / 1000 if gen else None
    custo = None
    if media_s is not None:
        horas = media_s * 1000 / 3600
        custo = {
            "tempo_cpu_min": round(media_s * 1000 / 60, 1),
            "energia_kwh_15w": round(CUSTO["potencia_base_w"] * horas / 1000, 4),
            "energia_kwh_55w": round(CUSTO["potencia_turbo_w"] * horas / 1000, 4),
            "reais_15w": round(CUSTO["potencia_base_w"] * horas / 1000 * CUSTO["tarifa_r_kwh"], 4),
            "reais_55w": round(CUSTO["potencia_turbo_w"] * horas / 1000 * CUSTO["tarifa_r_kwh"], 4),
        }
    acertos = sum(l["obtido"] == l["esperado"] for l in linhas)
    return {
        "n": len(linhas), "acertos": acertos, "acuracia": round(acertos / len(linhas), 3) if linhas else None,
        "f1_macro": round(statistics.fmean(f1s), 3), "por_classe": por_classe, "matriz_confusao": matriz,
        "falsas_aprovacoes": [l["id"] for l in linhas if l["obtido"] == "CONTRATADO" and l["esperado"] != "CONTRATADO"],
        "respostas_invalidas": sum(l["obtido"] == "INVALIDO" for l in linhas),
        "latencia_ms": {"media": round(statistics.fmean(gen), 1) if gen else None, "mediana": round(statistics.median(gen), 1) if gen else None,
                        "p95": pct(gen, 0.95), "max": round(max(gen), 1) if gen else None},
        "tokens_entrada_media": round(statistics.fmean(tin), 1) if tin else None,
        "tokens_saida_media": round(statistics.fmean(tout), 1) if tout else None,
        "custo_por_1000_usos": custo,
    }


def cpu_percent():
    try:
        import psutil  # opcional: só para registrar a carga da máquina
        return psutil.cpu_percent(interval=1.0)
    except ImportError:
        return None


def rodar(nome: str, itens: list[dict]) -> dict:
    linhas = {k: [] for k, _, _ in CONFIGS}
    cargas = []
    for i, item in enumerate(itens, 1):
        cargas.append(cpu_percent())
        for k, adapter, rag in CONFIGS:  # as 4 configurações intercaladas, caso a caso
            r = classificar(item["com" if rag else "sem"], adapter)
            obtido = rotulo(r.get("response", "")) if "erro" not in r else "INVALIDO"
            linhas[k].append({"id": item["id"], "esperado": item["esperado"], "obtido": obtido,
                              "resposta": (r.get("response") or r.get("erro") or "")[:160],
                              "generation_ms": r.get("generation_ms"), "input_tokens": r.get("input_tokens"),
                              "output_tokens": r.get("output_tokens"), "ms_cliente": r.get("ms_cliente")})
        print(f"  {nome} {i:>2}/{len(itens)} {item['id']:<9} esperado {item['esperado']:<10} "
              + " ".join(f"{k}={linhas[k][-1]['obtido'][:4]}" for k, _, _ in CONFIGS), flush=True)
    cargas_validas = [c for c in cargas if c is not None]
    return {"configuracoes": {k: {"nome": NOMES[k], "adaptador": a, "rag": rg, "metricas": metricas(linhas[k]), "casos": linhas[k]}
                              for k, a, rg in CONFIGS},
            "cpu_maquina_percent_media": round(statistics.fmean(cargas_validas), 1) if cargas_validas else None}


def main() -> int:
    with urlopen(f"{SERVIDOR}/health", timeout=10) as r:
        saude = json.loads(r.read().decode("utf-8"))
    app = carregar_app()
    a, b = conjunto_a(app), conjunto_b()
    print(f"Servidor: {saude.get('model')} · base {saude.get('base_model')}@{saude.get('base_revision', '')[:8]}")
    for adapter in (False, True):  # aquecimento, não conta
        classificar(b[0]["com"], adapter)
    print("Conjunto A (16 casos finais, RAG real):")
    res_a = rodar("A", a)
    print("Conjunto B (20 casos de teste do treino):")
    res_b = rodar("B", b)
    resultado = {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "servidor": saude,
        "maquina": {"sistema": platform.platform(), "processador": platform.processor()},
        "geracao": "sem amostragem (do_sample=False), max_new_tokens=160, float32, CPU",
        "prompt_sistema": SYSTEM,
        "custo_parametros": CUSTO,
        "conjunto_a_casos_finais": res_a,
        "conjunto_b_teste_do_treino": res_b,
        "fontes_rag_por_caso_a": {x["id"]: x["fontes"] for x in a},
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print()
    for titulo, res in (("A (16 casos finais)", res_a), ("B (20 de teste do treino)", res_b)):
        print(f"Conjunto {titulo} · CPU da máquina {res['cpu_maquina_percent_media']}%")
        for k, _, _ in CONFIGS:
            m = res["configuracoes"][k]["metricas"]
            c = m["custo_por_1000_usos"] or {}
            print(f"  {NOMES[k]:<24} acerto {m['acertos']:>2}/{m['n']} ({m['acuracia']:.2f}) F1 {m['f1_macro']:.3f} "
                  f"falsas aprov. {len(m['falsas_aprovacoes'])} inválidas {m['respostas_invalidas']} · "
                  f"latência média {m['latencia_ms']['media']} ms p95 {m['latencia_ms']['p95']} · tokens {m['tokens_entrada_media']} · "
                  f"1.000 usos: {c.get('tempo_cpu_min')} min CPU, R$ {c.get('reais_15w')}–{c.get('reais_55w')}")
    print(f"Resultado: {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
