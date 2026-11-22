from __future__ import annotations

import unicodedata
from typing import Any, Dict, Iterable

from backend.campos import eh_padrao


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(
        "".join(char for char in text if not unicodedata.combining(char)).split()
    )


def invoice_identity_matches(launched: Dict[str, Any], paid: Dict[str, Any]) -> bool | None:
    # O valor padrão (999999999) não é identidade fiscal: conta como "sem chave/número".
    launched_key = "" if eh_padrao(launched.get("chave")) else _normalized(launched.get("chave"))
    paid_key = "" if eh_padrao(paid.get("chave")) else _normalized(paid.get("chave"))
    if launched_key and paid_key:
        return launched_key == paid_key

    launched_number = "" if eh_padrao(launched.get("numero")) else _normalized(launched.get("numero"))
    paid_number = "" if eh_padrao(paid.get("numero")) else _normalized(paid.get("numero"))
    launched_issuer = _normalized(launched.get("provedor_nome") or launched.get("provedorNome"))
    paid_issuer = _normalized(paid.get("provedor_nome") or paid.get("provedorNome"))
    if not all((launched_number, paid_number, launched_issuer, paid_issuer)):
        return None

    launched_series = _normalized(launched.get("serie"))
    paid_series = _normalized(paid.get("serie"))
    launched_date = str(launched.get("data_emissao") or launched.get("dataEmissao") or "")[:10]
    paid_date = str(paid.get("data_emissao") or paid.get("dataEmissao") or "")[:10]
    return (
        launched_number == paid_number
        # Série vazia de um lado é "não informada" (como a emissão), não divergência.
        and (not launched_series or not paid_series or launched_series == paid_series)
        and launched_issuer == paid_issuer
        and (not launched_date or not paid_date or launched_date == paid_date)
    )


def locations_match(launched: Dict[str, Any], paid: Dict[str, Any]) -> bool | None:
    launched_type = _normalized(launched.get("entidade_tipo") or launched.get("entidadeTipo"))
    paid_type = _normalized(paid.get("entidade_tipo") or paid.get("entidadeTipo"))
    if launched_type and paid_type and launched_type != paid_type:
        return False

    launched_id = str(launched.get("entidade_id") or launched.get("entidadeId") or "").strip()
    paid_id = str(paid.get("entidade_id") or paid.get("entidadeId") or "").strip()
    if launched_id and paid_id:
        return launched_id == paid_id and bool(launched_type or paid_type)

    launched_city = _normalized(launched.get("local_cidade") or launched.get("localCidade"))
    paid_city = _normalized(paid.get("local_cidade") or paid.get("localCidade"))
    if not launched_city or not paid_city:
        return None
    return launched_city == paid_city and (not launched_type or not paid_type or launched_type == paid_type)


def payment_belongs_to_invoice(
    launched: Dict[str, Any],
    paid: Dict[str, Any],
) -> bool:
    return (
        invoice_identity_matches(launched, paid) is True
        and locations_match(launched, paid) is True
    )


def _service_signature(items: Iterable[Dict[str, Any]]) -> list[tuple[str, float]]:
    signature = []
    for item in items:
        description = _normalized(item.get("descricao") or item.get("description"))
        try:
            amount = round(float(item.get("valorTotal") or item.get("valor") or 0), 2)
        except (TypeError, ValueError):
            amount = 0.0
        signature.append((description, amount))
    return sorted(signature)


def compare_reconciliation(
    launched: Dict[str, Any],
    paid: Dict[str, Any],
    total_paid: float,
    invoice_amount: float | None = None,
) -> Dict[str, Any]:
    identity_match = invoice_identity_matches(launched, paid)
    location_match = locations_match(launched, paid)
    launched_total = float(launched.get("valor_total") or launched.get("valorTotal") or 0)
    paid_invoice_total = float(paid.get("valor_total") or paid.get("valorTotal") or 0)
    paid_amount = float(total_paid or 0)
    has_invoice_reference = invoice_amount is not None and float(invoice_amount) > 0
    reference_amount = float(invoice_amount or 0)
    value_match = (
        launched_total > 0
        and paid_invoice_total > 0
        and paid_amount > 0
        and abs(launched_total - reference_amount) < 0.01
        and abs(paid_invoice_total - reference_amount) < 0.01
        and abs(paid_amount - reference_amount) < 0.01
        if has_invoice_reference
        else (
            launched_total > 0
            and paid_invoice_total > 0
            and abs(launched_total - paid_invoice_total) < 0.01
            and abs(launched_total - paid_amount) < 0.01
        )
    )

    launched_services = launched.get("servicos") or []
    paid_services = paid.get("servicos") or []
    classifications = [
        str(item.get("classificacao") or "PENDENTE").upper()
        for item in [*launched_services, *paid_services]
    ]
    services_pending = any(value not in {"CONTRATADO", "DIVERGENTE"} for value in classifications)
    services_divergent = "DIVERGENTE" in classifications
    if not launched_services and not paid_services:
        services_match: bool | None = True
    elif not launched_services or not paid_services:
        services_match = None
        services_pending = True
    else:
        services_match = _service_signature(launched_services) == _service_signature(paid_services)
        if not services_match:
            services_divergent = True

    comparison = {
        "chave": identity_match is True,
        "valor": value_match,
        "cidade": location_match is True,
        "servicos": services_match is True,
    }

    if identity_match is False or location_match is False or services_divergent:
        status = "DIVERGENCIA"
        observation = "Chave, local ou serviços divergem entre a nota lançada e o pagamento."
    elif has_invoice_reference and (
        (launched_total > 0 and abs(launched_total - reference_amount) >= 0.01)
        or (paid_invoice_total > 0 and abs(paid_invoice_total - reference_amount) >= 0.01)
        or paid_amount - reference_amount >= 0.01
    ):
        status = "DIVERGENCIA"
        observation = "O valor lançado ou pago diverge da fatura PDF de referência."
    elif has_invoice_reference and paid_amount > 0 and paid_amount - reference_amount <= -0.01:
        status = "PAGO_PARCIAL"
        observation = "O pagamento acumulado é parcial em relação à fatura PDF."
    elif not has_invoice_reference and launched_total > 0 and paid_invoice_total > 0 and abs(launched_total - paid_invoice_total) >= 0.01:
        status = "DIVERGENCIA"
        observation = "O valor total da nota paga diverge do valor da nota lançada."
    elif not has_invoice_reference and launched_total > 0 and paid_amount - launched_total >= 0.01:
        status = "DIVERGENCIA"
        observation = "O valor pago acumulado excede o valor da nota."
    elif (
        identity_match is None
        or location_match is None
        or launched_total <= 0
        or paid_invoice_total <= 0
        or paid_amount <= 0
        or services_pending
    ):
        status = "PENDENTE"
        observation = "Faltam dados ou classificação dos serviços para concluir a conciliação."
    elif not has_invoice_reference and paid_amount - launched_total <= -0.01:
        status = "PAGO_PARCIAL"
        observation = "O pagamento acumulado é parcial; ainda não libera a conciliação."
    elif not value_match:
        status = "DIVERGENCIA"
        observation = "O valor pago diverge do valor lançado."
    else:
        status = "MATCH"
        observation = "Identidade, local, serviços e valores conferem com a nota lançada."

    return {
        "status": status,
        "observacao": observation,
        "comparacao": comparison,
        "valorPagoAcumulado": round(paid_amount, 2),
    }
