"""Marcadores e grupos de localidades.

- Marcador: etiqueta que o usuário põe em cada local (Regional Itabuna, Terceirizado, CS...). Fica no local como texto
  (campo "marcadores", o mesmo do CSV) e no catálogo, com cor, descrição e apelidos ("Rota" = RT).
- Grupo: regra só com dados do cadastro (provedor, cidade, tipo, link reserva, marcador, sem provedor). Os locais entram
  e saem sozinhos quando o cadastro muda; não se marca à mão.
Situação das contas (vencida etc.) não é marcador nem grupo: é tratada à parte.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend import base_conhecimento as bc
from backend import database

CORES = ["#7c6bd6", "#d4883b", "#4fa3d8", "#3fae8a", "#d06a6a", "#c9a227", "#8a9a5b", "#c46aa8", "#5b8bd9", "#999999"]
CAMPOS_REGRA = {"provedor", "cidade", "tipo", "reserva", "marcador", "sem_provedor"}
TIPOS = {"agencia", "rodoviaria", "garagem"}
# Siglas das empresas do grupo (informadas pelo usuário): descrição e apelidos para o assistente.
EMPRESAS = {
    "RT": ("Rota Transportes Rodoviários", ["Rota Transportes Rodoviarios", "Rota Transportes", "Rota"]),
    "CS": ("Viação Jequié Cidade Sol", ["Viacao Jequie Cidade Sol", "Cidade Sol"]),
    "EB": ("Expresso Brasileiro", ["Expresso Brasileiro"]),
    "VM": ("Via Metro (Viação Metropolitana de Ilhéus)", ["Via Metro", "Viacao Metropolitana de Ilheus", "Viacao Metropolitana"]),
}
CORRECOES_NOME = {"REGIONAL JEQUIE": "Regional Jequié"}  # "Regional Jequíe" (acento errado) vira "Regional Jequié"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _limpar_nome(nome: Any) -> str:
    return re.sub(r"\s+", " ", str(nome or "")).strip()[:60]


# ---------------------------------------------------------------- tabela e migração
def garantir_tabelas() -> None:
    conn = database.get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS marcadores (
                id TEXT PRIMARY KEY, nome TEXT NOT NULL, chave TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL DEFAULT 'marcador',
                cor TEXT NOT NULL DEFAULT '', descricao TEXT NOT NULL DEFAULT '', apelidos_json TEXT NOT NULL DEFAULT '[]',
                regra_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            -- Marcador renomeado (novo = nome atual) ou excluído (novo = NULL): uma cópia antiga da tela que ainda
            -- tenha o nome antigo não o recria ao gravar o local.
            CREATE TABLE IF NOT EXISTS marcadores_trocas (
                chave TEXT PRIMARY KEY, novo TEXT, updated_at TEXT NOT NULL
            );
        """)
        vazio = not conn.execute("SELECT 1 FROM marcadores LIMIT 1").fetchone()
        conn.commit()
    finally:
        conn.close()
    if vazio:
        migrar()


def migrar() -> Dict[str, Any]:
    """Primeira vez: corrige "Regional Jequíe" nos locais e cria o catálogo com os marcadores que já existem nos dados
    (vindos do sistema antigo) e as siglas das empresas."""
    corrigidos = 0
    conn = database.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        nomes: Dict[str, str] = {}
        for row in conn.execute("SELECT id, dados_json FROM locais").fetchall():
            dados = json.loads(row["dados_json"] or "{}")
            lista = dados.get("marcadores") if isinstance(dados.get("marcadores"), list) else []
            nova = []
            for m in lista:
                nome = _limpar_nome(m.get("nome") if isinstance(m, dict) else m)
                if not nome:
                    continue
                nome = CORRECOES_NOME.get(bc.chave(nome), nome)
                if nome.lower() not in [n.lower() for n in nova]:
                    nova.append(nome)
                nomes.setdefault(bc.chave(nome), nome)
            if nova != lista:
                dados["marcadores"] = nova
                conn.execute("UPDATE locais SET dados_json = ? WHERE id = ?", (json.dumps(dados, ensure_ascii=False), row["id"]))
                corrigidos += 1
        for sigla in EMPRESAS:
            nomes.setdefault(bc.chave(sigla), sigla)
        for i, (k, nome) in enumerate(sorted(nomes.items())):
            desc, apelidos = EMPRESAS.get(nome, ("", []))
            conn.execute("INSERT OR IGNORE INTO marcadores (id, nome, chave, tipo, cor, descricao, apelidos_json, regra_json, created_at, updated_at)"
                         " VALUES (?, ?, ?, 'marcador', ?, ?, ?, '{}', ?, ?)",
                         (f"mrc-{secrets.token_hex(5)}", nome, k, CORES[i % len(CORES)], desc, json.dumps(apelidos, ensure_ascii=False), _agora(), _agora()))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"locaisCorrigidos": corrigidos}


