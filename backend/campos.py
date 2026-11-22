"""Regras de campos de identificação das notas lidas de PDF (número, chave) e datas.

Decisão do usuário (12/11/2026): quando o número ou a chave da nota vierem vazios ou preenchidos
incorretamente, grava-se o valor padrão ``999999999``. Valor, vencimento e nome do emissor NÃO
recebem valor padrão: são obrigatórios e, se o OCR não os achar, a entrada é manual.

O valor padrão não é uma identidade fiscal. Por isso ``eh_padrao`` deve ser usado em toda
comparação (conciliação, duplicidade, nota candidata) para tratá-lo como "sem identificador".
"""
from __future__ import annotations

import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict

VALOR_PADRAO = "999999999"

_CNPJ_RE = re.compile(r"^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$")
_CPF_RE = re.compile(r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$")
_DATA_RE = re.compile(r"^\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}$")
_DINHEIRO_RE = re.compile(r"^(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}$|^R\$")
_NUMERO_VALIDO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./\-]{0,29}$")
TAMANHOS_CHAVE = (44, 50)  # NF-e/NFCom: 44 dígitos; NFS-e nacional: 50 (confirmar com documentos reais)


def eh_padrao(valor: Any) -> bool:
    """True se o valor é o padrão (ou equivalente a "sem identificador")."""
    return str(valor or "").strip() == VALOR_PADRAO


def _sem_identificador(valor: Any) -> bool:
    texto = str(valor or "").strip()
    return not texto or texto == VALOR_PADRAO


def motivo_numero_invalido(valor: Any) -> str:
    """Devolve o motivo se o número lido não parece um número de documento; vazio se está ok."""
    texto = str(valor or "").strip()
    if not texto:
        return "vazio"
    if texto == VALOR_PADRAO:
        return ""  # já é o padrão; tratado à parte
    if not re.search(r"\d", texto):
        return "sem dígitos (provável rótulo)"
    if re.fullmatch(r"0+", re.sub(r"\D", "", texto)) and not re.search(r"[1-9]", texto):
        return "só zeros"
    compacto = texto.replace(" ", "")
    if _CNPJ_RE.match(compacto) or _CPF_RE.match(compacto):
        return "parece CNPJ/CPF"
    if _DATA_RE.match(compacto):
        return "parece uma data"
    if _DINHEIRO_RE.match(compacto):
        return "parece um valor em dinheiro"
    if not _NUMERO_VALIDO_RE.match(compacto):
        return "formato fora do esperado"
    return ""


def motivo_chave_invalida(valor: Any) -> str:
    texto = re.sub(r"\s+", "", str(valor or ""))
    if not texto:
        return "vazia"
    if texto == VALOR_PADRAO:
        return ""
    digitos = re.sub(r"\D", "", texto)
    if digitos != texto:
        return "contém caracteres que não são dígitos"
    if len(digitos) not in TAMANHOS_CHAVE:
        return f"tamanho {len(digitos)} (esperado {' ou '.join(map(str, TAMANHOS_CHAVE))})"
    return ""


