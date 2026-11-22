"""Base de conhecimento das unidades, gerada do banco (sempre atual), no formato "RAG-ready" combinado com o usuário
(base_conhecimento_rag_unidades.json): resumo global + um documento por unidade (metadata, dados estruturados e o
texto para busca). Também normaliza os nomes de provedor e aponta a qualidade do cadastro.

Regras combinadas: cada link é uma conta de internet; 2 ou mais links na unidade = redundância (mesmo provedor
conta); agência/sala VIP dentro da rodoviária conta como a rodoviária. Rede e IPs só com a permissão "rede.ver".
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROVEDORES = json.loads((Path(__file__).resolve().parent / "conhecimento_assistente" / "provedores.json").read_text(encoding="utf-8"))
ALIASES: Dict[str, str] = _PROVEDORES["aliases"]
INVALIDOS = set(_PROVEDORES["nomes_invalidos"])
TIPO_ROTULO = {"agencia": "Agência", "rodoviaria": "Rodoviária", "garagem": "Garagem"}
TIPO_ROTULO_PLURAL = {"agencia": "Agências", "rodoviaria": "Rodoviárias", "garagem": "Garagens"}
_PLANO = re.compile(r"\b(\d+\s?(?:MB|GB|KB)(?:\s?\+\s?IP)?(?:\s(?:CS|DEDICADO))?)\b", re.IGNORECASE)
# Nome de unidade que é cabeçalho de planilha importado por engano (ex.: "AGENCIAS"): fica fora da base.
UNIDADES_INVALIDAS = {"AGENCIA", "AGENCIAS", "RODOVIARIA", "RODOVIARIAS", "GARAGEM", "GARAGENS", "NOME", "LOCAL", "UNIDADE"}
_SUFIXOS = re.compile(r"\b(LTDA|EIRELI|ME|EPP|S\s?A)\b\.?", re.IGNORECASE)


def _sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in t if not unicodedata.combining(c))


def chave(texto: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", _sem_acento(str(texto or "")).upper())).strip()


def normalizar_provedor(nome: Any) -> Tuple[Optional[str], Optional[str]]:
    """("Brisanet Telecomunicações 200MB+IP") -> ("BRISANET", "200MB+IP"). Nome inválido (só telefone, "Suporte") -> (None, plano)."""
    bruto = str(nome or "").strip()
    m = _PLANO.search(bruto)
    plano = m.group(1).replace(" ", "") if m else None
    if m and m.group(1).upper().endswith(("CS", "DEDICADO")):
        plano = re.sub(r"(\d+\s?[MGK]B)\s?", r"\1 ", m.group(1)).strip()
    base = _PLANO.sub(" ", bruto)
    base = _SUFIXOS.sub(" ", base)
    k = chave(base)
    if not k or not re.search(r"[A-Z]", k) or k in INVALIDOS or k.startswith("SUPORTE"):
        return None, plano
    if k in ALIASES:
        return ALIASES[k], plano
    canonico = re.sub(r"\s+", " ", base.strip(" -/|")).upper()
    return (ALIASES.get(chave(canonico)) or canonico), plano


def _texto_lista(itens: Any) -> Optional[str]:
    if not itens:
        return None
    partes = []
    for item in itens if isinstance(itens, list) else [itens]:
        if isinstance(item, dict):
            valores = [str(v).strip() for v in item.values() if isinstance(v, (str, int, float)) and str(v).strip()]
            if valores:
                partes.append(" - ".join(valores))
        elif str(item).strip():
            partes.append(str(item).strip())
    return " | ".join(partes) or None


def _responsaveis(local: Dict[str, Any]) -> Optional[str]:
    lista = [r for r in (local.get("responsaveis") or []) if isinstance(r, dict)]
    partes = [" - ".join(x for x in (r.get("nome"), r.get("telefone"), r.get("email")) if x) for r in lista]
    return " | ".join(p for p in partes if p) or None


def _ultima_visita(local: Dict[str, Any]) -> Optional[str]:
    datas = []
    for v in local.get("historicoVisitas") or []:
        texto = json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else str(v)
        datas += re.findall(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", texto)
    if not datas:
        return None
    iso = lambda d: d if "-" in d else f"{d[6:]}-{d[3:5]}-{d[:2]}"  # noqa: E731
    d = max(datas, key=iso)
    return d if "/" in d else f"{d[8:]}/{d[5:7]}/{d[:4]}"


def documento(local: Dict[str, Any], pode_rede: bool, catalogo: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    from backend import marcadores  # aqui dentro: marcadores importa este módulo
    marc = marcadores.do_local(local, catalogo or [])
    tipo = local.get("tipo", "")
    rotulo = TIPO_ROTULO.get(tipo, tipo)
    provedores = []
    for p in local.get("provedores") or []:
        nome, plano = normalizar_provedor(p.get("nome"))
        provedores.append({
            "provedor_normalizado": nome, "nome_cadastrado": p.get("nome") or "",
            "plano_velocidade": plano, "valor_mensal": str(p.get("valor") or "") or None,
            "dia_vencimento": int(p["diaVencimento"]) if str(p.get("diaVencimento") or "").isdigit() else None,
            "contato": p.get("contato") or None, "email_suporte": p.get("email") or None,
        })
    # Registro de provedor com nome inválido (só telefone, "Suporte / Whatsapp") não é link: vai para a qualidade do cadastro.
    validos = [p for p in provedores if p["provedor_normalizado"]]
    nomes = [p["provedor_normalizado"] for p in validos]
    links = len(validos)
    rede = _texto_lista(local.get("redes")) if pode_rede else None
    endereco = local.get("endereco") or None
    numero = str(local.get("numero") or "").strip() or None
    gestao = {"responsaveis": _responsaveis(local), "vencimento_fatura_geral": local.get("vencimentoFatura") or None,
              "ultima_visita": _ultima_visita(local), "observacoes": (local.get("obs") or "").strip() or None}
    texto = (f"Unidade do tipo {rotulo}: {local.get('nome', '')}, localizada em {local.get('cidade', '') or 'cidade não informada'}. "
             + (f"Possui {links} link(s) de internet contratado(s) com: {', '.join(nomes)}. " if links else "Nenhum provedor de internet cadastrado. ")
             + (f"Tem redundância (link reserva). " if links >= 2 else "")
             + f"Endereço: {endereco or 'não informado'}, {numero or 'S/N'} (CEP: {local.get('cep') or 'não informado'}). "
             + (f"Rede/Gateway: {rede or 'não informado'}. " if pode_rede else "")
             + f"Responsável local: {gestao['responsaveis'] or 'não informado'}. Observações: {gestao['observacoes'] or 'nenhuma'}."
             + (f" Regional: {marc['regional']}." if marc["regional"] else "")
             + (f" Marcadores: {marcadores.texto_marcadores(marc)}." if marc["marcadores"] else "")
             + (f" Grupos: {', '.join(marc['grupos'])}." if marc["grupos"] else ""))
    return {
        "id": f"{tipo[:3]}_{local.get('id', '')}",
        "metadata": {"tipo_unidade": rotulo, "tipo": tipo, "local_id": local.get("id"), "nome_unidade": local.get("nome", ""),
                     "cidade": local.get("cidade", ""), "quantidade_links": links, "provedores_nomes": nomes,
                     "possui_redundancia": links >= 2, "regional": marc["regional"] or None,
                     "marcadores": [m["nome"] for m in marc["marcadores"]], "grupos": marc["grupos"],
                     "arquivo_origem": "sigp (banco de dados)"},
        "dados_estruturados": {
            "localizacao": {"endereco": endereco, "numero": numero, "cep": local.get("cep") or None, "cidade": local.get("cidade") or None},
            "infraestrutura": {"provedores": validos, **({"redes_ips": rede} if pode_rede else {"redes_ips": "restrito (permissão Ver rede e IPs)"})},
            "gestao": gestao,
            "marcadores": marc,
        },
        "texto_para_embedding": texto,
    }


def unidade_valida(local: Dict[str, Any]) -> bool:
    return chave(local.get("nome")) not in UNIDADES_INVALIDAS and bool(chave(local.get("nome")))


def gerar(locais: List[Dict[str, Any]], pode_rede: bool, hoje: Optional[date] = None,
          catalogo: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    from backend import marcadores  # aqui dentro: marcadores importa este módulo
    cat = catalogo if catalogo is not None else marcadores.catalogo_seguro()
    validos = [l for l in locais if unidade_valida(l)]
    docs = [documento(l, pode_rede, cat) for l in sorted(validos, key=lambda x: (x.get("tipo", ""), chave(x.get("nome"))))]
    por_regional: Dict[str, int] = {}
    for d in docs:
        if d["metadata"]["regional"]:
            por_regional[d["metadata"]["regional"]] = por_regional.get(d["metadata"]["regional"], 0) + 1
    unicos = sorted({n for d in docs for n in d["metadata"]["provedores_nomes"]}, key=chave)
    contagem = {TIPO_ROTULO_PLURAL[t]: sum(1 for d in docs if d["metadata"]["tipo"] == t) for t in ("garagem", "rodoviaria", "agencia")}
    links = sum(d["metadata"]["quantidade_links"] for d in docs)
    redund = [d["metadata"]["nome_unidade"] for d in docs if d["metadata"]["possui_redundancia"]]
    sem = [d["metadata"]["nome_unidade"] for d in docs if not d["metadata"]["quantidade_links"]]
    resumo = {
        "id": "resumo_global_infraestrutura",
        "metadata": {"tipo_unidade": "Resumo Global", "nome_unidade": "Consolidação Geral de Infraestrutura e Provedores",
                     "total_unidades": len(docs), "total_links_ativos": links, "total_provedores_unicos": len(unicos)},
        "dados_estruturados": {"contagem_por_tipo": contagem, "lista_provedores_unicos": unicos,
                               "unidades_com_redundancia": redund, "unidades_sem_provedor": sem,
                               "unidades_por_regional": dict(sorted(por_regional.items(), key=lambda x: (-x[1], chave(x[0]))))},
        "texto_para_embedding": (f"Resumo geral da rede e provedores de internet da empresa: ao todo, {len(docs)} unidades cadastradas "
                                 f"({contagem['Garagens']} garagens, {contagem['Rodoviárias']} rodoviárias e {contagem['Agências']} agências), "
                                 f"com {links} links/contas de internet de {len(unicos)} provedores únicos. "
                                 f"{len(redund)} unidade(s) com redundância e {len(sem)} sem provedor cadastrado. "
                                 f"Provedores: {', '.join(unicos)}."
                                 + (" Unidades por regional: " + ", ".join(f"{n} ({q})" for n, q in sorted(por_regional.items(), key=lambda x: (-x[1], chave(x[0]))))
                                    + f"; {len(docs) - sum(por_regional.values())} sem regional." if por_regional else "")),
    }
    return {"schema_version": "1.0-rag-ready", "data_geracao": (hoje or date.today()).isoformat(), "gerado_por": "SIGp",
            "rede_incluida": pode_rede,
            "metricas_consolidadas": {"total_unidades_validas": len(docs), "total_links_internet": links,
                                      "total_provedores_unicos": len(unicos), "provedores_unicos": unicos},
            "documentos_rag": [resumo] + docs}


def qualidade(locais: List[Dict[str, Any]]) -> Dict[str, Any]:
    """O que falta ou está inconsistente no cadastro (sem telefones nem e-mails nos detalhes)."""
    itens: List[Dict[str, str]] = []
    variantes: Dict[str, set] = {}
    for l in locais:
        unidade = f"{TIPO_ROTULO.get(l.get('tipo'), '')} {l.get('nome', '')}".strip()
        if not unidade_valida(l):
            itens.append({"problema": "Unidade inválida", "unidade": unidade,
                          "detalhe": "O nome parece cabeçalho de planilha importado por engano: confira e exclua se não for uma unidade."})
            continue
        provs = l.get("provedores") or []
        if not provs:
            itens.append({"problema": "Unidade sem provedor", "unidade": unidade, "detalhe": "Nenhum link de internet cadastrado."})
        for p in provs:
            nome, _ = normalizar_provedor(p.get("nome"))
            if not nome:
                bruto = re.sub(r"\d[\d\s().-]{6,}\d", "<telefone>", str(p.get("nome") or ""))
                itens.append({"problema": "Nome de provedor inválido", "unidade": unidade,
                              "detalhe": f"\"{bruto or '(vazio)'}\" não é nome de empresa: corrija o nome e mova telefone para Contato."})
                continue
            variantes.setdefault(nome, set()).add(re.sub(_PLANO, "", str(p.get("nome") or "")).strip())
            if not str(p.get("diaVencimento") or "").strip():
                itens.append({"problema": "Provedor sem dia de vencimento", "unidade": unidade, "detalhe": nome})
        end = chave(l.get("endereco"))
        if not end:
            itens.append({"problema": "Sem endereço", "unidade": unidade, "detalhe": "Endereço vazio."})
        elif end in (chave(l.get("nome")), chave(l.get("cidade"))):
            itens.append({"problema": "Endereço genérico", "unidade": unidade, "detalhe": "O endereço repete o nome ou a cidade."})
        if not [r for r in (l.get("responsaveis") or []) if isinstance(r, dict) and (r.get("nome") or r.get("telefone"))]:
            itens.append({"problema": "Sem responsável", "unidade": unidade, "detalhe": "Nenhum responsável com nome ou telefone."})
        if "NAO CONFIRMADO" in chave(l.get("obs")):
            itens.append({"problema": "Endereço não confirmado", "unidade": unidade, "detalhe": "Marcado nas observações."})
    for nome, nomes in sorted(variantes.items()):
        distintos = sorted({n for n in nomes if n}, key=chave)
        if len({chave(n) for n in distintos}) > 1:
            itens.insert(0, {"problema": "Nome de provedor com variantes", "unidade": "—",
                             "detalhe": f"{', '.join(chave(n) for n in distintos)} → unificar como {nome}"})
    from backend import marcadores  # aqui dentro: marcadores importa este módulo
    itens.extend(marcadores.problemas(locais))
    resumo: Dict[str, int] = {}
    for i in itens:
        resumo[i["problema"]] = resumo.get(i["problema"], 0) + 1
    return {"total": len(itens), "resumo": resumo, "itens": itens}
