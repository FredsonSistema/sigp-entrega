"""Cofre de chaves: segredos de integração (hoje o Client ID e o Client Secret do Google; depois, a chave do ERP)
gravados criptografados no banco do SIGp.

- AES-256-GCM (biblioteca cryptography). A chave mestra fica só em SIGP_COFRE_CHAVE, no .env do servidor: nunca no
  banco, no código ou no GitHub. Um backup ou uma cópia do banco sem o .env não revela nenhum segredo.
- O nome do segredo entra como dado autenticado: um valor cifrado não pode ser copiado para o lugar de outro.
- A API nunca devolve o valor. Mostra só se está definido, os 4 últimos caracteres (valores longos), quem salvou e quando.
  Só o próprio servidor decifra (ler_valor), para entregar ao n8n.
- Sem chave mestra válida, o cofre recusa gravar: nada é salvo em texto puro.
- Trocar a chave mestra invalida o que foi salvo com a anterior (a tela pede para colar de novo; nada é decifrado errado).
  Limite: quem tem acesso ao servidor e ao .env consegue decifrar (o n8n tem o mesmo limite com as credenciais dele).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend import database

VARIAVEL = "SIGP_COFRE_CHAVE"
VERSAO = "v1"
# Segredos aceitos (lista fechada: o cofre não guarda qualquer coisa que chegue).
SEGREDOS: Dict[str, Dict[str, Any]] = {
    "google_client_id": {"rotulo": "Google · Client ID", "max": 300},
    "google_client_secret": {"rotulo": "Google · Client Secret", "max": 300},
}
_SO_IMPRIMIVEIS = re.compile(r"^[\x21-\x7e]+$")  # sem espaço, quebra de linha ou caractere de controle


class CofreErro(Exception):
    """Erro com mensagem pronta para a tela (nunca contém o valor do segredo)."""


def gerar_chave() -> str:
    """Chave mestra nova (32 bytes aleatórios em base64 url-safe) para o SIGP_COFRE_CHAVE do .env."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _chave_mestra() -> Optional[bytes]:
    bruto = os.environ.get(VARIAVEL, "").strip()
    if not bruto:
        return None
    try:
        chave = base64.urlsafe_b64decode(bruto + "=" * (-len(bruto) % 4))
    except (binascii.Error, ValueError):
        return None
    return chave if len(chave) == 32 else None


def _id_da_chave(chave: bytes) -> str:
    # Identifica a chave mestra sem revelá-la (para saber se um segredo foi salvo com outra chave).
    return hashlib.sha256(b"sigp-cofre-id:" + chave).hexdigest()[:12]


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def garantir_tabelas() -> None:
    conn = database.get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cofre_segredos (
                nome TEXT PRIMARY KEY, cifrado TEXT NOT NULL, final TEXT NOT NULL DEFAULT '', chave_id TEXT NOT NULL,
                atualizado_por TEXT NOT NULL DEFAULT '', atualizado_em TEXT NOT NULL
            )""")
        conn.commit()
    finally:
        conn.close()


def disponivel() -> Dict[str, Any]:
    if _chave_mestra():
        return {"disponivel": True, "motivo": ""}
    motivo = (f"{VARIAVEL} não está definida no .env do servidor." if not os.environ.get(VARIAVEL, "").strip()
              else f"{VARIAVEL} no .env é inválida (precisa ter 32 bytes em base64).")
    return {"disponivel": False, "motivo": motivo + " Sem ela, o cofre não grava nada."}


def _definicao(nome: str) -> Dict[str, Any]:
    if nome not in SEGREDOS:
        raise CofreErro("Segredo desconhecido.")
    return SEGREDOS[nome]


def estado() -> Dict[str, Any]:
    """O que a tela pode saber: nunca o valor."""
    chave = _chave_mestra()
    atual = _id_da_chave(chave) if chave else ""
    conn = database.get_connection()
    try:
        linhas = {r["nome"]: r for r in conn.execute("SELECT nome, final, chave_id, atualizado_por, atualizado_em FROM cofre_segredos")}
    finally:
        conn.close()
    itens = []
    for nome, definicao in SEGREDOS.items():
        r = linhas.get(nome)
        itens.append({
            "nome": nome, "rotulo": definicao["rotulo"], "definido": bool(r),
            "final": r["final"] if r else "", "atualizadoPor": r["atualizado_por"] if r else "",
            "atualizadoEm": r["atualizado_em"] if r else "",
            # Salvo com outra chave mestra (ou sem chave agora): não dá para usar; é preciso colar de novo.
            "legivel": bool(r) and bool(atual) and r["chave_id"] == atual,
        })
    return {**disponivel(), "segredos": itens}


def salvar(nome: str, valor: Any, quem: str) -> Dict[str, Any]:
    definicao = _definicao(nome)
    chave = _chave_mestra()
    if not chave:
        raise CofreErro(disponivel()["motivo"])
    texto = str(valor or "").strip() if isinstance(valor, str) else ""
    if not texto:
        raise CofreErro("Cole o valor completo.")
    if len(texto) > definicao["max"] or not _SO_IMPRIMIVEIS.match(texto):
        raise CofreErro(f"Valor inválido para {definicao['rotulo']}: confira se colou só a chave, sem espaços nem quebras de linha.")
    nonce = secrets.token_bytes(12)
    cifrado = AESGCM(chave).encrypt(nonce, texto.encode("utf-8"), f"sigp-cofre:{VERSAO}:{nome}".encode("utf-8"))
    guardado = f"{VERSAO}:" + base64.b64encode(nonce + cifrado).decode("ascii")
    final = texto[-4:] if len(texto) >= 16 else ""
    conn = database.get_connection()
    try:
        conn.execute(
            "INSERT INTO cofre_segredos (nome, cifrado, final, chave_id, atualizado_por, atualizado_em) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(nome) DO UPDATE SET cifrado = excluded.cifrado, final = excluded.final, chave_id = excluded.chave_id, "
            "atualizado_por = excluded.atualizado_por, atualizado_em = excluded.atualizado_em",
            (nome, guardado, final, _id_da_chave(chave), (quem or "")[:80], _agora()))
        conn.commit()
    finally:
        conn.close()
    return estado()


def apagar(nome: str) -> Dict[str, Any]:
    _definicao(nome)
    conn = database.get_connection()
    try:
        conn.execute("DELETE FROM cofre_segredos WHERE nome = ?", (nome,))
        conn.commit()
    finally:
        conn.close()
    return estado()


def ler_valor(nome: str) -> Optional[str]:
    """Só para uso interno do servidor (entregar ao n8n). None = não definido. CofreErro = não dá para decifrar."""
    _definicao(nome)
    conn = database.get_connection()
    try:
        r = conn.execute("SELECT cifrado, chave_id FROM cofre_segredos WHERE nome = ?", (nome,)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    chave = _chave_mestra()
    if not chave:
        raise CofreErro(disponivel()["motivo"])
    if r["chave_id"] != _id_da_chave(chave):
        raise CofreErro(f"{SEGREDOS[nome]['rotulo']} foi salvo com outra chave mestra. Cole o valor de novo.")
    versao, _, corpo = str(r["cifrado"]).partition(":")
    try:
        bruto = base64.b64decode(corpo)
        return AESGCM(chave).decrypt(bruto[:12], bruto[12:], f"sigp-cofre:{versao}:{nome}".encode("utf-8")).decode("utf-8")
    except (InvalidTag, binascii.Error, ValueError) as exc:
        raise CofreErro(f"{SEGREDOS[nome]['rotulo']} está corrompido ou foi alterado no banco. Cole o valor de novo.") from exc
