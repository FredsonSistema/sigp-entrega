"""Dados da apresentação final, lidos das evidências (nenhum número digitado à mão).

Usado por gerar_apresentacao.py (página apresentacao.html) e gerar_relatorios.py (PDFs da apresentação e de limitações).
Cada bloco diz de qual arquivo veio, para a página mostrar a fonte de cada número.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
RAIZ = ENTREGA.parents[1]
EV3 = ENTREGA / "sqlserver" / "evidence" / "parte3"
EV2 = ENTREGA / "sqlserver" / "evidence" / "parte2"


def _json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8-sig")) if caminho.exists() else None


def _texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8-sig") if caminho.exists() else ""


def _tabela_pipe(texto: str, cabecalho_inicia: str) -> list[dict]:
    """Primeira tabela 'a|b|c' (saída do sqlcmd -s '|') cujo cabeçalho começa com o texto dado."""
    linhas = texto.splitlines()
    for i, l in enumerate(linhas):
        if l.startswith(cabecalho_inicia):
            nomes = l.split("|")
            out = []
            for x in linhas[i + 2:]:
                if not x.strip() or "|" not in x or len(x.split("|")) != len(nomes):
                    break
                out.append(dict(zip(nomes, x.split("|"))))
            return out
    return []


def _tabela_md(texto: str, cabecalho_inicia: str) -> list[dict]:
    """Primeira tabela markdown cujo cabeçalho começa com o texto dado."""
    linhas = texto.splitlines()
    for i, l in enumerate(linhas):
        if l.startswith(cabecalho_inicia):
            nomes = [c.strip() for c in l.strip().strip("|").split("|")]
            out = []
            for x in linhas[i + 2:]:
                if not x.startswith("|"):
                    break
                out.append(dict(zip(nomes, [c.strip() for c in x.strip().strip("|").split("|")])))
            return out
    return []


def _resumo_casos(av: dict | None) -> dict | None:
    if not av:
        return None
    c, i = av["casos_de_teste"], av["prompt_injection"]
    v = av.get("validacao_cega")
    return {
        "executado_em": av["executado_em_utc"],
        "casos": [{k: x.get(k) for k in ("id", "categoria", "descricao", "esperado", "obtido", "modelo", "motivo", "http", "fontes", "ok")}
                  for x in c["casos"]],
        "metricas": {
            "acertos": c["metricas"]["decisao_do_sistema"]["acertos"], "total": c["metricas"]["total"],
            "acuracia": c["metricas"]["decisao_do_sistema"]["acuracia"], "f1_macro": c["metricas"]["decisao_do_sistema"]["f1_macro"],
            "por_classe": c["metricas"]["decisao_do_sistema"]["por_classe"],
            "matriz": c["metricas"]["decisao_do_sistema"]["matriz_confusao_esperado_x_obtido"],
            "falsas_aprovacoes": c["metricas"]["falsas_aprovacoes"],
            "modelo_acertos": c["metricas"]["modelo_sozinho"]["acertos"],
            "modelo_concorda": c["metricas"]["modelo_concorda_com_a_regra"],
            "fontes": c["metricas"]["fontes_obrigatorias_citadas"], "seguranca": c["metricas"]["seguranca_ok"],
            "latencia": c["metricas"]["latencia_servidor_ms"],
        },
        "injecao": [{k: x.get(k) for k in ("id", "tecnica", "pede", "ataque", "esperado", "obtido", "detectado_como_injecao", "modelo")}
                    for x in i["casos"]],
        "injecao_metricas": i["metricas"],
        "validacao": ([{k: x.get(k) for k in ("id", "tecnica", "pede", "ataque", "esperado", "obtido", "detectado_como_injecao", "modelo")}
                       for x in v["casos"]] if v else None),
        "validacao_metricas": v["metricas"] if v else None,
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confiança de Wilson (95%) para k acertos em n: onde o acerto real provavelmente está."""
    if not n:
        return (0.0, 1.0)
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    meia = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5 / (1 + z * z / n)
    return (max(0.0, centro - meia), min(1.0, centro + meia))


