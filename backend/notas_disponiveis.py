"""Notas disponíveis: documentos que chegaram do provedor (Gmail: fatura, boleto, NFS-e/NFCom em XML ou PDF) e foram
associados a um local. Não são notas lançadas: nota lançada é só a do financeiro (Importar NF, WF-01) e nota paga
também vem do financeiro. Quando o financeiro lança a nota, ela se liga à nota disponível do mesmo local, provedor e
mês (ou da mesma chave) e os documentos entram na conciliação. SIG e SIE só contam o ciclo com todas as evidências:
nota lançada + nota paga + fatura.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from backend import database


def _serializar(row) -> Dict[str, Any]:
    item = database.serialize_row(row)
    return item


def documentos(conn, disponivel_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM faturas_locais WHERE nota_disponivel_id = ? ORDER BY COALESCE(json_extract(dados_json, '$.documentoAdicional'), 0), created_at",
        (disponivel_id,),
    ).fetchall()
    saida = []
    for r in rows:
        dados = json.loads(r["dados_json"] or "{}")
        xml = dados.get("xmlNotaFiscal") or {}
        saida.append({"id": r["id"], "nome": r["nome_arquivo"], "principal": not dados.get("documentoAdicional"),
                      "url": f"/api/faturas/{r['id']}/arquivo", "xmlNome": xml.get("nome") or "",
                      "xmlUrl": f"/api/faturas/{r['id']}/xml" if xml.get("storage") else "", "associadoEm": r["created_at"]})
    return saida


def listar(entidade_tipo: str = "", entidade_id: str = "") -> List[Dict[str, Any]]:
    cond, params = [], []
    if entidade_tipo:
        cond.append("entidade_tipo = ?")
        params.append(entidade_tipo)
    if entidade_id:
        cond.append("entidade_id = ?")
        params.append(entidade_id)
    where = f"WHERE {' AND '.join(cond)}" if cond else ""
    conn = database.get_connection()
    try:
        rows = conn.execute(f"SELECT * FROM notas_disponiveis {where} ORDER BY data_vencimento DESC, updated_at DESC", params).fetchall()
        return [{**_serializar(r), "documentos": documentos(conn, r["id"])} for r in rows]
    finally:
        conn.close()


def obter(disponivel_id: str) -> Optional[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM notas_disponiveis WHERE id = ?", (disponivel_id,)).fetchone()
        return {**_serializar(row), "documentos": documentos(conn, row["id"])} if row else None
    finally:
        conn.close()


def vincular_lancada(nota: Dict[str, Any]) -> Optional[str]:
    """O financeiro lançou a nota: liga à nota disponível correspondente (mesma chave no local, ou mesmo local +
    empresa + mês) que ainda não tem nota lançada, e leva os documentos dela para a conciliação. Devolve o id ligado."""
    if not nota or not nota.get("id") or str(nota.get("sistema_origem") or "") == "gmail":
        return None
    tipo, local = str(nota.get("entidade_tipo") or ""), str(nota.get("entidade_id") or "")
    conn = database.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        alvo = None
        chave = str(nota.get("chave") or "").strip()
        if chave and not database.eh_padrao(chave):
            alvo = conn.execute("SELECT * FROM notas_disponiveis WHERE entidade_tipo = ? AND entidade_id = ? AND chave = ?",
                                (tipo, local, chave)).fetchone()
        if not alvo:
            alvo = database.encontrar_disponivel_da_competencia(conn, tipo, local, str(nota.get("provedor_nome") or ""),
                                                                 str(nota.get("data_vencimento") or ""))
        if not alvo or (alvo["nota_lancada_id"] and alvo["nota_lancada_id"] != nota["id"]):
            conn.rollback()
            return None
        agora = database._now()
        conn.execute("UPDATE notas_disponiveis SET nota_lancada_id = ?, updated_at = ? WHERE id = ?", (nota["id"], agora, alvo["id"]))
        conn.execute("UPDATE faturas_locais SET nota_lancada_id = ?, updated_at = ? WHERE nota_disponivel_id = ?", (nota["id"], agora, alvo["id"]))
        conn.execute("UPDATE notas_recebidas SET nota_lancada_id = ?, updated_at = ? WHERE nota_disponivel_id = ?", (nota["id"], agora, alvo["id"]))
        conn.commit()
        return str(alvo["id"])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def limpar_notas_fiscais_do_local(item: Dict[str, Any]) -> Dict[str, Any]:
    """Linha "Nota lançada" criada no navegador pela associação do Gmail (id "gmail-...") não é nota lançada:
    sai da lista do local (o pagamento da linha, se houver, fica). Protege contra cópia antiga da tela."""
    linhas = item.get("notasFiscais")
    if not isinstance(linhas, list):
        return item
    novas = []
    for linha in linhas:
        if isinstance(linha, dict) and str((linha.get("notaLancada") or {}).get("id") or "").startswith("gmail-"):
            if not linha.get("notaPaga"):
                continue
            linha = {k: v for k, v in linha.items() if k not in ("notaLancada", "conciliacao")}
            linha["status"] = "PENDENTE"
            if str(linha.get("id") or "").startswith("gmail-"):
                linha["id"] = str(linha["notaPaga"].get("id") or linha["id"])
        novas.append(linha)
    return {**item, "notasFiscais": novas}


def migrar_lancadas_do_gmail(aplicar: bool = False) -> Dict[str, Any]:
    """Notas lançadas criadas pela associação do Gmail viram notas disponíveis (mesmo id). Documentos e e-mails
    passam a apontar para a disponível; conciliações delas saem (o ciclo só fecha quando o financeiro lançar);
    pagamentos (notas pagas) ficam. Sem aplicar: só a prévia."""
    conn = database.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        notas = conn.execute("SELECT * FROM notas_lancadas WHERE origem = 'gmail' OR sistema_origem = 'gmail'").fetchall()
        previa = []
        for n in notas:
            docs = conn.execute("SELECT COUNT(*) FROM faturas_locais WHERE nota_lancada_id = ?", (n["id"],)).fetchone()[0]
            emails = conn.execute("SELECT COUNT(*) FROM notas_recebidas WHERE nota_lancada_id = ?", (n["id"],)).fetchone()[0]
            conc = conn.execute("SELECT id, nota_paga_id, status FROM conciliacoes WHERE nota_lancada_id = ?", (n["id"],)).fetchall()
            previa.append({"id": n["id"], "local": n["local_nome"], "provedor": n["provedor_nome"], "numero": n["numero"],
                           "valor": n["valor_total"], "vencimento": n["data_vencimento"], "documentos": docs, "emails": emails,
                           "conciliacoes": [dict(c) for c in conc]})
            if not aplicar:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO notas_disponiveis (id, entidade_tipo, entidade_id, chave, numero, serie, provedor_nome, local_nome,
                    local_cidade, valor_total, data_emissao, data_vencimento, observacao, servicos_json, nota_lancada_id, origem, id_externo,
                    created_at, updated_at)
                SELECT id, entidade_tipo, entidade_id, chave, numero, serie, provedor_nome, local_nome, local_cidade, valor_total,
                    data_emissao, data_vencimento, observacao, servicos_json, '', 'gmail', id_externo, created_at, ?
                FROM notas_lancadas WHERE id = ?
                """,
                (database._now(), n["id"]),
            )
            conn.execute("UPDATE faturas_locais SET nota_disponivel_id = ?, nota_lancada_id = '' WHERE nota_lancada_id = ?", (n["id"], n["id"]))
            conn.execute("UPDATE notas_recebidas SET nota_disponivel_id = ?, nota_lancada_id = '' WHERE nota_lancada_id = ?", (n["id"], n["id"]))
            conn.execute("DELETE FROM conciliacoes WHERE nota_lancada_id = ?", (n["id"],))
            conn.execute("DELETE FROM notas_lancadas WHERE id = ?", (n["id"],))
        locais_alterados = 0
        if aplicar:
            for row in conn.execute("SELECT id, dados_json FROM locais").fetchall():
                dados = json.loads(row["dados_json"] or "{}")
                limpo = limpar_notas_fiscais_do_local(dados)
                if limpo.get("notasFiscais") != dados.get("notasFiscais"):
                    conn.execute("UPDATE locais SET dados_json = ? WHERE id = ?", (json.dumps(limpo, ensure_ascii=False), row["id"]))
                    locais_alterados += 1
        conn.commit() if aplicar else conn.rollback()
        return {"notas": previa, "total": len(previa), "aplicado": aplicar, "locaisAlterados": locais_alterados}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
