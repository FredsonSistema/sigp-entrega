"""Eventos de saída da API para o n8n (orquestrador).

Cada evento é gravado em `eventos_saida` antes do envio; se o n8n estiver fora do ar, o evento
fica como FALHA/PENDENTE e pode ser reenviado por `POST /api/eventos/reenviar`.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict

from backend.database import enqueue_evento, list_eventos, mark_evento

MAX_TENTATIVAS = 10


def webhook_url() -> str:
    return os.environ.get("SIGP_N8N_EVENTOS_URL", "").strip()


def _send(evento: Dict[str, Any]) -> tuple[bool, str]:
    url = webhook_url()
    if not url:
        return False, "SIGP_N8N_EVENTOS_URL não configurada"
    body = json.dumps({
        "versao": 2,
        "id": evento["id"],
        "evento": evento["evento"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dados": evento["payload"],
    }, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("SIGP_N8N_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300, ""
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # rede, DNS, timeout
        return False, str(exc)


def _deliver(evento: Dict[str, Any]) -> bool:
    ok, error = _send(evento)
    mark_evento(evento["id"], ok, error)
    return ok


def emit(nome: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Registra o evento e tenta entregar em segundo plano, sem atrasar a resposta da API."""
    evento = enqueue_evento(nome, payload)
    if webhook_url():
        threading.Thread(target=_deliver, args=(evento,), daemon=True).start()
    return evento


def retry_pending() -> Dict[str, int]:
    enviados = falhas = 0
    for evento in list_eventos("PENDENTE", 200) + list_eventos("FALHA", 200):
        if evento["tentativas"] >= MAX_TENTATIVAS:
            continue
        if _deliver(evento):
            enviados += 1
        else:
            falhas += 1
    return {"enviados": enviados, "falhas": falhas}