# ---------------------------------------------------------------- catálogo
def _item(row) -> Dict[str, Any]:
    return {"id": row["id"], "nome": row["nome"], "tipo": row["tipo"], "cor": row["cor"], "descricao": row["descricao"],
            "apelidos": json.loads(row["apelidos_json"] or "[]"), "regra": json.loads(row["regra_json"] or "{}")}


def catalogo() -> List[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        return [_item(r) for r in conn.execute("SELECT * FROM marcadores ORDER BY tipo, nome COLLATE NOCASE")]
    finally:
        conn.close()


def validar_regra(regra: Any) -> Dict[str, Any]:
    condicoes = (regra or {}).get("condicoes") if isinstance(regra, dict) else None
    if not isinstance(condicoes, list) or not condicoes:
        raise ValueError("O grupo precisa de pelo menos uma condição (ex.: provedor é HE-NET).")
    limpas = []
    for c in condicoes[:8]:
        campo = str((c or {}).get("campo") or "")
        if campo not in CAMPOS_REGRA:
            raise ValueError(f"Condição inválida: {campo or '(vazia)'}.")
        valores = [_limpar_nome(v) for v in ((c or {}).get("valores") or []) if _limpar_nome(v)][:30]
        if campo in ("provedor", "cidade", "marcador") and not valores:
            raise ValueError("Escolha pelo menos um valor para a condição.")
        if campo == "tipo":
            valores = [v for v in valores if v in TIPOS]
            if not valores:
                raise ValueError("Escolha o tipo (agência, rodoviária ou garagem).")
        if campo == "reserva":
            valores = ["sim" if (valores or ["sim"])[0] != "nao" else "nao"]
        limpas.append({"campo": campo, "valores": valores})
    return {"condicoes": limpas}


def salvar(dados: Dict[str, Any], marcador_id: Optional[str] = None) -> Dict[str, Any]:
    nome = _limpar_nome(dados.get("nome"))
    if not nome:
        raise ValueError("Informe o nome.")
    tipo = "grupo" if dados.get("tipo") == "grupo" else "marcador"
    regra = validar_regra(dados.get("regra")) if tipo == "grupo" else {}
    cor = str(dados.get("cor") or "")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", cor):
        cor = CORES[len(catalogo()) % len(CORES)]
    descricao = str(dados.get("descricao") or "").strip()[:200]
    apelidos = [_limpar_nome(a) for a in (dados.get("apelidos") or []) if _limpar_nome(a)][:10]
    conn = database.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        outro = conn.execute("SELECT id FROM marcadores WHERE chave = ?", (bc.chave(nome),)).fetchone()
        if outro and outro["id"] != marcador_id:
            raise ValueError("Já existe um marcador ou grupo com esse nome.")
        if marcador_id:
            atual = conn.execute("SELECT * FROM marcadores WHERE id = ?", (marcador_id,)).fetchone()
            if not atual:
                raise LookupError("Marcador não encontrado.")
            if atual["tipo"] != tipo:
                raise ValueError("Não dá para transformar marcador em grupo (ou o contrário): crie um novo.")
            conn.execute("UPDATE marcadores SET nome = ?, chave = ?, cor = ?, descricao = ?, apelidos_json = ?, regra_json = ?, updated_at = ? WHERE id = ?",
                         (nome, bc.chave(nome), cor, descricao, json.dumps(apelidos, ensure_ascii=False), json.dumps(regra, ensure_ascii=False), _agora(), marcador_id))
            if tipo == "marcador" and atual["nome"] != nome:
                _renomear_nos_locais(conn, atual["nome"], nome)
                if bc.chave(atual["nome"]) != bc.chave(nome):
                    _registrar_troca(conn, atual["nome"], nome)
            conn.execute("DELETE FROM marcadores_trocas WHERE chave = ?", (bc.chave(nome),))
        else:
            conn.execute("DELETE FROM marcadores_trocas WHERE chave = ?", (bc.chave(nome),))
            marcador_id = f"mrc-{secrets.token_hex(5)}"
            conn.execute("INSERT INTO marcadores (id, nome, chave, tipo, cor, descricao, apelidos_json, regra_json, created_at, updated_at)"
                         " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (marcador_id, nome, bc.chave(nome), tipo, cor, descricao, json.dumps(apelidos, ensure_ascii=False),
                          json.dumps(regra, ensure_ascii=False), _agora(), _agora()))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return next(m for m in catalogo() if m["id"] == marcador_id)