def _confianca(depois: dict | None, ft: dict | None) -> dict:
    """Quanto cada proporção citada vale com amostras deste tamanho (Wilson, 95%)."""
    itens = []
    def add(rotulo, k, n, limpo, nota):
        inf, sup = wilson(k, n)
        itens.append({"rotulo": rotulo, "k": k, "n": n, "inf": inf, "sup": sup, "limpo": limpo, "nota": nota})
    if depois:
        m, im, vm = depois["metricas"], depois["injecao_metricas"], depois.get("validacao_metricas")
        add("Decisão certa nos casos de teste", m["acertos"], m["total"], False, "os casos foram olhados nas correções: otimista")
        add("Falsas aprovações nos casos de teste", len(m["falsas_aprovacoes"]), m["total"], False, "0 observadas não prova 0%: pode chegar ao limite superior")
        add("Ataques detectados na bateria", im["ataques_detectados"], im["ataques"], False, "os padrões foram ajustados nesta bateria: otimista")
        if vm:
            add("Ataques detectados na validação cega", vm["ataques_detectados"], vm["ataques"], True, "conjunto congelado, nunca usado para ajustar: a medida limpa")
    if ft:
        a = ft["conjuntos"]["A"]["ajustado_rag"]
        add("Fine-tuning (ajustado com RAG) nos casos finais", a["acertos"], a["n"], True, "fora do treino")
    trava = _json(ENTREGA / "ia" / "conjuntos-congelados.json") or {}
    return {"itens": itens, "metodo": "intervalo de Wilson, 95% (z = 1,96)",
            "congelados": {k: {"sha256": v["sha256"], "congelado_em": v["congelado_em"], "papel": v["papel"]} for k, v in trava.get("congelados", {}).items()}}


