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
        "servico": {k: (av.get("servico") or {}).get(k) for k in ("model", "prompt_version", "prompt_sha256", "embed_model", "database_scope")},
        "fora": ({"casos": [{k: x.get(k) for k in ("id", "categoria", "descricao", "esperado", "obtido", "modelo", "ok")}
                            for x in av["fora_de_escopo"]["casos"]],
                  "acertos": av["fora_de_escopo"]["metricas"]["decisao_do_sistema"]["acertos"],
                  "total": av["fora_de_escopo"]["metricas"]["total"],
                  "falsas_aprovacoes": av["fora_de_escopo"]["metricas"]["falsas_aprovacoes"],
                  "seguranca": av["fora_de_escopo"]["metricas"]["seguranca_ok"]}
                 if av.get("fora_de_escopo") else None),
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
        if depois.get("fora"):
            f = depois["fora"]
            add("Decisão certa nos casos fora de escopo", f["acertos"], f["total"], False, "escrito antes de rodar; 1 falha corrigida olhando para ele")
        if vm:
            add("Ataques detectados na validação cega", vm["ataques_detectados"], vm["ataques"], True, "conjunto congelado, nunca usado para ajustar: a medida limpa")
    if ft:
        a = ft["conjuntos"]["A"]["ajustado_rag"]
        add("Fine-tuning (ajustado com RAG) nos casos finais", a["acertos"], a["n"], True, "fora do treino")
        if "C" in ft["conjuntos"]:
            c = ft["conjuntos"]["C"]["ajustado_rag"]
            add("Fine-tuning (ajustado com RAG) fora de escopo", c["acertos"], c["n"], True, "nenhum caso parecido com o treino")
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
    out = {"executado_em": d["executado_em_utc"], "custo_parametros": d["custo_parametros"], "conjuntos": {}, "rag": d.get("rag")}
    for chave, nome in (("conjunto_a_casos_finais", "A"), ("conjunto_b_teste_do_treino", "B"), ("conjunto_c_fora_de_escopo", "C")):
        if chave not in d:
            continue
        cfgs = d[chave]["configuracoes"]
        out["conjuntos"][nome] = {
            k: {"nome": v["nome"], "rag": v["rag"], "adaptador": v["adaptador"],
                "acertos": v["metricas"]["acertos"], "n": v["metricas"]["n"], "acuracia": v["metricas"]["acuracia"],
                "f1": v["metricas"]["f1_macro"], "falsas": len(v["metricas"]["falsas_aprovacoes"]), "falsas_ids": v["metricas"]["falsas_aprovacoes"],
                "latencia_media_ms": v["metricas"]["latencia_ms"]["media"], "latencia_p95_ms": v["metricas"]["latencia_ms"]["p95"],
                "tokens": v["metricas"]["tokens_entrada_media"], "custo": v["metricas"]["custo_por_1000_usos"],
                "respostas": {c: sum(1 for x in v["casos"] if x["obtido"] == c) for c in ("CONTRATADO", "DIVERGENTE", "REVISAR")}}
            for k, v in cfgs.items()}
    return out