def _renomear_nos_locais(conn, antigo: Optional[str], novo: Optional[str]) -> int:
    """Troca (ou tira, com novo=None) o marcador em todos os locais. Usa a mesma conexão/transação."""
    alvo = bc.chave(antigo)
    n = 0
    for row in conn.execute("SELECT id, dados_json FROM locais").fetchall():
        dados = json.loads(row["dados_json"] or "{}")
        lista = dados.get("marcadores") if isinstance(dados.get("marcadores"), list) else []
        if not any(bc.chave(m) == alvo for m in lista):
            continue
        nova = []
        for m in lista:
            valor = (novo if bc.chave(m) == alvo else m)
            if valor and bc.chave(valor) not in [bc.chave(x) for x in nova]:
                nova.append(valor)
        dados["marcadores"] = nova
        conn.execute("UPDATE locais SET dados_json = ?, updated_at = ? WHERE id = ?", (json.dumps(dados, ensure_ascii=False), _agora(), row["id"]))
        n += 1
    return n


def _registrar_troca(conn, antigo: str, novo: Optional[str]) -> None:
    """Guarda a troca e atualiza as anteriores que apontavam para o nome antigo (A->B, depois B->C: A vai para C)."""
    conn.execute("UPDATE marcadores_trocas SET novo = ?, updated_at = ? WHERE novo IS NOT NULL AND novo = ?", (novo, _agora(), antigo))
    conn.execute("INSERT INTO marcadores_trocas (chave, novo, updated_at) VALUES (?, ?, ?)"
                 " ON CONFLICT(chave) DO UPDATE SET novo = excluded.novo, updated_at = excluded.updated_at",
                 (bc.chave(antigo), novo, _agora()))


def trocas() -> Dict[str, Optional[str]]:
    conn = database.get_connection()
    try:
        return {r["chave"]: r["novo"] for r in conn.execute("SELECT chave, novo FROM marcadores_trocas")}
    finally:
        conn.close()


