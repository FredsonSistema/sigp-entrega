"""Medição do RAG com embeddings (critério fixado antes em rag-embeddings-criterio.md).

Compara, sobre o mesmo escopo (LOC-001 / PROV-001 e políticas gerais):
  - lexical: retrieve_documents() de app.py, a busca atual;
  - embedding: similaridade de cosseno com cada modelo do Ollama;
  - híbrido: fusão de postos recíprocos (RRF, k = 60) entre lexical e embedding.
Conjuntos: rag-parafrases.json (14) e casos-finais.json (os casos com fontes obrigatórias).
Métricas: revocação@5, revocação@3, MRR, latência por consulta (gerar o vetor + ordenar).

Modos:
  medir      roda dentro do contêiner da IA acadêmica (tem Flask e alcança o Ollama):
               docker cp docs/entrega-academica/ia sigp_academic_ai:/tmp/ia
               docker exec -e PYTHONIOENCODING=utf-8 sigp_academic_ai python /tmp/ia/medir_rag_embeddings.py medir /tmp/rag-embeddings.json
               docker cp sigp_academic_ai:/tmp/rag-embeddings.json docs/entrega-academica/sqlserver/evidence/parte3/
  documento  gera ia/rag-embeddings.md a partir da evidência e aplica o critério (no host, só biblioteca padrão).
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DIR = Path(__file__).resolve().parent
EVIDENCIA = DIR.parent / "sqlserver" / "evidence" / "parte3" / "rag-embeddings.json"
DOCUMENTO = DIR / "rag-embeddings.md"
LOCAL_ID = "LOC-001"
MODELOS = ["nomic-embed-text", "embeddinggemma", "bge-m3"]
# Prefixos recomendados na documentação de cada modelo (o mesmo texto, com a marca de consulta ou documento).
PREFIXOS = {
    "nomic-embed-text": ("search_query: ", "search_document: "),
    "embeddinggemma": ("task: search result | query: ", "title: none | text: "),
    "bge-m3": ("", ""),
}
RRF_K = 60


def _carregar_app():
    spec = importlib.util.spec_from_file_location("sigp_academic_ai_medicao", DIR / "app.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _embed(url: str, modelo: str, textos: list[str]) -> list[list[float]]:
    corpo = json.dumps({"model": modelo, "input": textos, "keep_alive": "30m"}).encode("utf-8")
    req = Request(f"{url}/api/embed", data=corpo, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))["embeddings"]


def _cos(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _consultas(app) -> list[dict]:
    """Os dois conjuntos, com a consulta montada como o /api/analyze monta."""
    itens = []
    paraf = json.loads((DIR / "rag-parafrases.json").read_text(encoding="utf-8"))
    for caso in paraf["casos"]:
        itens.append({"conjunto": "parafrases", "id": caso["id"], "consulta": caso["consulta"],
                      "provider_id": "PROV-001", "fontes": caso["fontes"]})
    finais = json.loads((DIR / "casos-finais.json").read_text(encoding="utf-8"))
    for caso in finais["casos"]:
        fontes = caso["esperado"].get("fontes_obrigatorias", [])
        if not fontes:
            continue  # sem fonte obrigatória (provedor desconhecido / de outro local): nada a recuperar
        inv = app._normalize_invoice(dict(caso["invoice"]))
        provider = inv.get("provider") or ""
        consulta = " ".join((provider, inv.get("description") or "", str(inv.get("amount")),
                             str(inv.get("due_date", ""))))
        itens.append({"conjunto": "casos-finais", "id": caso["id"], "consulta": consulta,
                      "provider_id": app.PROVIDER_IDS.get(app._provider_key(provider), "PROV-UNKNOWN"),
                      "fontes": fontes})
    return itens


def _escopo(app, provider_id: str) -> list[dict]:
    return [d for d in app.CORPUS if d["local_id"] in {"*", LOCAL_ID} and d["provider_id"] in {"*", provider_id}]


def _rrf(*rankings: list[str]) -> list[str]:
    pontos: dict[str, float] = {}
    for ranking in rankings:
        for pos, doc in enumerate(ranking, start=1):
            pontos[doc] = pontos.get(doc, 0.0) + 1.0 / (RRF_K + pos)
    return [d for d, _ in sorted(pontos.items(), key=lambda kv: (-kv[1], kv[0]))]


def _metricas(resultados: list[dict]) -> dict:
    def rec(k):
        ok = sum(1 for r in resultados if set(r["fontes"]) <= set(r["top"][:k]))
        return {"acertos": ok, "total": len(resultados), "taxa": round(ok / len(resultados), 4)}
    rr = []
    for r in resultados:
        pos = next((i for i, d in enumerate(r["top"], start=1) if d in r["fontes"]), None)
        rr.append(1.0 / pos if pos else 0.0)
    lat = [r["latencia_ms"] for r in resultados]
    return {"revocacao_5": rec(5), "revocacao_3": rec(3), "mrr": round(sum(rr) / len(rr), 4),
            "latencia_mediana_ms": round(statistics.median(lat), 1), "latencia_max_ms": round(max(lat), 1)}


def medir(saida: Path) -> None:
    app = _carregar_app()
    url = os.environ.get("OLLAMA_URL", "http://ollama:11434").rstrip("/")
    consultas = _consultas(app)
    with urlopen(f"{url}/api/tags", timeout=30) as resp:
        tags = {m["name"].split(":")[0]: m for m in json.loads(resp.read().decode("utf-8"))["models"]}
    metodos: dict[str, list[dict]] = {"lexical": []}
    for c in consultas:
        t0 = time.perf_counter()
        top = [d["id"] for d in app.retrieve_documents(c["consulta"], LOCAL_ID, c["provider_id"], limit=5)]
        metodos["lexical"].append({**c, "top": top, "latencia_ms": (time.perf_counter() - t0) * 1000})
    modelos_info = {}
    for modelo in MODELOS:
        pq, pd = PREFIXOS[modelo]
        docs = list(app.CORPUS)
        _embed(url, modelo, ["aquecimento"])  # carrega o modelo na memória antes de medir
        t0 = time.perf_counter()
        vetores_docs = dict(zip([d["id"] for d in docs],
                                _embed(url, modelo, [pd + d["title"] + ". " + d["text"] for d in docs])))
        tempo_corpus = (time.perf_counter() - t0) * 1000
        info = tags.get(modelo, {})
        modelos_info[modelo] = {"download_bytes": info.get("size"), "digest": info.get("digest"),
                                "dimensao": len(next(iter(vetores_docs.values()))),
                                "vetorizar_corpus_20_docs_ms": round(tempo_corpus, 1),
                                "prefixo_consulta": pq, "prefixo_documento": pd}
        emb, hib = [], []
        for c, lex in zip(consultas, metodos["lexical"]):
            t0 = time.perf_counter()
            vq = _embed(url, modelo, [pq + c["consulta"]])[0]
            escopo = _escopo(app, c["provider_id"])  # o escopo vem antes da ordenação
            rank = [d["id"] for d in sorted(escopo, key=lambda d: (-_cos(vq, vetores_docs[d["id"]]), d["id"]))]
            t_emb = (time.perf_counter() - t0) * 1000
            emb.append({**c, "top": rank[:5], "latencia_ms": t_emb})
            t1 = time.perf_counter()
            fundido = _rrf(lex["top"], rank)[:5]
            hib.append({**c, "top": fundido, "latencia_ms": t_emb + lex["latencia_ms"] + (time.perf_counter() - t1) * 1000})
        metodos[f"embedding:{modelo}"] = emb
        metodos[f"hibrido:{modelo}"] = hib
    permitidos = {d["id"] for d in _escopo(app, "PROV-001")}
    resultado = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "criterio": "ia/rag-embeddings-criterio.md",
        "escopo": {"local_id": LOCAL_ID, "documentos_permitidos_prov001": sorted(permitidos)},
        "modelos": modelos_info,
        "metodos": {},
    }
    for nome, res in metodos.items():
        fora = sorted({d for r in res for d in r["top"]
                       if d not in {x["id"] for x in _escopo(app, r["provider_id"])}})
        resultado["metodos"][nome] = {
            "parafrases": _metricas([r for r in res if r["conjunto"] == "parafrases"]),
            "casos_finais": _metricas([r for r in res if r["conjunto"] == "casos-finais"]),
            "documentos_fora_do_escopo": fora,
            "detalhe": [{"conjunto": r["conjunto"], "id": r["id"], "fontes": r["fontes"], "top5": r["top"],
                         "latencia_ms": round(r["latencia_ms"], 1)} for r in res],
        }
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for nome, m in resultado["metodos"].items():
        print(f"{nome:28s} paráfrases r@5={m['parafrases']['revocacao_5']['acertos']}/{m['parafrases']['revocacao_5']['total']}"
              f" r@3={m['parafrases']['revocacao_3']['acertos']} mrr={m['parafrases']['mrr']}"
              f" | finais r@5={m['casos_finais']['revocacao_5']['acertos']}/{m['casos_finais']['revocacao_5']['total']}"
              f" | lat={m['parafrases']['latencia_mediana_ms']} ms | fora={m['documentos_fora_do_escopo']}")


def aplicar_criterio(ev: dict) -> dict:
    """Critério de rag-embeddings-criterio.md, aplicado à evidência sem ajuste manual."""
    lex = ev["metodos"]["lexical"]
    lex_p = lex["parafrases"]["revocacao_5"]["taxa"]
    lex_f = lex["casos_finais"]["revocacao_5"]["acertos"]
    avaliacao = {}
    for nome, m in ev["metodos"].items():
        if nome == "lexical":
            continue
        modelo = nome.split(":", 1)[1]
        download = ev["modelos"][modelo]["download_bytes"] or 0
        lat = max(m["parafrases"]["latencia_mediana_ms"], m["casos_finais"]["latencia_mediana_ms"])
        ganho_pp = round((m["parafrases"]["revocacao_5"]["taxa"] - lex_p) * 100, 1)
        regras = {
            "1_nao_piora_casos_finais": m["casos_finais"]["revocacao_5"]["acertos"] >= lex_f,
            "2_ganho_20pp_parafrases": ganho_pp >= 20.0,
            "4_download_ate_1_3GB": download <= 1.3e9,
            "4_latencia_mediana_ate_1s": lat <= 1000.0,
            "sem_documento_fora_do_escopo": not m["documentos_fora_do_escopo"],
        }
        avaliacao[nome] = {"modelo": modelo, "ganho_pp": ganho_pp, "download_bytes": download,
                           "latencia_mediana_ms": lat, "regras": regras, "passa": all(regras.values())}
    aprovados = [n for n, a in avaliacao.items() if a["passa"]]
    escolha = None
    if aprovados:
        acertos = {n: ev["metodos"][n]["parafrases"]["revocacao_5"]["acertos"] for n in aprovados}
        melhor = max(acertos.values())
        empatados = [n for n in aprovados if acertos[n] >= melhor - 1]  # regra 3: até 1 consulta é empate
        # regra 3: menor download; regra 5: mesmo modelo → maior revocação (já ordenado), depois o embedding sozinho
        empatados.sort(key=lambda n: (avaliacao[n]["download_bytes"], -acertos[n], 0 if n.startswith("hibrido") else 1))
        escolha = empatados[0]
    return {"avaliacao": avaliacao, "aprovados": aprovados, "escolha": escolha}


def _pct(m: dict) -> str:
    return f"{m['acertos']}/{m['total']} ({m['taxa'] * 100:.0f}%)"


def documento() -> None:
    ev = json.loads(EVIDENCIA.read_text(encoding="utf-8"))
    dec = aplicar_criterio(ev)
    L = ["# RAG com embeddings: medição e escolha",
         "",
         "Documento gerado por `ia/medir_rag_embeddings.py documento` a partir de "
         "[`sqlserver/evidence/parte3/rag-embeddings.json`](../sqlserver/evidence/parte3/rag-embeddings.json) "
         f"(medido em {ev['gerado_em']}). O critério foi fixado e versionado antes da medição: "
         "[`rag-embeddings-criterio.md`](rag-embeddings-criterio.md).",
         "",
         "## Modelos",
         "",
         "| Modelo | Download | Dimensão | Vetorizar os 20 documentos |",
         "|---|---:|---:|---:|"]
    for nome, m in ev["modelos"].items():
        L.append(f"| `{nome}` | {(m['download_bytes'] or 0) / 1e6:.0f} MB | {m['dimensao']} | {m['vetorizar_corpus_20_docs_ms']:.0f} ms |")
    L += ["", "## Resultado", "",
          "| Método | Paráfrases r@5 | Paráfrases r@3 | Paráfrases MRR | Casos finais r@5 | Latência mediana | Fora do escopo |",
          "|---|---:|---:|---:|---:|---:|---|"]
    for nome, m in ev["metodos"].items():
        lat = max(m["parafrases"]["latencia_mediana_ms"], m["casos_finais"]["latencia_mediana_ms"])
        L.append(f"| {nome} | {_pct(m['parafrases']['revocacao_5'])} | {_pct(m['parafrases']['revocacao_3'])} | "
                 f"{m['parafrases']['mrr']:.2f} | {_pct(m['casos_finais']['revocacao_5'])} | {lat:.0f} ms | "
                 f"{', '.join(m['documentos_fora_do_escopo']) or 'nenhum'} |")
    L += ["", "## Critério aplicado", "",
          "| Método | 1. Não piora os casos finais | 2. Ganho ≥ 20 pp | Ganho | 4. Download ≤ 1,3 GB | 4. Latência ≤ 1 s | Escopo | Passa |",
          "|---|---|---|---:|---|---|---|---|"]
    sim = lambda v: "sim" if v else "**não**"
    for nome, a in dec["avaliacao"].items():
        r = a["regras"]
        L.append(f"| {nome} | {sim(r['1_nao_piora_casos_finais'])} | {sim(r['2_ganho_20pp_parafrases'])} | "
                 f"{a['ganho_pp']:+.1f} pp | {sim(r['4_download_ate_1_3GB'])} | {sim(r['4_latencia_mediana_ate_1s'])} | "
                 f"{sim(r['sem_documento_fora_do_escopo'])} | {sim(a['passa'])} |")
    L += ["", "## Decisão", ""]
    if dec["escolha"]:
        a = dec["avaliacao"][dec["escolha"]]
        L.append(f"**{dec['escolha']}** (regra 3: maior revocação@5 nas paráfrases entre os aprovados; empate de até "
                 f"1 consulta vai para o menor download). Ganho de {a['ganho_pp']:+.1f} pp sobre a lexical nas paráfrases, "
                 "sem perder nenhum caso final.")
    else:
        L.append("Nenhum método passou em todas as regras: a busca continua **lexical** e o resultado fica registrado como achado.")
    L += ["", "## Consultas que a lexical perde", "",
          "| Consulta | Fontes | Lexical (top 5) | " + (f"{dec['escolha']} (top 5)" if dec["escolha"] else "") + " |",
          "|---|---|---|---|"]
    lex = {(d["conjunto"], d["id"]): d for d in ev["metodos"]["lexical"]["detalhe"]}
    esc = {(d["conjunto"], d["id"]): d for d in ev["metodos"][dec["escolha"]]["detalhe"]} if dec["escolha"] else {}
    for chave, d in lex.items():
        if set(d["fontes"]) <= set(d["top5"]):
            continue
        outro = ", ".join(esc[chave]["top5"]) if esc else ""
        L.append(f"| {d['id']} | {', '.join(d['fontes'])} | {', '.join(d['top5']) or '(nada)'} | {outro} |")
    if esc:
        perdidas = [d for d in esc.values() if not set(d["fontes"]) <= set(d["top5"])]
        L += ["", f"## Consultas que {dec['escolha']} ainda perde", ""]
        L += [f"- {d['id']}: precisava de {', '.join(d['fontes'])}; trouxe {', '.join(d['top5'])}." for d in perdidas] or ["- nenhuma"]
    linhas_aval = []
    for rotulo, nome in (("lexical (prompt v3.1)", "ia-avaliacao-prompt-v31.json"),
                         ("embedding ligado", "ia-avaliacao-rag-embeddings.json"),
                         ("final (embedding + regra de outra unidade + detector de 26/11)", "ia-avaliacao-final.json")):
        p = EVIDENCIA.parent / nome
        if not p.exists():
            continue
        a = json.loads(p.read_text(encoding="utf-8"))
        m, v = a["casos_de_teste"]["metricas"], (a.get("validacao_cega") or {}).get("metricas", {})
        mi = a["prompt_injection"]["metricas"]
        d = m["decisao_do_sistema"]
        linhas_aval.append(
            f"| {rotulo} ([`{nome}`](../sqlserver/evidence/parte3/{nome})) | {a['servico'].get('embed_model') or '—'} | "
            f"{m['casos_aprovados']}/{m['total']} | {d['acertos']}/{d['total']} | {len(m['falsas_aprovacoes'])} | "
            f"{mi['ataques_detectados']}/{mi['ataques']} | {v.get('ataques_detectados', '—')}/{v.get('ataques', '—')} | "
            f"{m['latencia_servidor_ms']['media']:.0f} ms |")
    if linhas_aval:
        L += ["", "## Avaliação completa da IA com o embedding ligado (critério 1)", "",
              "| Rodada | Modelo de embedding | Casos aprovados | Decisão certa | Falsas aprovações | Injeção detectada | "
              "1ª validação cega | Latência média |",
              "|---|---|---:|---:|---:|---:|---:|---:|"] + linhas_aval
    L += ["", "## Onde fica no sistema", "",
          "`ia/app.py` (`retrieve_with_method`): com `EMBED_MODEL` definido, os documentos do escopo são ordenados pelo cosseno "
          "entre o vetor da fatura e o de cada documento (os 20 vetores são calculados uma vez); sem a variável, ou se o "
          "Ollama falhar, a busca é a lexical. A resposta de `/api/analyze` informa a busca usada (`rag_method`). A decisão "
          "continua na regra sobre a evidência estruturada."]
    DOCUMENTO.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"escolha: {dec['escolha']}")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "documento"
    if modo == "medir":
        medir(Path(sys.argv[2]) if len(sys.argv) > 2 else EVIDENCIA)
    else:
        documento()
