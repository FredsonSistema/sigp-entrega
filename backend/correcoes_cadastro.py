"""Correções do cadastro a partir da qualidade (Configurações > Qualidade do cadastro).

Três correções, sempre com prévia e confirmação na tela, backup do banco antes e registro do que mudou:
1. Unificar nomes de provedor: variantes do mesmo provedor (ITS e ITS TELECOMUNICAÇÕES LTDA) passam a ter o nome
   normalizado; o plano/velocidade é mantido no nome ("BRISANET 200MB+IP"). O mapa nome antigo -> novo fica guardado
   e vale também quando uma tela aberta com cópia antiga regrava o local (não desfaz a correção).
2. Dia de vencimento: preenche o dia do provedor; sugestão a partir das faturas e notas já associadas ao local.
3. Unidade inválida (cabeçalho de planilha importado por engano, ex.: "AGENCIAS"): fica inativa (histórico mantido).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend import base_conhecimento as bc
from backend import database
from backend.provedores import mesma_empresa

CHAVE_MAPA = "correcoes_nomes_provedor_v1"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _nome_unidade(local: Dict[str, Any]) -> str:
    return f"{bc.TIPO_ROTULO.get(local.get('tipo'), '')} {local.get('nome', '')}".strip()


def nome_unificado(nome: Any) -> Optional[str]:
    """Nome normalizado do provedor, com o plano no fim quando houver. None se o nome não é de empresa."""
    canonico, plano = bc.normalizar_provedor(nome)
    if not canonico:
        return None
    return f"{canonico} {plano}" if plano else canonico


def _dia(data: Any) -> Optional[int]:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(data or ""))
    if m:
        return int(m.group(3))
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(data or ""))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- propostas
def propostas(locais: List[Dict[str, Any]], notas_recebidas: Iterable[Dict[str, Any]],
              notas_lancadas: Iterable[Dict[str, Any]], faturas: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    validos = [l for l in locais if bc.unidade_valida(l)]
    # 1) Unificar: provedores cujo nome cadastrado difere do nome normalizado, agrupados pelo provedor.
    grupos: Dict[str, Dict[str, Any]] = {}
    for l in validos:
        for i, p in enumerate(l.get("provedores") or []):
            atual = str(p.get("nome") or "")
            novo = nome_unificado(atual)
            canonico = bc.normalizar_provedor(atual)[0]
            if not novo or not canonico:
                continue
            g = grupos.setdefault(canonico, {"provedor": canonico, "nomes": Counter(), "itens": []})
            g["nomes"][re.sub(r"\s+", " ", atual).strip()] += 1
            if atual.strip() != novo:
                g["itens"].append({"localId": l["id"], "unidade": _nome_unidade(l), "indice": i, "provedorId": p.get("id") or "",
                                   "de": atual, "para": novo})
    unificar = []
    for canonico, g in sorted(grupos.items()):
        bases = {bc.chave(re.sub(bc._PLANO, "", n)) for n in g["nomes"]}
        if len(bases) > 1 and g["itens"]:  # há variantes de verdade (não só caixa alta/baixa no mesmo nome)
            unificar.append({"provedor": canonico, "variantes": [{"nome": n, "links": q} for n, q in g["nomes"].most_common()],
                             "itens": g["itens"]})

    # 2) Dia de vencimento: provedores sem dia, com a sugestão mais frequente das fontes.
    por_local: Dict[str, List[tuple]] = {}
    # Provedor que existe num único local: a fatura dele, mesmo ainda sem associação, é desse local.
    donos: List[tuple] = [(l["id"], p.get("nome") or "") for l in validos for p in (l.get("provedores") or []) if bc.normalizar_provedor(p.get("nome"))[0]]
    for n in notas_recebidas:
        d = n.get("dados") or {}
        emissor = d.get("emissorNome") or ""
        if n.get("status") == "ASSOCIADA" and n.get("entidade_id"):
            por_local.setdefault(n["entidade_id"], []).append((emissor, _dia(d.get("dataVencimento")), "fatura associada", "", 2))
        elif n.get("status") in ("AGUARDANDO_ASSOCIACAO", "REVISAO") and emissor and _dia(d.get("dataVencimento")):
            # Compara também pelo nome normalizado: um erro de digitação ("CNEXÃOBA") não pode criar falsa exclusividade.
            locais_do_emissor = {lid for lid, nome in donos
                                 if mesma_empresa(emissor, nome) or mesma_empresa(emissor, bc.normalizar_provedor(nome)[0])
                                 or bc.normalizar_provedor(emissor)[0] == bc.normalizar_provedor(nome)[0]}
            if len(locais_do_emissor) == 1:
                lid = next(iter(locais_do_emissor))
                por_local.setdefault(lid, []).append((emissor, _dia(d.get("dataVencimento")), "fatura recebida, ainda sem associação (provedor só neste local)", "", 1))
    for n in notas_lancadas:
        if n.get("entidade_id"):
            por_local.setdefault(n["entidade_id"], []).append((n.get("provedor_nome") or "", _dia(n.get("data_vencimento")), "nota lançada", "", 2))
    for f in faturas:
        if f.get("entidade_id"):
            d = f.get("dados") or {}
            por_local.setdefault(f["entidade_id"], []).append((f.get("provedor_nome") or "", _dia(d.get("dataVencimento")), "fatura anexada",
                                                               f.get("provedor_id") or "", 2))
    vencimento = []
    for l in validos:
        for i, p in enumerate(l.get("provedores") or []):
            nome = bc.normalizar_provedor(p.get("nome"))[0]
            if not nome or str(p.get("diaVencimento") or "").strip():
                continue
            dias: Counter = Counter()
            fontes: Counter = Counter()
            if _dia(p.get("dataVencimento")):
                dias[_dia(p["dataVencimento"])] += 3
                fontes["vencimento cadastrado"] += 1
            for emissor, dia, fonte, prov_id, peso in por_local.get(l["id"], []):
                if dia and ((prov_id and prov_id == p.get("id")) or mesma_empresa(emissor, p.get("nome"))
                            or mesma_empresa(emissor, nome)):
                    dias[dia] += peso
                    fontes[fonte] += 1
            sugestao = dias.most_common(1)[0][0] if dias else None
            vencimento.append({"localId": l["id"], "unidade": _nome_unidade(l), "indice": i, "provedorId": p.get("id") or "",
                               "provedor": str(p.get("nome") or ""), "sugestao": sugestao,
                               "fonte": ", ".join(f"{k} ({v})" for k, v in fontes.most_common()) if sugestao else "",
                               "dias": [{"dia": d_, "vezes": q} for d_, q in sorted(dias.items(), key=lambda x: -x[1])]})
    vencimento.sort(key=lambda x: (x["sugestao"] is None, x["unidade"]))

    # 3) Unidades inválidas
    invalidas = [{"localId": l["id"], "unidade": _nome_unidade(l), "tipo": l.get("tipo"), "provedores": len(l.get("provedores") or [])}
                 for l in locais if not bc.unidade_valida(l)]
    return {"unificar": unificar, "vencimento": vencimento, "unidadesInvalidas": invalidas,
            "resumo": {"unificar": sum(len(g["itens"]) for g in unificar), "vencimento": len(vencimento),
                       "vencimentoComSugestao": sum(1 for v in vencimento if v["sugestao"]), "unidadesInvalidas": len(invalidas)}}


# ---------------------------------------------------------------- aplicar
def _alterar_provedores(local_id: str, alteracoes: List[Dict[str, Any]], campo: str, valor_de) -> List[Dict[str, Any]]:
    """Altera provedores de um local (transação). Confere se cada provedor ainda é o da prévia (id ou índice + nome)."""
    conn = database.get_connection()
    feitos = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT provedores_json FROM locais WHERE id = ? AND ativo = 1", (local_id,)).fetchone()
        if not row:
            conn.rollback()
            return []
        provedores = json.loads(row["provedores_json"] or "[]")
        for alt in alteracoes:
            idx = next((i for i, p in enumerate(provedores) if alt.get("provedorId") and p.get("id") == alt["provedorId"]), None)
            if idx is None and 0 <= int(alt.get("indice", -1)) < len(provedores) and not alt.get("provedorId"):
                idx = int(alt["indice"])
            if idx is None:
                continue
            p = provedores[idx]
            if "de" in alt and str(p.get("nome") or "") != alt["de"]:
                continue  # mudou desde a prévia: não mexe
            antes = p.get(campo)
            p[campo] = valor_de(alt)
            feitos.append({"localId": local_id, "provedorId": p.get("id") or "", "campo": campo, "antes": antes, "depois": p[campo]})
        if feitos:
            conn.execute("UPDATE locais SET provedores_json = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(provedores, ensure_ascii=False), _agora(), local_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return feitos


def _por_local(itens: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    saida: Dict[str, List[Dict[str, Any]]] = {}
    for i in itens:
        if isinstance(i, dict) and i.get("localId"):
            saida.setdefault(str(i["localId"]), []).append(i)
    return saida


def unificar(itens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    validos = []
    for i in itens or []:
        novo = nome_unificado(i.get("de"))
        if novo and str(i.get("de")) != novo:
            validos.append({**i, "para": novo})  # o nome novo é sempre recalculado aqui, não vem da tela
    feitos = []
    for local_id, alts in _por_local(validos).items():
        feitos += _alterar_provedores(local_id, alts, "nome", lambda a: a["para"])
    if feitos:
        mapa = database.get_app_state([CHAVE_MAPA]).get(CHAVE_MAPA) or {}
        for f in feitos:
            mapa[bc.chave(f["antes"])] = f["depois"]
        database.save_app_state(CHAVE_MAPA, mapa)
    return feitos


def preencher_vencimento(itens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    validos = []
    for i in itens or []:
        try:
            dia = int(i.get("dia"))
        except (TypeError, ValueError):
            continue
        if 1 <= dia <= 31:
            validos.append({**i, "dia": dia})
    feitos = []
    for local_id, alts in _por_local(validos).items():
        feitos += _alterar_provedores(local_id, alts, "diaVencimento", lambda a: str(a["dia"]))
    return feitos


def desativar_unidade(local_id: str) -> Optional[Dict[str, Any]]:
    """Só unidade inválida (nome de cabeçalho): fica inativa, como a exclusão pela tela (histórico preservado)."""
    local = database.get_local(local_id)
    if not local or not local.get("ativo") or bc.unidade_valida(local):
        return None
    conn = database.get_connection()
    try:
        conn.execute("UPDATE locais SET ativo = 0, updated_at = ? WHERE id = ?", (_agora(), local_id))
        conn.commit()
    finally:
        conn.close()
    return {"localId": local_id, "unidade": _nome_unidade(local)}


def aplicar_mapa_nomes(items: List[Any]) -> List[Any]:
    """Na gravação pela tela: nome antigo de provedor já unificado vira o nome novo (cópia antiga não desfaz a correção)."""
    mapa = database.get_app_state([CHAVE_MAPA]).get(CHAVE_MAPA) or {}
    if not mapa:
        return items
    for item in items:
        if isinstance(item, dict):
            for p in item.get("provedores") or []:
                if isinstance(p, dict) and bc.chave(p.get("nome")) in mapa:
                    p["nome"] = mapa[bc.chave(p.get("nome"))]
    return items
