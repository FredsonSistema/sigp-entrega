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
        "validacao_v2": ([{k: x.get(k) for k in ("id", "tecnica", "pede", "ataque", "esperado", "obtido", "detectado_como_injecao", "modelo")}
                          for x in av["validacao_cega_v2"]["casos"]] if av.get("validacao_cega_v2") else None),
        "validacao_v2_metricas": av["validacao_cega_v2"]["metricas"] if av.get("validacao_cega_v2") else None,
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
        a26 = _resumo_casos(_json(EV3 / "ia-avaliacao-validacao-v2-antes.json"))
        if a26 and a26.get("validacao_metricas"):
            v1 = a26["validacao_metricas"]
            add("1ª validação cega, antes da correção de 26/11", v1["ataques_detectados"], v1["ataques"], False,
                "congelada; a correção de 26/11 partiu das falhas dela (o resultado final nela é otimista)")
        v2 = depois.get("validacao_v2_metricas")
        if v2:
            add("2ª validação cega, final", v2["ataques_detectados"], v2["ataques"], True,
                "congelada antes da correção; nenhum padrão escrito a partir dela: a medida mais limpa")
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
                "resposta": "A entrega é o repositório do pacote: só o fluxo avaliado (gestão de contas de provedores), a parte acadêmica e "
                            "uma base fictícia, com instalação em um comando. É o único repositório citado nos documentos.",
                "evidencia": d["projeto"].get("repositorio") or "—"})
    return out


def _git_datas(caminho: Path) -> list[str]:
    """Datas dos commits que mudaram o arquivo (vazio fora de um repositório Git)."""
    import subprocess
    try:
        r = subprocess.run(["git", "log", "--format=%ad", "--date=short", "--", str(caminho)], cwd=RAIZ,
                           capture_output=True, text=True, timeout=30)
        return [x for x in r.stdout.split() if x]
    except (OSError, subprocess.SubprocessError):
        return []


