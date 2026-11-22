"""Remetentes da busca de faturas no Gmail (WF-08). O administrador altera em Configurações > E-mail das faturas.
Ordem: lista salva pela tela (tabela app_state) > PADRAO (domínios dos provedores). O n8n pede a busca pronta por
GET /api/configuracoes/email-faturas antes de cada leitura do Gmail, então ninguém precisa abrir o n8n para trocar.

Endereços pessoais (e-mail de teste de um colaborador) ficam só no banco: nunca no código nem no GitHub.
A busca é montada aqui, e não no n8n, para que só entre e-mail ou domínio válido (sem operadores do Gmail).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from backend import database

CHAVE = "config_email_faturas_v1"
MAX_REMETENTES = 60

# Domínios públicos dos provedores (não são dado pessoal). Valem enquanto a tela não salvar uma lista.
PADRAO = [
    "henet.com.br", "brisanet.com.br", "ixnet.com.br", "itsbrasil.net", "kasatech.net",
    "tinettecnologia.com.br", "netplacetelecom.net", "proxxima.net", "minasonline.net.br",
    "minhaclaro.com.br", "netcanes.com.br", "sigaonmais.net.br", "mma.net.br", "internetvox.com.br",
    "infortel.net.br", "infotecprovedor.net", "voanet.com.br", "fsonline.com.br", "opix.com.br",
]

# Fora dos remetentes, a busca é fixa: exclui o que já tem etiqueta do SIGp e aceita assunto ou anexo de cobrança.
# No Gmail, { } é OU: uma mensagem entra pelo remetente conhecido OU pelo assunto OU pelo anexo.
ETIQUETAS = "-label:sigp-importado -label:sigp-ignorado -label:sigp-sem-anexo"
OUTROS_CRITERIOS = (
    'subject:(fatura OR boleto OR "nota fiscal" OR "conta digital" OR nfcom OR "segunda via") '
    '(has:attachment filename:pdf (fatura OR boleto OR "nota fiscal")) '
    '(has:attachment filename:xml ("nota fiscal" OR nfse OR "nfs-e" OR nfe OR nfcom))'
)

_ROTULO = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMINIO = rf"(?:{_ROTULO}\.)+[a-z]{{2,24}}"
_REMETENTE = re.compile(rf"^(?:[a-z0-9._+-]{{1,64}}@)?{_DOMINIO}$")


def _separar(texto: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,;\s]+", texto or "") if p.strip()]


def validar(remetentes: Any) -> List[str]:
    """Normaliza (minúsculas, sem repetição) e valida. Aceita e-mail ou domínio. Lança ValueError para a tela."""
    if isinstance(remetentes, str):
        remetentes = _separar(remetentes)
    if not isinstance(remetentes, list):
        raise ValueError("Envie os remetentes como uma lista de e-mails ou domínios.")
    vistos: List[str] = []
    for bruto in remetentes:
        item = str(bruto or "").strip().lower()
        if item.startswith("@"):
            item = item[1:]
        if not item:
            continue
        if len(item) > 254 or not _REMETENTE.match(item) or ".." in item:
            raise ValueError(f"Remetente inválido (use um e-mail ou um domínio, como provedor.com.br): {item[:80]}")
        if item not in vistos:
            vistos.append(item)
    if len(vistos) > MAX_REMETENTES:
        raise ValueError(f"Use no máximo {MAX_REMETENTES} remetentes.")
    return vistos


def consulta(remetentes: List[str]) -> str:
    """Busca do Gmail usada pelo WF-08 (o n8n acrescenta só o filtro de data da leitura automática)."""
    de = f"from:({' OR '.join(remetentes)}) " if remetentes else ""
    return f"{ETIQUETAS} {{{de}{OUTROS_CRITERIOS}}}"


def ler() -> Dict[str, Any]:
    salvo = database.get_app_state([CHAVE]).get(CHAVE)
    if isinstance(salvo, dict) and isinstance(salvo.get("remetentes"), list):
        dados = {"remetentes": salvo["remetentes"], "origem": "tela", "atualizadoPor": salvo.get("atualizadoPor", ""),
                 "atualizadoEm": salvo.get("atualizadoEm", "")}
    else:
        dados = {"remetentes": list(PADRAO), "origem": "padrão", "atualizadoPor": "", "atualizadoEm": ""}
    return {**dados, "consulta": consulta(dados["remetentes"]), "padrao": list(PADRAO), "maximo": MAX_REMETENTES}


def salvar(remetentes: Any, quem: str, quando: str) -> Dict[str, Any]:
    lista = validar(remetentes)
    database.save_app_state(CHAVE, {"remetentes": lista, "atualizadoPor": quem, "atualizadoEm": quando})
    return ler()