def _rag() -> dict | None:
    """RAG com embeddings: medição, critério aplicado e escolha (ia/medir_rag_embeddings.py)."""
    ev = _json(EV3 / "rag-embeddings.json")
    if not ev:
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("medir_rag_embeddings", ENTREGA / "ia" / "medir_rag_embeddings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dec = mod.aplicar_criterio(ev)
    metodos = {k: {"parafrases": v["parafrases"]["revocacao_5"], "finais": v["casos_finais"]["revocacao_5"],
                   "mrr": v["parafrases"]["mrr"], "latencia_ms": max(v["parafrases"]["latencia_mediana_ms"], v["casos_finais"]["latencia_mediana_ms"]),
                   "fora_do_escopo": v["documentos_fora_do_escopo"]} for k, v in ev["metodos"].items()}
    return {"executado_em": ev["gerado_em"], "metodos": metodos, "escolha": dec["escolha"],
            "ganho_pp": dec["avaliacao"][dec["escolha"]]["ganho_pp"] if dec["escolha"] else None,
            "modelos": {k: {"download_mb": round((v["download_bytes"] or 0) / 1e6)} for k, v in ev["modelos"].items()},
            "fonte": "sqlserver/evidence/parte3/rag-embeddings.json · ia/rag-embeddings-criterio.md · ia/rag-embeddings.md"}


def _sobreposicao() -> dict | None:
    s = _json(EV3 / "sobreposicao-treino.json")
    if not s:
        return None
    fora = [x for x in s["casos"] if x["conjunto"] == "casos-fora-escopo.json"]
    return {"casos": s["casos_de_teste"], "treino": s["exemplos_de_treino"], "repetem": s["casos_que_repetem_o_treino"],
            "limite": s["limite_parecido_jaccard"], "provedores_em_comum": s["provedores_em_comum"],
            "maior_fora": max(x["semelhanca"] for x in fora) if fora else None}


def _respostas(d: dict) -> list[dict]:
    """Uma linha por comentário da Prof.ª Bruna (devolutiva da Entrega 2), com a resposta e a evidência, tudo calculado."""
    B, F, R, O, S, SB = d["ia_depois"], d["finetuning"], d.get("rag"), d["otimizacao"], d["seguranca"], d.get("sobreposicao")
    q = {(x["cfg"], x["consulta"]): x for x in O["tempos"]}
    sv = B["servico"]
    out = []
    out.append({"disciplina": "IA", "comentario": "O relatório cita a v4.2 como prompt atual, enquanto o fluxo avaliado ainda roda a v3.0.",
                "resposta": f"Cada fluxo tem o seu prompt: a análise de fatura avaliada (/api/analyze) usa o v{sv['prompt_version']} e a triagem do "
                            "Gmail (WF-08/WF-10), o v4.2. A avaliação final foi feita no serviço com o mesmo prompt, modelo e busca que o "
                            "pacote de entrega sobe, e um teste falha se o pacote divergir da evidência.",
                "evidencia": "ia/prompts/CHANGELOG.md (Qual prompt cada fluxo usa hoje) · ia/casos-de-teste-final.md · tests/test_pacote_mesma_ia.py"})
    if R and R["escolha"]:
        lex, esc = R["metodos"]["lexical"], R["metodos"][R["escolha"]]
        out.append({"disciplina": "IA", "comentario": "RAG com embeddings.",
                    "resposta": f"Busca por embedding ({R['escolha'].split(':', 1)[1]}, no Ollama local) escolhida por critério versionado antes "
                                f"da medição, entre 3 modelos e a busca híbrida: fonte certa em {esc['parafrases']['acertos']}/{esc['parafrases']['total']} "
                                f"paráfrases contra {lex['parafrases']['acertos']}/{lex['parafrases']['total']} da lexical, sem perder nenhum caso final "
                                f"({esc['finais']['acertos']}/{esc['finais']['total']}) e sem documento de outro local. Ligada no sistema entregue.",
                    "evidencia": R["fonte"]})
    if B.get("fora"):
        f = B["fora"]
        out.append({"disciplina": "IA", "comentario": "Mais casos de teste, incluindo fora de escopo.",
                    "resposta": f"{f['total']} casos fora de escopo (outra conta, outro local, outro idioma, não é fatura), com o esperado escrito antes "
                                f"de rodar. A 1ª rodada achou uma falsa aprovação (fatura de outra unidade aprovada com o contrato da Agência "
                                f"Centro), corrigida; final {f['acertos']}/{f['total']}, segurança {f['seguranca']}.",
                    "evidencia": "ia/casos-fora-escopo.json · ia/casos-de-teste-final.md · ia-avaliacao-final.json"})
    if F and "C" in F["conjuntos"]:
        a, c = F["conjuntos"]["A"]["ajustado_rag"], F["conjuntos"]["C"]["ajustado_rag"]
        out.append({"disciplina": "IA", "comentario": "Fine-tuning medido em cenários fora do treino.",
                    "resposta": f"Medido nos casos finais ({a['acertos']}/{a['n']}) e nos fora de escopo ({c['acertos']}/{c['n']}), com o RAG do sistema "
                                f"entregue; no teste do próprio treino, {F['conjuntos']['B']['ajustado_rag']['acertos']}/{F['conjuntos']['B']['ajustado_rag']['n']}. "
                                + (f"A sobreposição com os {SB['treino']} exemplos de treino foi conferida caso a caso: nenhum provedor em comum; os "
                                   f"{len(SB['repetem'])} casos que usam o nome de serviço do treino saem separados. " if SB else "")
                                + "Conclusão: o ajuste não generaliza fora do treino.",
                    "evidencia": "ia/finetuning/comparacao-final.md · finetuning-comparacao.json · sobreposicao-treino.json"})
    out.append({"disciplina": "BD", "comentario": "Explicar nos planos o que mudou (scan × seek, custo).",
                "resposta": "Cada operador dos planos reais lido do XML: tipo de acesso (scan ou seek), linhas lidas e devolvidas, custo próprio "
                            "e da consulta, por configuração, com o porquê da mudança.",
                "evidencia": "seguranca/otimizacao-consultas.md (seção \"O que mudou no plano\") · evidence/parte3/otimizacao/*.sqlplan"})
    out.append({"disciplina": "BD", "comentario": "Melhorar a consulta 1 (ganho ainda pequeno).",
                "resposta": f"Só com índice o ganho era {br_(q[('A', 1)]['mediana'] / q[('C', 1)]['mediana'])}× (o plano mostra que sobra somar as notas da janela). "
                            f"Com o resumo diário (desnormalização com gatilho e RLS): {br_(q[('A', 1)]['mediana'])} → {br_(q[('D', 1)]['mediana'])} ms "
                            f"({br_(q[('A', 1)]['mediana'] / q[('D', 1)]['mediana'])}×) e {br_(q[('A', 1)]['leituras'], 0)} → {br_(q[('D', 1)]['leituras'], 0)} leituras lógicas, "
                            "com a mesma resposta.",
                "evidencia": "seguranca/otimizacao-consultas.md · evidence/parte3/otimizacao/"})
    L = S.get("ledger")
    if L:
        out.append({"disciplina": "BD", "comentario": "Proteger a tabela de auditoria contra alteração.",
                    "resposta": f"audit.Eventos virou tabela ledger só de inserção: antes o sa reescrevia {L['antes'].get('UPDATE', '?')} e apagava "
                                f"{L['antes'].get('DELETE', '?')} eventos; agora ninguém altera nem apaga (erro 37359), e a trilha é conferida contra o "
                                f"digest guardado fora do banco ({L['resultado']}).",
                    "evidencia": L["fonte"]})
    out.append({"disciplina": "IA e BD", "comentario": "Repositório só com a parte acadêmica, com commits de todos os integrantes.",
                "resposta": "Repositório de entrega separado (pacote com base fictícia, instalação em um comando). Commits de cada integrante: "
                            "cada um faz os seus, na própria conta.",
                "evidencia": d["projeto"].get("repositorio_pacote") or "—"})
    return out


def br_(v, casas=1):
    return f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
    d = _carregar()
    d["respostas_professora"] = _respostas(d)
    return d


def _carregar() -> dict:
    ident = _json(ENTREGA / "identificacao.json") or {}
    return {
        "projeto": {"repositorio": ident.get("repositorio"), "repositorio_pacote": ident.get("repositorio_pacote"), "disciplinas": ident.get("disciplinas", []),
                    "integrantes": [{"nome": i["nome"], "contribuicao": i.get("contribuicao_final") or i.get("contribuicao", "")} for i in ident.get("integrantes", [])]},
        "ia_antes": _resumo_casos(_json(EV3 / "ia-avaliacao-antes.json")),
        # "depois" = a rodada final, no serviço com o mesmo prompt, modelo e busca do pacote entregue.
        "ia_depois": _resumo_casos(_json(EV3 / "ia-avaliacao-final.json")),
        "finetuning": _finetuning(),
        "latencia": _latencia(),
        "otimizacao": _otimizacao(),
        "seguranca": _seguranca(),
        "evolucao_llm": _evolucao_llm(),
        "historico": _historico(),
        "triagem_modelos": _triagem_modelos(),
        "confianca": _confianca(_resumo_casos(_json(EV3 / "ia-avaliacao-final.json")), _finetuning()),
        "rag": _rag(),
        "sobreposicao": _sobreposicao(),
    }


if __name__ == "__main__":
    d = carregar()
    print(json.dumps({k: (type(v).__name__, len(v) if hasattr(v, "__len__") else v) for k, v in d.items()}, ensure_ascii=False, indent=1))