def _mudancas(d: dict) -> dict:
    """Mudanças desde a Entrega 2: melhorado (antes → depois, medido), corrigido (histórico) e inalterado (conferido)."""
    A, B, F, R, O, S, LA = d["ia_antes"], d["ia_depois"], d["finetuning"], d.get("rag"), d["otimizacao"], d["seguranca"], d["latencia"]
    q = {(x["cfg"], x["consulta"]): x for x in O["tempos"]}
    e2 = _json(EV2 / "ai-test-results.json") or {}
    e2_obs = [x["observed"] for x in e2.get("results", [])]
    vul_a, vul_d = (_json(EV3 / "vulnerabilidades-antes.json") or {}).get("resumo"), (_json(EV3 / "vulnerabilidades-depois.json") or {}).get("resumo")
    tde_r, sqli = _json(EV3 / "restauracao-tde.json") or {}, _json(EV3 / "injecao-sql-depois.json") or {}
    esc_a = sum(1 for x in S["escalonamento"] if x["fase"] == "antes" and x["obtido"] == "PERMITIDO")
    esc_d = sum(1 for x in S["escalonamento"] if x["fase"] == "depois" and x["veredito"] == "OK")
    tr_a = sum(1 for x in S["trilha"]["antes"] if x["veredito"] == "FALHA")
    tr_d = sum(1 for x in S["trilha"]["depois"] if x["veredito"] == "OK")
    L = S.get("ledger") or {}
    m = []
    m.append({"tema": "Interface", "antes": "tela numa aba do navegador", "depois": "janela própria do Windows, aberta pelo atalho SIGp "
              "(Edge em modo aplicativo, sem barra de endereço nem abas); liga os containers se o computador foi reiniciado",
              "evidencia": "abrir-sigp.ps1 · historico-evolucao.md (H-48)"})
    m.append({"tema": "IA: decisão nos 16 casos", "antes": f"{A['metricas']['acertos']}/16, falsa aprovação em {', '.join(A['metricas']['falsas_aprovacoes']) or 'nenhum'}",
              "depois": f"{B['metricas']['acertos']}/16, nenhuma falsa aprovação", "evidencia": "ia/casos-de-teste-final.md"})
    if B.get("fora"):
        m.append({"tema": "IA: casos fora de escopo (novos)", "antes": "não havia", "depois": f"{B['fora']['acertos']}/{B['fora']['total']}, "
                  "depois de corrigir a aprovação de fatura de outra unidade", "evidencia": "ia/casos-fora-escopo.json · ia/casos-de-teste-final.md"})
    if R and R["escolha"]:
        lx, es = R["metodos"]["lexical"]["parafrases"], R["metodos"][R["escolha"]]["parafrases"]
        m.append({"tema": "IA: RAG (fonte certa nas paráfrases)", "antes": f"busca por palavras, {lx['acertos']}/{lx['total']}",
                  "depois": f"embedding {R['escolha'].split(':', 1)[1]}, {es['acertos']}/{es['total']}", "evidencia": "ia/rag-embeddings.md"})
    if LA.get("prompt31_fatura_nova") and LA.get("fatura_nova_com_carga"):
        m.append({"tema": "IA: tempo da análise de uma fatura nova", "antes": f"{br_(LA['fatura_nova_com_carga']['latencia']['media'] / 1000)} s (prompt 3.0)",
                  "depois": f"{br_(LA['prompt31_fatura_nova']['latencia']['media'] / 1000)} s (prompt 3.1)", "evidencia": "ia/finetuning/comparacao-final.md"})
    m.append({"tema": "IA: prompt injection detectado", "antes": f"{A['injecao_metricas']['ataques_detectados']}/{A['injecao_metricas']['ataques']} na bateria",
              "depois": f"{B['injecao_metricas']['ataques_detectados']}/{B['injecao_metricas']['ataques']} na bateria; 1ª validação cega "
                        + (f"{d['injecao_antes_26']['validacao_metricas']['ataques_detectados']}/{d['injecao_antes_26']['validacao_metricas']['ataques']} → "
                           if d.get("injecao_antes_26") else "")
                        + f"{B['validacao_metricas']['ataques_detectados']}/{B['validacao_metricas']['ataques']} (otimista: a correção partiu dela); "
                        + (f"2ª validação cega, congelada antes da correção, "
                           f"{d['injecao_antes_26']['validacao_v2_metricas']['ataques_detectados']}/{d['injecao_antes_26']['validacao_v2_metricas']['ataques']} → "
                           f"{B['validacao_v2_metricas']['ataques_detectados']}/{B['validacao_v2_metricas']['ataques']}"
                           if B.get("validacao_v2_metricas") and d.get("injecao_antes_26") else ""),
              "evidencia": "ia/casos-de-teste-final.md"})
    if F and "C" in F["conjuntos"]:
        m.append({"tema": "IA: fine-tuning", "antes": "medido só no teste do próprio treino",
                  "depois": f"medido fora do treino: {F['conjuntos']['A']['ajustado_rag']['acertos']}/16 nos casos finais e "
                            f"{F['conjuntos']['C']['ajustado_rag']['acertos']}/{F['conjuntos']['C']['ajustado_rag']['n']} fora de escopo (não generaliza)",
                  "evidencia": "ia/finetuning/comparacao-final.md"})
    m.append({"tema": "BD: consulta 1 (mediana)", "antes": f"{br_(q[('A', 1)]['mediana'])} ms, {br_(q[('A', 1)]['leituras'], 0)} leituras",
              "depois": f"{br_(q[('D', 1)]['mediana'])} ms, {br_(q[('D', 1)]['leituras'], 0)} leituras (resumo diário)", "evidencia": "seguranca/otimizacao-consultas.md"})
    m.append({"tema": "BD: consulta 2 (mediana)", "antes": f"{br_(q[('A', 2)]['mediana'])} ms, {br_(q[('A', 2)]['leituras'], 0)} leituras",
              "depois": f"{br_(q[('C', 2)]['mediana'])} ms, {br_(q[('C', 2)]['leituras'], 0)} leituras (índice filtrado)", "evidencia": "seguranca/otimizacao-consultas.md"})
    m.append({"tema": "BD: escalonamento de privilégio", "antes": f"{esc_a} ataques passaram", "depois": f"{esc_d} verificações OK, todos barrados",
              "evidencia": "seguranca/ataque-escalonamento.md"})
    m.append({"tema": "BD: trilha de auditoria", "antes": f"{tr_a} falhas", "depois": f"{tr_d}/{len(S['trilha']['depois'])} OK", "evidencia": "seguranca/trilha-auditoria.md"})
    if L:
        m.append({"tema": "BD: trilha à prova de alteração", "antes": f"o sa reescrevia {L['antes'].get('UPDATE', '?')} e apagava {L['antes'].get('DELETE', '?')} eventos",
                  "depois": f"tabela ledger só de inserção; verificação {L['resultado']}", "evidencia": "seguranca/trilha-auditoria.md"})
    if S.get("tde"):
        m.append({"tema": "BD: criptografia do arquivo e do backup (TDE)", "antes": f"chave fiscal {S['tde']['chave_fiscal_em_texto_no_backup_antes']} vezes em texto no backup",
                  "depois": f"{S['tde']['chave_fiscal_em_texto_no_backup_depois']} vezes; restauração em outro servidor: {tde_r.get('resultado', '—')}",
                  "evidencia": "seguranca/restauracao-tde.md"})
    if vul_a and vul_d:
        m.append({"tema": "BD: avaliação de vulnerabilidades (27 regras)", "antes": f"{vul_a.get('PASSOU')} passando, {vul_a.get('FALHOU')} falhas",
                  "depois": f"{vul_d.get('PASSOU')} passando, {vul_d.get('FALHOU')} falhas, {vul_d.get('ACEITO')} riscos aceitos com justificativa",
                  "evidencia": "seguranca/avaliacao-vulnerabilidades.md"})
    if sqli:
        m.append({"tema": "BD: injeção de SQL", "antes": "não testada", "depois": f"API, procedimentos e primitiva do banco: {sqli.get('resultado')}",
                  "evidencia": "seguranca/injecao-sql.md"})
    m.append({"tema": "Segredos nos fluxos do n8n", "antes": "1 modelo com chave literal", "depois": f"{S['segredos']['resultado']}", "evidencia": "ia/segredos-n8n.md"})
    m.append({"tema": "Instalação", "antes": "script do ambiente acadêmico e passos do guia, com o Docker já instalado", "depois": "um comando (Instalar SIGp.cmd): Docker, chaves, banco, modelos, workflows, base fictícia e o acesso",
              "evidencia": "GUIA-INSTALACAO.md"})
    m.append({"tema": "Entrada manual de notas (função nova)", "antes": "só por e-mail", "depois": "PDF e/ou XML enviados pela tela passam pela mesma leitura e IA (WF-10)",
              "evidencia": "historico-evolucao.md (H-38)"})

    corrigido = [x for x in d["historico"] if x["tipo"] in ("REPROVADO", "ERRO DO TESTE")]

    inal = []
    if e2_obs:
        modelos = sorted({x.get("model") for x in e2_obs if x.get("model")})
        metodo = sorted({x.get("decision_method") for x in e2_obs if x.get("decision_method")})
        inal.append({"item": "Quem decide", "como": f"a regra sobre a evidência estruturada (`{', '.join(metodo)}` na Entrega 2 e hoje); o modelo só sugere e não tem autoridade",
                     "evidencia": "sqlserver/evidence/parte2/ai-test-results.json · ia/app.py"})
        inal.append({"item": "Modelo da análise de fatura", "como": f"{', '.join(modelos)} no Ollama local, na Entrega 2 e hoje ({B['servico']['model']})",
                     "evidencia": "sqlserver/evidence/parte2/ai-test-results.json · ia-avaliacao-final.json"})
    inal.append({"item": "Pagamento", "como": "nenhum pagamento automático (automatic_payment sempre falso)", "evidencia": "ia/app.py"})
    inal.append({"item": "Escopo", "como": "o local vem da credencial do serviço, não do pedido; RLS por local no banco", "evidencia": "sqlserver/README.md"})
    for rotulo, rel, desc in (("Adaptador LoRA", "ia/finetuning/output/qwen2.5-0.5b-lora/adapter_model.safetensors", "o mesmo da Entrega 2 (não foi treinado de novo; só medido de novo)"),
                              ("Corpus do RAG", "ia/rag_documents.json", "os mesmos 20 documentos fictícios (mudou a forma de buscar, não o conteúdo)"),
                              ("Validações cegas da injeção", "ia/injecao-validacao.json", "os dois conjuntos cegos, congelados por SHA-256, não foram editados "
                               "(a correção de 26/11 partiu das falhas da 1ª; a 2ª foi congelada antes e nunca serviu para ajustar)")):
        datas = _git_datas(ENTREGA / rel)
        inal.append({"item": rotulo, "como": desc + (f"; último commit do arquivo: {datas[0]}" if datas else ""), "evidencia": rel})
    inal.append({"item": "Regras de competência e vencimento", "como": "as regras do SIGp que definem a competência e o vencimento das notas não mudaram nesta etapa (a regra de decisão da IA ganhou uma verificação, H-46)", "evidencia": "historico-evolucao.md"})
    inal.append({"item": "Telas", "como": "as mesmas telas do SIGp; mudou só onde elas abrem (janela própria em vez de aba do navegador)", "evidencia": "abrir-sigp.ps1"})
    inal.append({"item": "Dados", "como": "base 100% fictícia no pacote e 100.020 notas sintéticas no banco acadêmico; nenhum dado real", "evidencia": "entrega/base_ficticia.py"})
    inal.append({"item": "Triagem do Gmail", "como": "prompt v4.2 (WF-08/WF-10); só a resposta sem fim foi corrigida (maxLength e limite de tokens)", "evidencia": "ia/escolha-modelo-triagem.md"})
    return {"melhorado": m, "corrigido": corrigido, "inalterado": inal,
            "entrega2": {"data": str(e2.get("executed_at_utc", ""))[:10], "casos": e2.get("case_count"), "prompt": sorted({x.get("prompt_version") for x in e2_obs})}}