def excluir(marcador_id: str) -> Dict[str, Any]:
    conn = database.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        atual = conn.execute("SELECT * FROM marcadores WHERE id = ?", (marcador_id,)).fetchone()
        if not atual:
            raise LookupError("Marcador não encontrado.")
        tirados = 0
        if atual["tipo"] == "marcador":
            tirados = _renomear_nos_locais(conn, atual["nome"], None)
            for nome in [atual["nome"], *json.loads(atual["apelidos_json"] or "[]")]:
                _registrar_troca(conn, nome, None)
        conn.execute("DELETE FROM marcadores WHERE id = ?", (marcador_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"nome": atual["nome"], "locais": tirados}


# ---------------------------------------------------------------- uso
def normalizar_marcadores_do_local(lista: Any, cat: Optional[List[Dict[str, Any]]] = None,
                                   trocados: Optional[Dict[str, Optional[str]]] = None) -> List[str]:
    """Marcadores vindos da tela ou do CSV: sem repetição e com a grafia do catálogo (aceita apelido).
    Nome de marcador já renomeado vira o nome novo; de marcador excluído sai (cópia antiga da tela não o traz de volta)."""
    cat = cat if cat is not None else catalogo()
    trocados = trocados if trocados is not None else trocas()
    por_chave = {}
    for m in cat:
        if m["tipo"] != "marcador":
            continue
        por_chave[bc.chave(m["nome"])] = m["nome"]
        for a in m["apelidos"]:
            por_chave.setdefault(bc.chave(a), m["nome"])
    for antigo, novo in CORRECOES_NOME.items():
        por_chave.setdefault(antigo, novo)
    saida: List[str] = []
    for m in lista if isinstance(lista, list) else []:
        nome = _limpar_nome(m.get("nome") if isinstance(m, dict) else m)
        if not nome:
            continue
        k = bc.chave(nome)
        if k not in por_chave and k in trocados:
            if not trocados[k]:
                continue
            nome = trocados[k]
        nome = por_chave.get(bc.chave(nome), nome)
        if bc.chave(nome) not in [bc.chave(x) for x in saida]:
            saida.append(nome)
    return saida


def garantir_no_catalogo(nomes: List[str]) -> None:
    """Marcador novo (digitado na tela ou vindo do CSV) entra no catálogo."""
    existentes = {bc.chave(m["nome"]) for m in catalogo()}
    for nome in nomes:
        if bc.chave(nome) not in existentes:
            try:
                salvar({"nome": nome, "tipo": "marcador"})
            except ValueError:
                pass
            existentes.add(bc.chave(nome))


def normalizar_itens(items: List[Any]) -> List[Any]:
    """Gravação dos locais (tela, CSV, integração): marcadores com a grafia do catálogo; os novos entram no catálogo."""
    cat, trocados = catalogo(), trocas()
    novos: List[str] = []
    for item in items:
        if isinstance(item, dict) and "marcadores" in item:
            item["marcadores"] = normalizar_marcadores_do_local(item.get("marcadores"), cat, trocados)
            novos.extend(item["marcadores"])
    if novos:
        garantir_no_catalogo(novos)
    return items


def previa(locais: List[Dict[str, Any]], regra: Any) -> Dict[str, Any]:
    regra = validar_regra(regra)
    membros = [l for l in locais if bc.unidade_valida(l) and atende(l, regra)]
    return {"regra": regra, "regraTexto": descrever_regra(regra), "locais": len(membros),
            "membros": [{"id": l["id"], "nome": l.get("nome", ""), "tipo": l.get("tipo"), "cidade": l.get("cidade", "")} for l in membros]}


def _links(local: Dict[str, Any]) -> List[str]:
    return [n for n in (bc.normalizar_provedor(p.get("nome"))[0] for p in (local.get("provedores") or [])) if n]


def atende(local: Dict[str, Any], regra: Dict[str, Any]) -> bool:
    """Todas as condições precisam valer (E); dentro de uma condição, qualquer valor serve (OU)."""
    links = _links(local)
    for c in (regra or {}).get("condicoes") or []:
        campo, valores = c.get("campo"), c.get("valores") or []
        if campo == "provedor":
            alvos = {bc.chave(bc.normalizar_provedor(v)[0] or v) for v in valores}
            if not any(bc.chave(n) in alvos for n in links):
                return False
        elif campo == "cidade":
            if bc.chave(local.get("cidade")) not in {bc.chave(v) for v in valores}:
                return False
        elif campo == "tipo":
            if local.get("tipo") not in valores:
                return False
        elif campo == "reserva":
            if (len(links) >= 2) != (valores[:1] != ["nao"]):
                return False
        elif campo == "marcador":
            if not ({bc.chave(m) for m in (local.get("marcadores") or [])} & {bc.chave(v) for v in valores}):
                return False
        elif campo == "sem_provedor":
            if links:
                return False
    return True


def grupos_do_local(local: Dict[str, Any], cat: List[Dict[str, Any]]) -> List[str]:
    return [g["nome"] for g in cat if g["tipo"] == "grupo" and bc.unidade_valida(local) and atende(local, g["regra"])]


def com_contagem(locais: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cat = catalogo()
    validos = [l for l in locais if bc.unidade_valida(l)]
    saida = []
    for m in cat:
        if m["tipo"] == "grupo":
            membros = [l for l in validos if atende(l, m["regra"])]
        else:
            membros = [l for l in validos if bc.chave(m["nome"]) in {bc.chave(x) for x in (l.get("marcadores") or [])}]
        saida.append({**m, "locais": len(membros),
                      "membros": [{"id": l["id"], "nome": l.get("nome", ""), "tipo": l.get("tipo"), "cidade": l.get("cidade", "")} for l in membros],
                      "regraTexto": descrever_regra(m["regra"]) if m["tipo"] == "grupo" else ""})
    return saida


def descrever_regra(regra: Dict[str, Any]) -> str:
    rot_tipo = {"agencia": "agência", "rodoviaria": "rodoviária", "garagem": "garagem"}
    partes = []
    for c in (regra or {}).get("condicoes") or []:
        v = c.get("valores") or []
        ou = lambda xs: " ou ".join(xs)  # noqa: E731
        if c["campo"] == "provedor":
            partes.append(f"provedor é {ou(v)}")
        elif c["campo"] == "cidade":
            partes.append(f"cidade é {ou(v)}")
        elif c["campo"] == "tipo":
            partes.append(f"tipo é {ou([rot_tipo.get(x, x) for x in v])}")
        elif c["campo"] == "reserva":
            partes.append("tem link reserva (2 ou mais links)" if v[:1] != ["nao"] else "não tem link reserva")
        elif c["campo"] == "marcador":
            partes.append(f"tem o marcador {ou(v)}")
        elif c["campo"] == "sem_provedor":
            partes.append("não tem provedor cadastrado")
    return " e ".join(partes)


def citado_na_pergunta(pergunta: str) -> Optional[Dict[str, Any]]:
    """Marcador ou grupo citado (nome ou apelido; nomes maiores primeiro). Siglas curtas só como palavra inteira."""
    alvo = f" {bc.chave(pergunta)} "
    candidatos = []
    for m in catalogo():
        for nome in [m["nome"], *m["apelidos"]]:
            k = bc.chave(nome)
            if len(k) >= 2 and f" {k} " in alvo:
                candidatos.append((len(k), m))
    return max(candidatos, key=lambda x: x[0])[1] if candidatos else None


def _distancia_ate(a: str, b: str, limite: int) -> int:
    if abs(len(a) - len(b)) > limite:
        return limite + 1
    anterior = list(range(len(b) + 1))
    for x, ca in enumerate(a, 1):
        atual = [x]
        for y, cb in enumerate(b, 1):
            atual.append(min(anterior[y] + 1, atual[y - 1] + 1, anterior[y - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def problemas(locais: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Qualidade do cadastro dos marcadores (só com os dados dos locais, sem o catálogo):
    marcador com nome de cidade (melhor um grupo por cidade) e marcadores com nomes quase iguais."""
    validos = [l for l in locais if bc.unidade_valida(l)]
    nomes: Dict[str, str] = {}
    uso: Dict[str, int] = {}
    for l in validos:
        for m in l.get("marcadores") or [] if isinstance(l.get("marcadores"), list) else []:
            k = bc.chave(m)
            if k:
                nomes.setdefault(k, _limpar_nome(m))
                uso[k] = uso.get(k, 0) + 1
    cidades = {bc.chave(l.get("cidade")) for l in validos if l.get("cidade")}
    itens = []
    for k, nome in sorted(nomes.items()):
        if k in cidades:
            itens.append({"problema": "Marcador com nome de cidade", "unidade": "—",
                          "detalhe": f"\"{nome}\" ({uso[k]} local(is)): para cidade, crie um grupo (Configurações › Marcadores e grupos › "
                                     f"+ Criar grupo › Cidade é {nome}); ele inclui sozinho os locais novos da cidade."})
    chaves = sorted(nomes)
    for i, a in enumerate(chaves):
        for b in chaves[i + 1:]:
            if min(len(a), len(b)) >= 6 and _distancia_ate(a, b, 2) <= 2:
                itens.append({"problema": "Marcadores parecidos", "unidade": "—",
                              "detalhe": f"\"{nomes[a]}\" e \"{nomes[b]}\": se forem o mesmo, renomeie um para o outro "
                                         "(Configurações › Marcadores e grupos)."})
    return itens


def catalogo_seguro() -> List[Dict[str, Any]]:
    """Catálogo, ou vazio se o banco ainda não tem a tabela (base de conhecimento gerada fora da API)."""
    try:
        return catalogo()
    except Exception:  # noqa: BLE001 (sem catálogo, os textos saem sem marcadores)
        return []


def regional(nomes: List[str]) -> str:
    """Regional do local: o marcador que começa com "Regional" (ex.: Regional Itabuna); vazio se não tiver."""
    return next((n for n in nomes or [] if bc.chave(n).startswith("REGIONAL ")), "")


def do_local(local: Dict[str, Any], cat: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Marcadores (com a descrição do catálogo, ex.: RT = Rota Transportes Rodoviários), grupos e regional do local."""
    por_chave = {bc.chave(m["nome"]): m for m in cat if m["tipo"] == "marcador"}
    nomes = [m for m in (local.get("marcadores") or []) if isinstance(m, str) and m.strip()]
    marc = [{"nome": n, "descricao": (por_chave.get(bc.chave(n)) or {}).get("descricao", "")} for n in nomes]
    return {"marcadores": marc, "grupos": grupos_do_local(local, cat), "regional": regional(nomes)}


def texto_marcadores(info: Dict[str, Any]) -> str:
    """ "RT (Rota Transportes Rodoviários), Terceirizado" """
    return ", ".join(m["nome"] + (f" ({m['descricao']})" if m["descricao"] else "") for m in info["marcadores"])


def pertence(local: Dict[str, Any], m: Dict[str, Any]) -> bool:
    if m["tipo"] == "grupo":
        return bc.unidade_valida(local) and atende(local, m["regra"])
    return bc.chave(m["nome"]) in {bc.chave(x) for x in (local.get("marcadores") or [])}
