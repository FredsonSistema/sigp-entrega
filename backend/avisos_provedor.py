"""Situação 1 — vários e-mails da mesma fatura: fatura nova, 2ª via, lembrete, aviso de atraso, pagamento confirmado.

O tipo de e-mail ("evento") é lido do assunto, do corpo e do começo do PDF por frases claras; sem frase clara,
vale o que a LLM disser (no WF-08). Um aviso procura a cobrança já lançada (nota lançada) do mesmo provedor:
- exatamente uma candidata: o aviso é vinculado; no pagamento confirmado o SIGp registra o pagamento sozinho;
- nenhuma ou várias: o aviso fica na caixa (Inconclusivo) com o motivo e as candidatas, para o operador decidir.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional

EVENTOS = ("fatura_nova", "segunda_via", "lembrete_vencimento", "aviso_atraso", "pagamento_confirmado")
EVENTOS_AVISO = ("lembrete_vencimento", "aviso_atraso", "pagamento_confirmado")
ROTULOS = {
    "fatura_nova": "Fatura nova", "segunda_via": "2ª via", "lembrete_vencimento": "Lembrete de vencimento",
    "aviso_atraso": "Aviso de atraso", "pagamento_confirmado": "Pagamento confirmado",
}
PADRAO = "999999999"


def _norm(texto: Any) -> str:
    texto = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(texto.lower().split())


# Frases claras, da mais forte para a mais fraca. Atraso e lembrete só valem no assunto/corpo do e-mail: o boleto
# em PDF sempre tem "após o vencimento cobrar multa", e isso não é aviso de atraso.
_PAGAMENTO = re.compile(
    r"pagamento (foi )?(confirmado|recebido|identificado|aprovado|compensado|efetuado com sucesso|realizado com sucesso)"
    r"|recebemos (o )?(seu )?pagamento|confirmacao de pagamento|obrigad[oa] pelo pagamento"
    r"|(fatura|boleto|conta) (foi )?(paga|quitada|liquidada)|baixa (do|de) pagamento|pagamento (ja )?consta"
)
_SEGUNDA_VIA = re.compile(r"\b2\s?[a\u00aao\u00ba]?\s?via\b|segunda via")
_ATRASO = re.compile(
    r"(fatura|boleto|conta|pagamento|mensalidade)s? (esta |estao |se encontra |consta |constam )?(em atraso|vencid[oa]s?|atrasad[oa]s?|em aberto|pendentes?)"
    r"|aviso de (atraso|debito|cobranca|suspensao|bloqueio)|evite (o |a )?(bloqueio|suspensao)|pendencia financeira"
    r"|regularize|debito(s)? em aberto|servico (sera )?suspenso"
)
_LEMBRETE = re.compile(
    r"lembrete|vence (hoje|amanha|em \d+ dias?)|vencimento (proximo|hoje|amanha)|esta proxim[oa] do vencimento|nao esqueca"
)


def detectar_evento(assunto: str = "", corpo: str = "", texto: str = "") -> Dict[str, Any]:
    email = _norm(f"{assunto} {corpo}")
    documento = _norm(str(texto or "")[:1500])
    for nome, padrao, onde in (
        ("pagamento_confirmado", _PAGAMENTO, email + " " + documento[:600]),
        ("segunda_via", _SEGUNDA_VIA, email + " " + documento[:600]),
        ("aviso_atraso", _ATRASO, email),
        ("lembrete_vencimento", _LEMBRETE, email),
    ):
        achado = padrao.search(onde)
        if achado:
            return {"tipo": nome, "origem": "regra", "frase": achado.group(0)[:80]}
    return {"tipo": "fatura_nova", "origem": "padrao", "frase": ""}


def _data(valor: Any) -> Optional[date]:
    texto = str(valor or "")[:10]
    try:
        return date.fromisoformat(texto)
    except ValueError:
        pass
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _so_digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def data_pagamento_no_texto(texto: str) -> Optional[str]:
    """Data citada como pagamento ("pago em 16/11/2026", "pagamento realizado em 16/11/2026")."""
    m = re.search(r"pag[oa]\w*\s+(?:\w+\s+){0,3}(?:em|no dia|dia)\s+(\d{2}/\d{2}/\d{4})", _norm(texto))
    d = _data(m.group(1)) if m else None
    return d.isoformat() if d else None


def candidatas(
    aviso: Dict[str, Any],
    notas_lancadas: Iterable[Dict[str, Any]],
    saldo: Callable[[Dict[str, Any]], float],
    mesma_empresa: Callable[[Any, Any], bool],
    locais_do_remetente: Iterable[str] = (),
    nome_util: Callable[[str], bool] = lambda _nome: True,
) -> List[Dict[str, Any]]:
    """Notas lançadas que podem ser a cobrança deste aviso. Identificação forte (linha digitável, chave ou número)
    decide sozinha; sem ela vale o vencimento igual e, por último, a cobrança em aberto mais próxima no tempo."""
    evento = aviso.get("evento")
    emissor = str(aviso.get("emissorNome") or "")
    locais = set(locais_do_remetente)
    recebida = _data(aviso.get("recebidaEm")) or date.today()
    # E-mail do remetente cadastrado num local: a busca fica nesse(s) local(is). Sem isso, vale o nome do provedor,
    # desde que tenha marca própria (nome genérico como "Fibra" ou "Financeiro" não identifica ninguém).
    nome_ok = bool(emissor) and nome_util(emissor)
    notas_lancadas = list(notas_lancadas)
    if locais:
        do_provedor = [n for n in notas_lancadas if str(n.get("entidade_id") or "") in locais]
        mesmo_nome = [n for n in do_provedor if nome_ok and mesma_empresa(n.get("provedor_nome"), emissor)]
        if mesmo_nome:
            do_provedor = mesmo_nome
    elif nome_ok:
        do_provedor = [n for n in notas_lancadas if mesma_empresa(n.get("provedor_nome"), emissor)]
    else:
        do_provedor = []
    if evento == "pagamento_confirmado":
        do_provedor = [n for n in do_provedor if saldo(n) > 0.01]
    linha = _so_digitos(aviso.get("linhaDigitavel"))
    chave = _so_digitos(aviso.get("chave"))
    numero = str(aviso.get("numero") or "").strip()
    fortes = [
        n for n in do_provedor
        if (chave and len(chave) >= 44 and _so_digitos(n.get("chave")) == chave)
        or (numero and numero != PADRAO and str(n.get("numero") or "").strip() == numero)
        or (linha and linha in _so_digitos(n.get("observacao")))
    ]
    if fortes:
        return fortes
    venc = _data(aviso.get("dataVencimento"))
    if venc:
        mesmo_venc = [n for n in do_provedor if _data(n.get("data_vencimento")) == venc]
        if mesmo_venc:
            return mesmo_venc
    # Sem identificação: cobranças com vencimento entre 45 dias antes e 10 dias depois do e-mail.
    janela = [
        n for n in do_provedor
        if (d := _data(n.get("data_vencimento"))) and recebida - timedelta(days=45) <= d <= recebida + timedelta(days=10)
    ]
    if evento == "pagamento_confirmado" and len(janela) > 1:
        # Pagamento sem identificação e com várias em aberto: só decide se o valor bate com uma só.
        try:
            valor = float(aviso.get("valorTotal") or 0)
        except (TypeError, ValueError):
            valor = 0.0
        if valor > 0:
            mesmo_valor = [n for n in janela if abs(saldo(n) - valor) <= 0.01]
            if mesmo_valor:
                return mesmo_valor
    return janela


def resumo_candidata(n: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": n.get("id"), "numero": n.get("numero") or "", "provedor": n.get("provedor_nome") or "",
            "local": n.get("local_nome") or "", "entidadeTipo": n.get("entidade_tipo") or "",
            "entidadeId": n.get("entidade_id") or "", "vencimento": str(n.get("data_vencimento") or "")[:10],
            "valor": n.get("valor_total")}


def agora_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