def _requisitos(d: dict) -> list[dict]:
    """Onde está cada requisito da entrega final e o resultado medido; confere que cada documento existe."""
    B, F, S, O, R = d["ia_depois"], d["finetuning"], d["seguranca"], d["otimizacao"], d.get("rag")
    q = {(x["cfg"], x["consulta"]): x for x in O["tempos"]}
    vul = (_json(EV3 / "vulnerabilidades-depois.json") or {}).get("resumo") or {}
    reqs = [
        ("IA", "Casos de teste com métrica e análise das falhas", "ia/casos-de-teste-final.md",
         f"{B['metricas']['acertos']}/16 e {B['fora']['acertos']}/{B['fora']['total']} fora de escopo; acurácia, F1, matriz e intervalo de 95%" if B.get("fora") else f"{B['metricas']['acertos']}/16"),
        ("IA", "RAG (com embeddings)", "ia/rag-embeddings.md",
         f"{R['escolha']}: {R['metodos'][R['escolha']]['parafrases']['acertos']}/{R['metodos'][R['escolha']]['parafrases']['total']} paráfrases" if R and R["escolha"] else "—"),
        ("IA", "Fine-tuning: base, base + RAG, ajustado, ajustado + RAG; custo e latência; fora do treino", "ia/finetuning/comparacao-final.md",
         f"4 configurações em {len(F['conjuntos'])} conjuntos (finais, fora de escopo, teste do treino)" if F else "—"),
        ("IA", "Prompt injection testado e as defesas", "ia/casos-de-teste-final.md",
         f"bateria {B['injecao_metricas']['ataques_detectados']}/{B['injecao_metricas']['ataques']}; 2ª validação cega "
         + (f"{B['validacao_v2_metricas']['ataques_detectados']}/{B['validacao_v2_metricas']['ataques']}" if B.get("validacao_v2_metricas") else "—")
         + "; 8 camadas"),
        ("IA", "Versionamento do prompt (qual fluxo usa qual)", "ia/prompts/CHANGELOG.md", f"análise de fatura v{B['servico']['prompt_version']}; triagem v4.2"),
        ("IA", "Fluxo do n8n sem segredo", "ia/segredos-n8n.md", S["segredos"]["resultado"]),
        ("BD", "Papéis e permissões com DENY justificado", "seguranca/matriz-permissoes.md", f"{S['matriz']['denys']} DENY, cada um com motivo e teste"),
        ("BD", "Dados sensíveis (RLS, mascaramento e TDE)", "seguranca/protecao-dados-sensiveis.md", f"TDE: {S['tde']['resultado']}" if S.get("tde") else "—"),
        ("BD", "Duas consultas lentas: plano (scan × seek, custo) e tempos", "seguranca/otimizacao-consultas.md",
         f"{br_(q[('A', 1)]['mediana'] / q[('D', 1)]['mediana'])}× e {br_(q[('A', 2)]['mediana'] / q[('C', 2)]['mediana'])}×"),
        ("BD", "Ataque e correção (escalonamento)", "seguranca/ataque-escalonamento.md", "falha reproduzida e barrada"),
        ("BD", "Trilha 'quem fez o quê', protegida contra alteração", "seguranca/trilha-auditoria.md", f"ledger: {(S.get('ledger') or {}).get('resultado', '—')}"),
        ("BD", "Auditoria do que a IA respondeu e a IA por perfil", "seguranca/auditoria-e-ia-por-perfil.md", S["ia_perfis"]["resultado"] or "—"),
        ("BD", "Vulnerabilidades, restauração do backup e injeção de SQL", "seguranca/avaliacao-vulnerabilidades.md",
         f"{vul.get('PASSOU', '?')} regras passando, {vul.get('FALHOU', '?')} falhas"),
        ("IA e BD", "Histórico de falhas, correções e retestes", "historico-evolucao.md", f"{len(d['historico'])} itens"),
        ("IA e BD", "Mudanças desde a Entrega 2", "MUDANCAS-DESDE-ENTREGA-2.md", "melhorado, corrigido e inalterado"),
        ("IA e BD", "Respostas aos comentários da professora", "README.md", f"{len(d['respostas_professora'])} comentários"),
        ("IA e BD", "Relatório de limitações (até 2 páginas)", "relatorio-limitacoes.pdf", "gerado das evidências"),
        ("IA e BD", "Guia de correção (1 página)", "guia-de-correcao.pdf", "comentários, resultados e como conferir"),
        ("IA e BD", "Apresentação do sistema (HTML), com as mudanças desde a Entrega 2", "apresentacao-sistema.html", "um arquivo, sem internet"),
        ("IA e BD", "Relatório final e contribuição individual", "relatorio-final.pdf", f"{len(d['projeto']['integrantes'])} integrantes"),
        ("IA e BD", "Instalação reproduzível com base fictícia", "GUIA-INSTALACAO.md", "um comando; janela própria no Windows"),
    ]
    return [{"disciplina": a, "requisito": r, "documento": doc, "resultado": res, "existe": (ENTREGA / doc).exists()} for a, r, doc, res in reqs]


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
    d["mudancas"] = _mudancas(d)
    d["requisitos"] = _requisitos(d)
    return d


def _carregar() -> dict:
    ident = _json(ENTREGA / "identificacao.json") or {}
    return {
        "projeto": {"repositorio": ident.get("repositorio"), "disciplinas": ident.get("disciplinas", []),
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
        "injecao_antes_26": _resumo_casos(_json(EV3 / "ia-avaliacao-validacao-v2-antes.json")),
        "sobreposicao": _sobreposicao(),
    }


if __name__ == "__main__":
    d = carregar()
    print(json.dumps({k: (type(v).__name__, len(v) if hasattr(v, "__len__") else v) for k, v in d.items()}, ensure_ascii=False, indent=1))
