"""Situações 3 a 5 — identificação do cliente na fatura: código do cliente, contrato e endereço de instalação.

Quando o mesmo provedor atende vários locais (HE-NET, Claro, Vox...) ou há vários locais na mesma cidade, o nome
do provedor não diz qual local é. O código do cliente/contrato diz. A regra é a mesma do WF-08
(n8n/wf08/wf08_lib.js, lerIdentificadoresCliente); os casos de teste são os mesmos nos dois lados.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List

_ROTULO_CLIENTE = r"(?:c[oó]d(?:igo|\.)?\s*(?:do\s*)?cliente|n[ºo°.]*\s*(?:do\s*)?cliente|id\s*(?:do\s*)?cliente)"
_ROTULO_CONTRATO = r"(?:n[uú]mero\s*do\s*contrato(?:\s*\(id\))?|n[ºo°.]+\s*(?:do\s*)?contrato|ref\.?\s*a\s*contrato|contrato(?:\(s\))?)"
_VALOR = r"[:\-]?\s*([A-Z0-9][A-Z0-9.\-/]{0,24})"
_PADROES = (
    ("cliente", re.compile(_ROTULO_CLIENTE + r"\s*" + _VALOR, re.IGNORECASE)),
    ("contrato", re.compile(_ROTULO_CONTRATO + r"\s*" + _VALOR, re.IGNORECASE)),
)
_ROTULO_SO_CLIENTE = re.compile(_ROTULO_CLIENTE, re.IGNORECASE)
_TOKEN_COLUNA = re.compile(r"\S+")
_INSTALACAO = re.compile(r"(?:endere[cç]o\s*de\s*)?instala[cç][aã]o\s*:\s*([^\n]{8,80})", re.IGNORECASE)
_DATA = re.compile(r"^\d{1,2}[/.]\d{1,2}([/.]\d{2,4})?$")
MAXIMO = 6


def normalizar(valor: Any) -> str:
    """Comparação: só letras e números, maiúsculas, sem zeros à esquerda (00077120 = 77120)."""
    texto = unicodedata.normalize("NFD", str(valor or "")).encode("ascii", "ignore").decode("ascii").upper()
    texto = re.sub(r"[^A-Z0-9]", "", texto)
    return texto.lstrip("0") or texto


def _valido(valor: str) -> bool:
    digitos = re.sub(r"\D", "", valor)
    return bool(digitos) and 3 <= len(normalizar(valor)) <= 15 and len(digitos) <= 15 and not _DATA.match(valor)


def ler(texto: str) -> List[Dict[str, str]]:
    """Identificadores do cliente no texto da fatura: [{"tipo": "cliente"|"contrato"|"instalacao", "valor": ...}]."""
    texto = str(texto or "")
    linhas = texto.splitlines()
    achados: List[Dict[str, str]] = []
    vistos = set()

    def guardar(tipo: str, valor: str) -> None:
        chave = (tipo, normalizar(valor))
        if chave[1] and chave not in vistos and len(achados) < MAXIMO:
            vistos.add(chave)
            achados.append({"tipo": tipo, "valor": valor.strip(".-/ ")})

    for indice, linha in enumerate(linhas):
        for tipo, padrao in _PADROES:
            for m in padrao.finditer(linha):
                if _valido(m.group(1)):
                    guardar(tipo, m.group(1))
        # Rótulo de coluna ("Código do cliente" com outro título ao lado ou no fim da linha): o valor está na linha
        # de baixo, na mesma coluna (o texto do PDF preserva as posições).
        for m in _ROTULO_SO_CLIENTE.finditer(linha):
            depois = linha[m.end():m.end() + 30]
            if re.match(r"\s*[:\-]?\s*[A-Z0-9]*\d", depois, re.IGNORECASE) or indice + 1 >= len(linhas):
                continue
            perto = [
                (abs(t.start() - m.start()), t.group(0)) for t in _TOKEN_COLUNA.finditer(linhas[indice + 1])
                if re.fullmatch(r"[A-Z0-9][A-Z0-9.\-/]{3,24}", t.group(0), re.IGNORECASE) and _valido(t.group(0))
            ]
            perto = [p for p in perto if p[0] <= 15]
            if perto:
                guardar("cliente", min(perto)[1])
        m = _INSTALACAO.search(linha)
        if m and re.search(r"[A-Za-z]{3,}", m.group(1)):
            guardar("instalacao", " ".join(m.group(1).split())[:80])
    return achados


def codigos(identificadores: Iterable[Dict[str, Any]]) -> List[str]:
    """Valores normalizados para comparar: cliente/contrato e o endereço de instalação (prefixo END:)."""
    saida = []
    for i in identificadores or []:
        valor = normalizar(i.get("valor"))
        if valor and i.get("tipo") in ("cliente", "contrato"):
            saida.append(valor)
        elif valor and i.get("tipo") == "instalacao":
            saida.append("END:" + valor)
    return saida


def codigos_do_provedor(provedor: Dict[str, Any]) -> List[str]:
    saida = [normalizar(v) for v in re.split(r"[,;\n]+", str(provedor.get("codigosCliente") or "")) if normalizar(v)]
    if normalizar(provedor.get("enderecoInstalacao")):
        saida.append("END:" + normalizar(provedor.get("enderecoInstalacao")))
    return saida
