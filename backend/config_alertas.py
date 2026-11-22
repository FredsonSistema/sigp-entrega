"""E-mails que recebem os alertas diários (WF-06). O administrador altera em Configurações > Alertas por e-mail.

Ordem: lista salva pela tela (tabela app_state) > SIGP_RELATORIO_EMAIL do .env (aceita vários, separados por vírgula
ou ponto e vírgula) > nenhum. O n8n lê a lista por GET /api/configuracoes/alertas antes de enviar.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from backend import database

CHAVE = "config_alertas_email_v1"
MAX_EMAILS = 10
_EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


def _separar(texto: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,;\s]+", texto or "") if p.strip()]


def validar(emails: Any) -> List[str]:
    """Normaliza (minúsculas, sem repetição) e valida. Lança ValueError com mensagem para a tela."""
    if isinstance(emails, str):
        emails = _separar(emails)
    if not isinstance(emails, list):
        raise ValueError("Envie emails como uma lista de endereços.")
    vistos: List[str] = []
    for bruto in emails:
        email = str(bruto or "").strip().lower()
        if not email:
            continue
        if len(email) > 254 or not _EMAIL.match(email):
            raise ValueError(f"E-mail inválido: {email[:80]}")
        if email not in vistos:
            vistos.append(email)
    if len(vistos) > MAX_EMAILS:
        raise ValueError(f"Use no máximo {MAX_EMAILS} e-mails.")
    return vistos


def ler() -> Dict[str, Any]:
    salvo = database.get_app_state([CHAVE]).get(CHAVE)
    if isinstance(salvo, dict) and isinstance(salvo.get("emails"), list):
        return {"emails": salvo["emails"], "origem": "tela", "atualizadoPor": salvo.get("atualizadoPor", ""),
                "atualizadoEm": salvo.get("atualizadoEm", "")}
    try:
        do_env = validar(os.environ.get("SIGP_RELATORIO_EMAIL", ""))
    except ValueError:
        do_env = []
    return {"emails": do_env, "origem": ".env" if do_env else "nenhum", "atualizadoPor": "", "atualizadoEm": ""}


def salvar(emails: Any, quem: str, quando: str) -> Dict[str, Any]:
    lista = validar(emails)
    database.save_app_state(CHAVE, {"emails": lista, "atualizadoPor": quem, "atualizadoEm": quando})
    return ler()
