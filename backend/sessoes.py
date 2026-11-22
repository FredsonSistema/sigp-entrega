"""Login no servidor: usuário e senha, sessões, troca obrigatória de senha e bloqueio por tentativas.

- Pessoas entram com nome de usuário e senha. A senha fica só como hash scrypt (sal aleatório por usuário).
- O administrador cria a pessoa com um perfil; o sistema gera uma senha temporária, mostrada uma única vez.
  No primeiro acesso a pessoa é obrigada a trocar a senha: até trocar, a API recusa todo o resto.
- Sessão: token aleatório entregue no login, guardado só como hash, expira em SESSAO_HORAS ou ao sair.
- 5 senhas erradas seguidas bloqueiam o usuário por 15 minutos.
- Chaves de API (acesso.py) continuam só para integrações (n8n, outro sistema) e a chave do .env (administrador).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from backend import acesso, database

SESSAO_HORAS = 12
MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 15
SENHA_MINIMA = 8
GRUPO_ADMIN = acesso.GRUPO_ADMIN  # perfil Administrador (todas as permissões), só para pessoas


class LoginRecusado(Exception):
    """Usuário, senha ou estado do usuário não permitem entrar (mensagem segura para a tela)."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def garantir_tabelas() -> None:
    conn = database.get_connection()
    try:
        colunas = {r["name"] for r in conn.execute("PRAGMA table_info(acesso_usuarios)")}
        for nome, tipo in (("usuario", "TEXT NOT NULL DEFAULT ''"), ("tipo", "TEXT NOT NULL DEFAULT 'integracao'"),
                           ("senha_hash", "TEXT NOT NULL DEFAULT ''"), ("trocar_senha", "INTEGER NOT NULL DEFAULT 0"),
                           ("tentativas", "INTEGER NOT NULL DEFAULT 0"), ("bloqueado_ate", "TEXT NOT NULL DEFAULT ''")):
            if nome not in colunas:
                conn.execute(f"ALTER TABLE acesso_usuarios ADD COLUMN {nome} {tipo}")
        conn.executescript("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_acesso_usuarios_usuario ON acesso_usuarios(usuario) WHERE usuario != '';
            CREATE TABLE IF NOT EXISTS acesso_sessoes (
                token_hash TEXT PRIMARY KEY, usuario_id TEXT NOT NULL, criada_em TEXT NOT NULL,
                expira_em TEXT NOT NULL, ultimo_uso TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_acesso_sessoes_usuario ON acesso_sessoes(usuario_id);
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- senha
def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${sal.hex()}${h.hex()}"


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, h = guardado.split("$")
        calc = hashlib.scrypt(senha.encode("utf-8"), salt=bytes.fromhex(sal), n=int(n), r=int(r), p=int(p), dklen=len(h) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calc.hex(), h)


def validar_usuario(usuario: Any) -> str:
    u = str(usuario or "").strip().lower()
    if not (3 <= len(u) <= 40) or not all(c.isalnum() or c in "._-" for c in u) or not u[0].isalnum():
        raise ValueError("Nome de usuário: de 3 a 40 caracteres, só letras, números, ponto, hífen ou sublinhado (ex.: fredson.santos).")
    return u


def validar_senha_nova(senha: Any, usuario: str) -> str:
    s = str(senha or "")
    if len(s) < SENHA_MINIMA:
        raise ValueError(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    if len(s) > 200:
        raise ValueError("Senha longa demais.")
    if s.strip().lower() == usuario.lower() or usuario.lower() in s.lower():
        raise ValueError("A senha não pode conter o nome de usuário.")
    if len(set(s)) < 4:
        raise ValueError("A senha é fácil demais: misture letras, números ou símbolos.")
    return s


def senha_temporaria() -> str:
    # Sem caracteres parecidos (0/O, 1/l/I); fácil de ditar, difícil de adivinhar (~60 bits).
    alfabeto = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(alfabeto) for _ in range(4)) for _ in range(3))


# ---------------------------------------------------------------- pessoas
def _row_por_usuario(conn, usuario: str):
    return conn.execute("SELECT * FROM acesso_usuarios WHERE usuario = ? AND tipo = 'pessoa'", (usuario,)).fetchone()


def existe_administrador() -> bool:
    conn = database.get_connection()
    try:
        return bool(conn.execute("SELECT 1 FROM acesso_usuarios WHERE tipo = 'pessoa' AND grupo_id = ? AND ativo = 1",
                                 (GRUPO_ADMIN,)).fetchone())
    finally:
        conn.close()


def criar_pessoa(nome: str, usuario: str, grupo_id: str, ajustes: Optional[Dict[str, bool]] = None,
                 senha: Optional[str] = None, trocar: bool = True) -> Tuple[Dict[str, Any], str]:
    """Cria a pessoa. Sem senha informada, gera a temporária (devolvida uma única vez)."""
    usuario = validar_usuario(usuario)
    nome = str(nome or "").strip()[:80] or usuario
    ajustes = acesso._validar_ajustes(ajustes or {})
    temporaria = senha is None
    senha = senha_temporaria() if temporaria else validar_senha_nova(senha, usuario)
    conn = database.get_connection()
    try:
        if grupo_id != GRUPO_ADMIN and not conn.execute("SELECT 1 FROM acesso_grupos WHERE id = ?", (grupo_id,)).fetchone():
            raise ValueError("Escolha um perfil (grupo de permissões).")
        if conn.execute("SELECT 1 FROM acesso_usuarios WHERE usuario = ?", (usuario,)).fetchone():
            raise ValueError("Já existe um usuário com esse nome de usuário.")
        usuario_id = f"usr-{secrets.token_hex(6)}"
        agora = _iso(_agora())
        conn.execute(
            "INSERT INTO acesso_usuarios (id, nome, grupo_id, ajustes_json, chave_hash, chave_prefixo, ativo, created_at, updated_at,"
            " usuario, tipo, senha_hash, trocar_senha) VALUES (?, ?, ?, ?, ?, '', 1, ?, ?, ?, 'pessoa', ?, ?)",
            # chave_hash é única e obrigatória na tabela: pessoa recebe um valor aleatório que nunca é entregue.
            (usuario_id, nome, grupo_id, json.dumps(ajustes), "pessoa-" + secrets.token_hex(24), agora, agora,
             usuario, hash_senha(senha), int(trocar)))
        conn.commit()
    finally:
        conn.close()
    return pessoa(usuario_id), senha


def pessoa(usuario_id: str) -> Dict[str, Any]:
    return next(u for u in acesso.listar_usuarios() if u["id"] == usuario_id)


def redefinir_senha(usuario_id: str) -> Tuple[Dict[str, Any], str]:
    """Administrador gera nova senha temporária: a pessoa troca no próximo acesso; sessões abertas caem."""
    temp = senha_temporaria()
    conn = database.get_connection()
    try:
        n = conn.execute("UPDATE acesso_usuarios SET senha_hash = ?, trocar_senha = 1, tentativas = 0, bloqueado_ate = '', updated_at = ?"
                         " WHERE id = ? AND tipo = 'pessoa'", (hash_senha(temp), _iso(_agora()), usuario_id)).rowcount
        conn.execute("DELETE FROM acesso_sessoes WHERE usuario_id = ?", (usuario_id,))
        conn.commit()
    finally:
        conn.close()
    if not n:
        raise LookupError("Pessoa não encontrada.")
    return pessoa(usuario_id), temp


def encerrar_sessoes_do_usuario(usuario_id: str) -> None:
    conn = database.get_connection()
    try:
        conn.execute("DELETE FROM acesso_sessoes WHERE usuario_id = ?", (usuario_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- login e sessão
def entrar(usuario: str, senha: str) -> Tuple[str, Dict[str, Any]]:
    """Confere usuário e senha e abre a sessão. Devolve (token, quem). Mensagem genérica para não revelar quem existe."""
    erro = "Usuário ou senha incorretos."
    try:
        usuario = validar_usuario(usuario)
    except ValueError:
        raise LoginRecusado(erro)
    conn = database.get_connection()
    try:
        row = _row_por_usuario(conn, usuario)
        agora = _agora()
        if not row:
            hash_senha(senha or "x")  # mesmo custo de tempo de um usuário real
            raise LoginRecusado(erro)
        if row["bloqueado_ate"] and row["bloqueado_ate"] > _iso(agora):
            raise LoginRecusado(f"Muitas tentativas erradas. Tente de novo depois de {BLOQUEIO_MINUTOS} minutos ou peça ao administrador para redefinir a senha.")
        if not conferir_senha(senha or "", row["senha_hash"]):
            tentativas = row["tentativas"] + 1
            bloqueio = _iso(agora + timedelta(minutes=BLOQUEIO_MINUTOS)) if tentativas >= MAX_TENTATIVAS else ""
            conn.execute("UPDATE acesso_usuarios SET tentativas = ?, bloqueado_ate = ? WHERE id = ?",
                         (0 if bloqueio else tentativas, bloqueio, row["id"]))
            conn.commit()
            raise LoginRecusado(erro)
        if not row["ativo"]:
            raise LoginRecusado("Usuário desativado. Fale com o administrador.")
        token = secrets.token_urlsafe(32)
        conn.execute("UPDATE acesso_usuarios SET tentativas = 0, bloqueado_ate = '', ultimo_uso = ? WHERE id = ?", (_iso(agora), row["id"]))
        conn.execute("DELETE FROM acesso_sessoes WHERE expira_em < ?", (_iso(agora),))
        conn.execute("INSERT INTO acesso_sessoes (token_hash, usuario_id, criada_em, expira_em, ultimo_uso) VALUES (?, ?, ?, ?, ?)",
                     (acesso._hash(token), row["id"], _iso(agora), _iso(agora + timedelta(hours=SESSAO_HORAS)), _iso(agora)))
        conn.commit()
    finally:
        conn.close()
    return token, identificar_sessao(token)


def identificar_sessao(token: str) -> Optional[Dict[str, Any]]:
    """Quem é o dono da sessão (com trocarSenha), ou None se a sessão não existe, expirou ou o usuário foi desativado."""
    if not token:
        return None
    conn = database.get_connection()
    try:
        s = conn.execute("SELECT * FROM acesso_sessoes WHERE token_hash = ?", (acesso._hash(token),)).fetchone()
        if not s or s["expira_em"] < _iso(_agora()):
            return None
        row = conn.execute("SELECT * FROM acesso_usuarios WHERE id = ? AND tipo = 'pessoa'", (s["usuario_id"],)).fetchone()
        if not row or not row["ativo"]:
            return None
        grupo_row = conn.execute("SELECT * FROM acesso_grupos WHERE id = ?", (row["grupo_id"],)).fetchone()
        if s["ultimo_uso"][:16] != _iso(_agora())[:16]:
            conn.execute("UPDATE acesso_sessoes SET ultimo_uso = ? WHERE token_hash = ?", (_iso(_agora()), s["token_hash"]))
            conn.commit()
    finally:
        conn.close()
    base = {"id": row["id"], "nome": row["nome"], "usuario": row["usuario"], "trocarSenha": bool(row["trocar_senha"]),
            "sessaoExpiraEm": s["expira_em"]}
    if row["grupo_id"] == GRUPO_ADMIN:
        return {**base, "perfil": acesso.ADMIN, "grupo": "Administrador", "permissoes": acesso.TODAS}
    grupo = acesso._grupo(grupo_row) if grupo_row else None
    usuario = {"ajustes": json.loads(row["ajustes_json"] or "{}")}
    return {**base, "perfil": "usuario", "grupo": (grupo or {}).get("nome", "—"), "permissoes": acesso.efetivas(usuario, grupo)}


def sair(token: str) -> None:
    conn = database.get_connection()
    try:
        conn.execute("DELETE FROM acesso_sessoes WHERE token_hash = ?", (acesso._hash(token),))
        conn.commit()
    finally:
        conn.close()


def trocar_senha(usuario_id: str, atual: str, nova: str, token_atual: str) -> None:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM acesso_usuarios WHERE id = ? AND tipo = 'pessoa'", (usuario_id,)).fetchone()
        if not row or not conferir_senha(atual or "", row["senha_hash"]):
            raise ValueError("A senha atual está incorreta.")
        nova = validar_senha_nova(nova, row["usuario"])
        if conferir_senha(nova, row["senha_hash"]):
            raise ValueError("A nova senha precisa ser diferente da atual.")
        conn.execute("UPDATE acesso_usuarios SET senha_hash = ?, trocar_senha = 0, updated_at = ? WHERE id = ?",
                     (hash_senha(nova), _iso(_agora()), usuario_id))
        # As outras sessões desta pessoa caem; a atual continua.
        conn.execute("DELETE FROM acesso_sessoes WHERE usuario_id = ? AND token_hash != ?", (usuario_id, acesso._hash(token_atual)))
        conn.commit()
    finally:
        conn.close()