def aplicar_padrao_identificacao(campos: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica o valor padrão a número e chave vazios ou inválidos, preservando o que foi lido.

    Altera e devolve ``campos``. Marca ``numeroPadrao``/``chavePadrao`` e guarda o texto lido em
    ``numeroOriginal``/``chaveOriginal`` quando ele existia mas foi rejeitado.
    """
    revisar = list(campos.get("camposParaRevisar") or [])
    for campo, rotulo, motivo_fn in (
        ("numero", "numero", motivo_numero_invalido),
        ("chave", "chave", motivo_chave_invalida),
    ):
        atual = str(campos.get(campo) or "").strip()
        if atual == VALOR_PADRAO:
            campos[f"{campo}Padrao"] = True
            if campo == "numero" and rotulo not in revisar:
                revisar.append(rotulo)
            continue
        motivo = motivo_fn(atual)
        if campo == "chave" and atual and motivo:
            # Decisão do usuário (14/11/2026): a chave lida tem prioridade; o padrão só entra quando não há chave.
            # Tamanho fora de 44/50 (ex.: 41 dígitos em XML de teste) fica como veio, com o motivo anotado.
            campos[campo] = atual
            campos[f"{campo}Padrao"] = False
            campos[f"{campo}Motivo"] = motivo
            continue
        if motivo:
            if atual:
                campos[f"{campo}Original"] = atual[:160]
                campos[f"{campo}Motivo"] = motivo
            campos[campo] = VALOR_PADRAO
            campos[f"{campo}Padrao"] = True
            # Chave vazia é normal em boleto/fatura: só vai para revisão quando algo foi lido e rejeitado.
            if (atual or campo == "numero") and rotulo not in revisar:
                revisar.append(rotulo)
        else:
            campos[campo] = atual
            campos[f"{campo}Padrao"] = False
    # "numero/chave" era o aviso antigo de ambos ausentes; agora a revisão é por campo.
    campos["camposParaRevisar"] = [item for item in revisar if item != "numero/chave"]
    return campos


def mesclar_identificacao(novo: Dict[str, Any], salvo: Dict[str, Any]) -> None:
    """Regra de atualização: dado real vence o padrão; padrão nunca substitui dado real.

    ``novo`` é a leitura atual (já com padrão aplicado); ``salvo`` é o que estava gravado.
    Altera ``novo`` no lugar.
    """
    for campo in ("numero", "chave"):
        if eh_padrao(novo.get(campo)) and not _sem_identificador(salvo.get(campo)):
            novo[campo] = str(salvo[campo]).strip()
            novo[f"{campo}Padrao"] = False
            novo.pop(f"{campo}Original", None)
            novo.pop(f"{campo}Motivo", None)
            revisar = novo.get("camposParaRevisar") or []
            novo["camposParaRevisar"] = [item for item in revisar if item != campo]


# Campos fiscais que o XML define (decisão do usuário, 13/11/2026: o XML tem prioridade sobre o PDF).
# Mesma regra de n8n/lib/xml_fiscal.js (aplicarPrioridadeXml).
CAMPOS_PRIORIDADE_XML = (
    "numero", "serie", "chave", "emissorNome", "cnpjEmissor", "cnpjDestinatario",
    "valorTotal", "dataEmissao", "dataVencimento", "descricaoServico",
)
_CAMPOS_DIVERGENCIA_XML = ("numero", "valorTotal", "dataVencimento", "cnpjEmissor")


def _vazio_pdf(valor: Any) -> bool:
    return valor is None or str(valor).strip() in ("", VALOR_PADRAO)


def _mesmo_identificador(campo: str, a: Any, b: Any) -> bool:
    """Mesmo número com outra formatação não é divergência: "000004572" (PDF) = "4572" (XML); CNPJ com ou sem pontuação."""
    limpo = lambda v: str(v if v is not None else "").strip().upper()  # noqa: E731
    if campo == "cnpjEmissor":
        return re.sub(r"\D", "", limpo(a)) == re.sub(r"\D", "", limpo(b))
    if campo == "numero":
        n = lambda v: re.sub(r"^0+(?=.)", "", re.sub(r"[^0-9A-Z]", "", limpo(v)))  # noqa: E731
        return n(a) == n(b)
    return limpo(a) == limpo(b)


def aplicar_prioridade_xml(campos: Dict[str, Any], xml: Dict[str, Any]) -> Dict[str, Any]:
    """Junta a leitura do PDF com o XML da nota: o XML vence; diferenças relevantes vão para ``divergenciasXml``."""
    saida = dict(campos)
    if not isinstance(xml, dict) or not xml.get("ok"):
        return saida
    divergencias = []
    for campo in CAMPOS_PRIORIDADE_XML:
        do_xml = xml.get(campo)
        if do_xml in (None, ""):
            continue
        do_pdf = saida.get(campo)
        if not _vazio_pdf(do_pdf) and campo in _CAMPOS_DIVERGENCIA_XML:
            try:
                iguais = abs(float(do_pdf) - float(do_xml)) < 0.01 if campo == "valorTotal" else _mesmo_identificador(campo, do_pdf, do_xml)
            except (TypeError, ValueError):
                iguais = False
            if not iguais:
                divergencias.append({"campo": campo, "pdf": do_pdf, "xml": do_xml})
        saida[campo] = do_xml
    if xml.get("destinatarioNome") and not saida.get("destinatarioNome"):
        saida["destinatarioNome"] = xml["destinatarioNome"]
    if xml.get("servicos"):
        saida["servicos"] = xml["servicos"]
    saida["origemCampos"] = "xml"
    saida["divergenciasXml"] = divergencias
    preenchidos = {campo for campo in CAMPOS_PRIORIDADE_XML if not _vazio_pdf(saida.get(campo))}
    revisar = [item for item in (saida.get("camposParaRevisar") or []) if item not in preenchidos]
    if divergencias and "divergenciasXml" not in revisar:
        revisar.append("divergenciasXml")
    saida["camposParaRevisar"] = revisar
    return saida


def _parse_data(valor: Any) -> str:
    """Converte textos de data/hora comuns (ISO, RFC 2822 de e-mail, dd/mm/aaaa) em AAAA-MM-DD."""
    texto = str(valor or "").strip()
    if not texto:
        return ""
    candidatos = (
        lambda: datetime.fromisoformat(texto.replace("Z", "+00:00")).date(),
        lambda: parsedate_to_datetime(texto).date(),
        lambda: datetime.strptime(texto[:10], "%d/%m/%Y").date(),
    )
    for conv in candidatos:
        try:
            return conv().isoformat()
        except (ValueError, TypeError, IndexError):
            continue
    return ""


def aplicar_data_emissao(campos: Dict[str, Any], recebida_em: Any = "", criada_em: Any = "") -> Dict[str, Any]:
    """Se a emissão não foi achada no documento, usa a data de recebimento e registra a origem."""
    campos["dataEmissao"] = _parse_data(campos.get("dataEmissao")) or ""
    if campos["dataEmissao"]:
        campos.setdefault("dataEmissaoOrigem", "documento")
        return campos
    recebimento = _parse_data(recebida_em) or _parse_data(criada_em) or date.today().isoformat()
    campos["dataEmissao"] = recebimento
    campos["dataEmissaoOrigem"] = "recebimento"
    revisar = list(campos.get("camposParaRevisar") or [])
    if "dataEmissao" not in revisar:
        revisar.append("dataEmissao")
    campos["camposParaRevisar"] = revisar
    return campos