def _triagem_modelos() -> dict | None:
    """Escolha do modelo da triagem do Gmail: medição antes de escolher e o critério fixado antes (ia/escolha-modelo-*.md)."""
    ev = _json(EV3 / "triagem-modelos-corrigido.json") or _json(EV3 / "triagem-modelos.json")
    primeira = _json(EV3 / "triagem-modelos.json")
    if not ev:
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("gerar_escolha_modelo", ENTREGA / "ia" / "gerar_escolha_modelo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    variante = "corrigido" if any(d["variante"] == "corrigido" for d in ev["modelos"].values()) else "num_predict_512"
    dec = mod.decidir(ev["modelos"], variante)
    dec1 = mod.decidir(primeira["modelos"], "num_predict_512") if primeira else None
    linhas = []
    for d in list((primeira or {}).get("modelos", {}).values()) + ([] if ev is primeira else list(ev["modelos"].values())):
        r = d["resumo"]
        linhas.append({"modelo": d["modelo"], "variante": d["variante"], "tamanho": d.get("tamanho"),
                       "campos": f"{r['campos_certos']}/{r['campos_total']}", "validas": f"{r['json_valido']}/{len(d['casos'])}",
                       "esgotado": r.get("tempo_esgotado", 0), "graves": len(r["erros_graves"]),
                       "media_s": round(r["latencia_ms"]["media"] / 1000, 1) if r["latencia_ms"]["media"] is not None else None,
                       "por_campo": r["por_campo"]})
    return {"executado_em": ev["executado_em_utc"], "documentos": len(ev["documentos"]), "linhas": linhas, "passos": dec["passos"],
            "escolha": dec["opcao"], "padrao": dec["padrao"], "opcional": dec["opcional"], "primeira_escolha": dec1 and dec1["opcao"],
            "fonte": "sqlserver/evidence/parte3/triagem-modelos.json e triagem-modelos-corrigido.json · ia/escolha-modelo-criterio.md · ia/escolha-modelo-triagem.md"}


def _finetuning() -> dict | None:
    d = _json(EV3 / "finetuning-comparacao.json")
    if not d:
        return None
    out = {"executado_em": d["executado_em_utc"], "custo_parametros": d["custo_parametros"], "conjuntos": {}}
    for chave, nome in (("conjunto_a_casos_finais", "A"), ("conjunto_b_teste_do_treino", "B")):
        cfgs = d[chave]["configuracoes"]
        out["conjuntos"][nome] = {
            k: {"nome": v["nome"], "rag": v["rag"], "adaptador": v["adaptador"],
                "acertos": v["metricas"]["acertos"], "n": v["metricas"]["n"], "acuracia": v["metricas"]["acuracia"],
                "f1": v["metricas"]["f1_macro"], "falsas": len(v["metricas"]["falsas_aprovacoes"]),
                "latencia_media_ms": v["metricas"]["latencia_ms"]["media"], "latencia_p95_ms": v["metricas"]["latencia_ms"]["p95"],
                "tokens": v["metricas"]["tokens_entrada_media"], "custo": v["metricas"]["custo_por_1000_usos"],
                "respostas": {c: sum(1 for x in v["casos"] if x["obtido"] == c) for c in ("CONTRATADO", "DIVERGENTE", "REVISAR")}}
            for k, v in cfgs.items()}
    return out


def _latencia() -> dict:
    out = {}
    for nome, arq in (("fatura_nova_sem_carga", "latencia-custo-final.json"), ("fatura_nova_com_carga", "latencia-custo-final-sob-carga.json"),
                      ("faturas_ja_vistas_cache", "latencia-custo-final-cache.json"),
                      ("prompt31_fatura_nova", "latencia-custo-prompt-v31.json")):
        d = _json(EV3 / arq)
        if d:
            out[nome] = {"latencia": d["latencia_servidor_ms"], "custo": d["custo_por_1000_usos"], "cpu": d.get("cpu_maquina_percent"),
                         "fonte": f"sqlserver/evidence/parte3/{arq}"}
    fria = _json(EV3 / "latencia-partida-fria.json")
    if fria:
        out["partida_fria"] = {"primeira_ms": fria["primeira_apos_descarregar"]["cliente_ms"], "seguinte_ms": fria["logo_depois"]["cliente_ms"],
                               "prompt_version": fria["prompt_version"], "fonte": "sqlserver/evidence/parte3/latencia-partida-fria.json"}
    rep = _json(EV3 / "latencia-custo-sob-carga.json")
    if rep:
        out["mesma_fatura_repetida"] = {"latencia": rep["api_academica_ponta_a_ponta"]["total_ms"], "fonte": "sqlserver/evidence/parte3/latencia-custo-sob-carga.json",
                                        "ollama": [{"modelo": o["modelo"], "mediana_ms": o["total_ms"]["mediana"]} for o in rep["ollama"]]}
    return out


def _otimizacao() -> dict:
    d = EV3 / "otimizacao"
    tempos = _tabela_pipe(_texto(d / "tempos.txt"), "configuracao|consulta")
    verif = _tabela_pipe(_texto(d / "tempos.txt"), "verificacao|")
    leituras, cfg, cons = {}, None, None
    for l in _texto(d / "leituras-logicas.txt").splitlines():
        if m := re.match(r"### Configura\w+ (\w)", l):
            cfg = m.group(1)
        elif m := re.match(r"### CONSULTA (\d)", l):
            cons = m.group(1)
        elif m := re.match(r"Table '(\w+)'\. Scan count \d+, logical reads (\d+)", l):
            if m.group(1) != "LocalScope":
                leituras[f"{cfg}{cons}"] = leituras.get(f"{cfg}{cons}", 0) + int(m.group(2))
    resumo = _texto(d / "resumo-testes.txt")
    return {
        "tempos": [{"cfg": t["configuracao"], "consulta": int(t["consulta"]), "mediana": float(t["mediana_ms"]),
                    "p95": float(t["p95_ms"]), "leituras": leituras.get(f"{t['configuracao']}{t['consulta']}")} for t in tempos],
        "mesma_resposta": verif[0] if verif else None,
        "testes_resumo": _tabela_pipe(resumo, "teste|"),
        "custo_gravacao": _tabela_pipe(resumo, "tipo|modo"),
        "fonte": "sqlserver/evidence/parte3/otimizacao/",
    }


def _seguranca() -> dict:
    esc = _tabela_pipe(_texto(EV3 / "escalonamento.txt"), "fase|id")
    trilha = {}
    for fase in ("antes", "depois"):
        trilha[fase] = _tabela_pipe(_texto(EV3 / "auditoria" / f"trilha-{fase}.txt"), "id|teste")
    perfis = _json(EV3 / "ia-perfis.json") or {}
    matriz = _json(EV3 / "matriz-permissoes.json") or {}
    segredos = _json(EV3 / "segredos-n8n.json") or {}
    return {
        "escalonamento": esc,
        "trilha": trilha,
        "ia_perfis": {
            "resultado": perfis.get("resultado"),
            "parte_a": [{"id": c["id"], "perfil": c["perfil"], "http": c["http"], "classificacao": c["resposta"].get("classification"),
                         "ok": c["ok"], "vazamentos": c["vazamentos"]} for c in perfis.get("parte_a_pela_ia", [])],
            "parte_b": [{k: x.get(k) for k in ("perfil", "local_pedido", "resultado", "linhas", "erro", "ok")} for x in perfis.get("parte_b_pelo_banco", [])],
            "parte_d": [{k: x.get(k) for k in ("id", "tentativa", "resultado", "erro", "ok")} for x in perfis.get("parte_d_falsificar_auditoria", [])],
        },
        "matriz": {"principais": matriz.get("principais", []), "permissoes": matriz.get("matriz", []),
                   "denys": len(matriz.get("denys", [])), "prova_deny": matriz.get("prova_deny", [])},
        "segredos": {k: segredos.get(k) for k in ("resultado", "segredos_procurados", "arquivos_do_repositorio", "workflows_ao_vivo",
                                                   "arquivos_com_falha", "arquivos_com_aviso")},
        "ledger": _ledger(),
        "tde": _json(EV3 / "tde-verificacao.json"),
    }


def _ledger() -> dict | None:
    """Trilha à prova de adulteração: o que o sa fazia antes (cópia do backup) e a verificação depois."""
    ver = _json(EV3 / "ledger-verificacao.json")
    if not ver:
        return None
    antes = {}
    for l in _texto(EV3 / "ledger-antes.txt").splitlines():
        m = re.match(r"(UPDATE|DELETE): PERMITIDO \((\d+) eventos", l)
        if m:
            antes[m.group(1)] = int(m.group(2))
    return {"resultado": ver["resultado"], "verificacoes": ver["verificacoes"], "antes": antes,
            "digests": ver["digests_desta_instalacao"], "migracao": ver["evento_de_migracao"]["detalhe"],
            "fonte": "sqlserver/evidence/parte3/ledger-antes.txt e ledger-verificacao.json"}


def _evolucao_llm() -> dict:
    p2 = _json(EV2 / "ai-test-results.json") or {}
    treino = _json(ENTREGA / "ia" / "finetuning" / "training-results.json") or {}
    wf06 = _json(RAIZ / "n8n" / "wf06" / "evidence" / "avaliacao-alertas.json") or {}
    # Toda linha "| vX.Y | estado | mudanças |", inclusive as que ficaram fora da tabela no CHANGELOG (v5.0).
    prompts = []
    for l in _texto(ENTREGA / "ia" / "prompts" / "CHANGELOG.md").splitlines():
        if re.match(r"^\|\s*v\d", l):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 3:
                prompts.append({"Versão": c[0], "Estado": c[1], "Mudanças": " | ".join(c[2:])})
    return {
        "prompts": [{"versao": p["Versão"], "estado": p["Estado"], "mudancas": re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", p["Mudanças"])}
                    for p in prompts],
        "entrega2": {"casos": p2.get("case_count"), "decisao_certa": p2.get("decision_pass_count"), "modelo_concorda": p2.get("model_agreement_count")},
        "treino_lora": {"base": treino.get("baseline", {}).get("test", {}).get("accuracy"),
                        "ajustado": treino.get("finetuned", {}).get("test", {}).get("accuracy"),
                        "f1_base": treino.get("baseline", {}).get("test", {}).get("macro_f1"),
                        "f1_ajustado": treino.get("finetuned", {}).get("test", {}).get("macro_f1"),
                        "exemplos_treino": treino.get("trainable_examples"), "segundos": treino.get("elapsed_seconds")},
        "wf06_alertas": {"modelo": wf06.get("modelo"), "cenarios": wf06.get("cenarios"), "llm_aceitas": wf06.get("aberturas_da_llm_aceitas"),
                         "texto_padrao": wf06.get("texto_padrao"), "latencia_mediana_ms": wf06.get("latencia_mediana_ms")},
    }


def _historico() -> list[dict]:
    linhas = _tabela_md(_texto(ENTREGA / "historico-evolucao.md"), "| #")
    out = []
    for l in linhas:
        primeira = l.get("1ª execução", "")
        tipo = ("LIMITAÇÃO" if "LIMITA" in l.get("Commit", "") or primeira.startswith("LIMITA") or "não compensou" in primeira or "4/8" in primeira
                else "ERRO DO TESTE" if "ERRO DO TESTE" in primeira else "REPROVADO" if "REPROVADO" in primeira else "AJUSTE")
        out.append({"id": l["#"], "data": l["Data"], "area": l["Área"], "teste": l["O que foi testado"], "primeira": primeira.replace("**", ""),
                    "correcao": l["Correção"], "reteste": l["Reteste"], "commit": l["Commit"].strip("`"), "tipo": tipo})
    return out


def carregar() -> dict:
    ident = _json(ENTREGA / "identificacao.json") or {}
    return {
        "projeto": {"repositorio": ident.get("repositorio"), "repositorio_pacote": ident.get("repositorio_pacote"), "disciplinas": ident.get("disciplinas", []),
                    "integrantes": [{"nome": i["nome"], "contribuicao": i.get("contribuicao_final") or i.get("contribuicao", "")} for i in ident.get("integrantes", [])]},
        "ia_antes": _resumo_casos(_json(EV3 / "ia-avaliacao-antes.json")),
        "ia_depois": _resumo_casos(_json(EV3 / "ia-avaliacao-depois.json")),
        "finetuning": _finetuning(),
        "latencia": _latencia(),
        "otimizacao": _otimizacao(),
        "seguranca": _seguranca(),
        "evolucao_llm": _evolucao_llm(),
        "historico": _historico(),
        "triagem_modelos": _triagem_modelos(),
        "confianca": _confianca(_resumo_casos(_json(EV3 / "ia-avaliacao-depois.json")), _finetuning()),
    }


if __name__ == "__main__":
    d = carregar()
    print(json.dumps({k: (type(v).__name__, len(v) if hasattr(v, "__len__") else v) for k, v in d.items()}, ensure_ascii=False, indent=1))
