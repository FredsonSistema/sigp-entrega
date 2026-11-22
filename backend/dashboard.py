from __future__ import annotations

from datetime import date
from math import isfinite
import unicodedata
from typing import Any, Dict, Iterable

from backend.campos import eh_padrao
from backend.reconciliation import payment_belongs_to_invoice


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def _amount(value: Any) -> float:
    try:
        result = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return result if isfinite(result) else 0.0


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def default_period(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    month = today.month - 11
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1).isoformat(), today.isoformat()


def _in_period(value: Any, start: date, end: date) -> bool:
    parsed = _parse_date(value)
    return parsed is not None and start <= parsed <= end


def _invoice_fingerprint(note: Dict[str, Any]) -> str:
    key = "" if eh_padrao(note.get("chave")) else _normalized(note.get("chave"))
    if key:
        return f"key:{key}"
    fallback = (
        _normalized(note.get("provedor_nome") or note.get("provedorNome")),
        "" if eh_padrao(note.get("numero")) else _normalized(note.get("numero")),
        _normalized(note.get("serie")),
        str(note.get("data_emissao") or note.get("dataEmissao") or "")[:10],
        _normalized(note.get("entidade_tipo") or note.get("entidadeTipo")),
        str(note.get("entidade_id") or note.get("entidadeId") or ""),
    )
    return "|".join(fallback) if fallback[0] and fallback[1] else f"id:{note.get('id') or id(note)}"


def _note_status(
    note: Dict[str, Any],
    latest_reconciliation: Dict[str, Dict[str, Any]],
) -> str:
    reconciliation = latest_reconciliation.get(str(note.get("id") or ""))
    return str(
        (reconciliation or {}).get("status")
        or note.get("status")
        or "PENDENTE"
    ).upper()


ELIGIBLE_PAYMENT_STATUSES = {"PAGA", "PAGO_PARCIAL", "PAGO_COM_ATRASO", "PAGO_COM_VALOR_INFERIOR"}
# Desempate quando duas conciliações da mesma nota têm o mesmo horário: vale a mais avançada.
STATUS_RANK = {"PENDENTE": 0, "PAGO_PARCIAL": 1, "AGUARDANDO_FATURA": 2, "DIVERGENCIA": 3, "MATCH": 4}


def latest_reconciliations(rows: Iterable[Dict[str, Any]]) -> dict[str, Dict[str, Any]]:
    """Conciliação vigente por nota lançada: mais recente por horário, depois por status, depois por ordem de gravação."""
    latest: dict[str, Dict[str, Any]] = {}
    ordered = sorted(
        rows,
        key=lambda item: (
            str(item.get("updated_at") or ""),
            STATUS_RANK.get(str(item.get("status") or "").upper(), 0),
            int(item.get("_ordem") or 0),
        ),
        reverse=True,
    )
    for row in ordered:
        latest.setdefault(str(row.get("nota_lancada_id") or ""), row)
    return latest


def _month_keys(start: date, end: date) -> list[str]:
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def build_sig_summary(
    launched_notes: Iterable[Dict[str, Any]],
    paid_notes: Iterable[Dict[str, Any]],
    reconciliations: Iterable[Dict[str, Any]],
    start_date: str,
    end_date: str,
    entity_type: str = "",
    provider_query: str = "",
    status_filter: str = "",
    today: date | None = None,
) -> Dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    launched = list(launched_notes)
    paid = list(paid_notes)
    reconciliation_rows = list(reconciliations)

    fingerprints: dict[str, list[Dict[str, Any]]] = {}
    for note in launched:
        fingerprints.setdefault(_invoice_fingerprint(note), []).append(note)
    ambiguous_fingerprints = {
        fingerprint for fingerprint, rows in fingerprints.items() if len(rows) > 1
    }
    ambiguous_ids = {
        str(note.get("id") or "")
        for fingerprint in ambiguous_fingerprints
        for note in fingerprints[fingerprint]
    }

    latest_reconciliation = latest_reconciliations(reconciliation_rows)

    eligible_payments = [
        note for note in paid
        if str(note.get("status") or "").upper() in ELIGIBLE_PAYMENT_STATUSES
    ]
    filters_entity = _normalized(entity_type)
    filters_provider = _normalized(provider_query)
    filters_status = str(status_filter or "").strip().upper()

    selected_notes = []
    excluded_ambiguous = 0
    missing_issue_date = 0
    for note in launched:
        issue_date = note.get("data_emissao") or note.get("dataEmissao")
        if not _parse_date(issue_date):
            missing_issue_date += 1
        if str(note.get("id") or "") in ambiguous_ids:
            excluded_ambiguous += 1
            continue
        if not _in_period(issue_date, start, end):
            continue
        if filters_entity and _normalized(note.get("entidade_tipo") or note.get("entidadeTipo")) != filters_entity:
            continue
        if filters_provider and filters_provider not in _normalized(note.get("provedor_nome") or note.get("provedorNome")):
            continue
        if filters_status and _note_status(note, latest_reconciliation) != filters_status:
            continue
        selected_notes.append(note)

    monthly = {
        month: {"mes": month, "lancado": 0.0, "pago": 0.0}
        for month in _month_keys(start, end)
    }
    provider_totals: dict[str, float] = {}
    location_totals: dict[str, float] = {}
    status_counts: dict[str, int] = {}
    matched_payment_ids: set[str] = set()
    paid_in_period = 0.0
    pending_balance = 0.0
    overdue_count = 0
    missing_invoice = 0
    # Pagamentos contam até o fim do período; "vencida" é medida em relação a hoje (ou ao fim, se o período já passou).
    as_of = end
    overdue_reference = min(end, today or date.today())

    for note in selected_notes:
        amount = _amount(note.get("valor_total") or note.get("valorTotal"))
        issue_date = _parse_date(note.get("data_emissao") or note.get("dataEmissao"))
        if issue_date:
            month = issue_date.strftime("%Y-%m")
            if month in monthly:
                monthly[month]["lancado"] += amount
        provider = str(note.get("provedor_nome") or note.get("provedorNome") or "Sem provedor").strip()
        location = " · ".join(
            part for part in (
                str(note.get("entidade_tipo") or note.get("entidadeTipo") or "").strip(),
                str(note.get("local_nome") or note.get("localNome") or "Local não informado").strip(),
            )
            if part
        )
        provider_totals[provider] = provider_totals.get(provider, 0.0) + amount
        location_totals[location] = location_totals.get(location, 0.0) + amount
        status = _note_status(note, latest_reconciliation)
        status_counts[status] = status_counts.get(status, 0) + 1

        related_payments = [
            item for item in eligible_payments
            if payment_belongs_to_invoice(note, item)
            and (
                not _parse_date(item.get("data_pagamento") or item.get("dataPagamento"))
                or _parse_date(item.get("data_pagamento") or item.get("dataPagamento")) <= as_of
            )
        ]
        total_paid = sum(_amount(item.get("valor_pago") or item.get("valorPago")) for item in related_payments)
        pending_balance += max(0.0, amount - total_paid)
        due_date = _parse_date(note.get("data_vencimento") or note.get("dataVencimento"))
        if due_date and due_date < overdue_reference and amount - total_paid > 0.01:
            overdue_count += 1
        if "fatura_anexada" in note and not note.get("fatura_anexada"):
            missing_invoice += 1

        for payment in related_payments:
            payment_id = str(payment.get("id") or "")
            payment_date = _parse_date(payment.get("data_pagamento") or payment.get("dataPagamento"))
            if payment_id in matched_payment_ids or not payment_date:
                continue
            matched_payment_ids.add(payment_id)
            if start <= payment_date <= end:
                value = _amount(payment.get("valor_pago") or payment.get("valorPago"))
                paid_in_period += value
                month = payment_date.strftime("%Y-%m")
                if month in monthly:
                    monthly[month]["pago"] += value

    selected_paid = [
        payment for payment in eligible_payments
        if str(payment.get("id") or "") in matched_payment_ids
        and _in_period(payment.get("data_pagamento") or payment.get("dataPagamento"), start, end)
    ]
    latest_counts = {
        "match": sum(count for status, count in status_counts.items() if status == "MATCH"),
        "pendente": sum(count for status, count in status_counts.items() if status in {"PENDENTE", "PAGO_PARCIAL", "RECEBIDA"}),
        "divergencia": sum(count for status, count in status_counts.items() if status in {"DIVERGENCIA", "DIVERGENCIA_CADASTRAL"}),
        "aguardandoFatura": status_counts.get("AGUARDANDO_FATURA", 0),
    }
    return {
        "periodo": {"inicio": start.isoformat(), "fim": end.isoformat()},
        "indicadores": {
            "notasLancadas": len(selected_notes),
            "valorLancado": round(sum(_amount(note.get("valor_total") or note.get("valorTotal")) for note in selected_notes), 2),
            "pagamentos": len(selected_paid),
            "valorPago": round(paid_in_period, 2),
            "valorPendente": round(pending_balance, 2),
            "vencidas": overdue_count,
            "conciliadas": latest_counts["match"],
            "pendentes": latest_counts["pendente"],
            "divergencias": latest_counts["divergencia"],
            "aguardandoFatura": latest_counts["aguardandoFatura"],
            "semFatura": missing_invoice,
        },
        "qualidade": {
            "notasAmbiguasExcluidas": excluded_ambiguous,
            "gruposChaveDuplicada": len(ambiguous_fingerprints),
            "notasSemDataEmissao": missing_issue_date,
        },
        "mensal": [
            {
                "mes": row["mes"],
                "lancado": round(row["lancado"], 2),
                "pago": round(row["pago"], 2),
            }
            for row in monthly.values()
        ],
        "porProvedor": [
            {"nome": name, "valor": round(value, 2)}
            for name, value in sorted(provider_totals.items(), key=lambda item: item[1], reverse=True)[:8]
        ],
        "porLocal": [
            {"nome": name, "valor": round(value, 2)}
            for name, value in sorted(location_totals.items(), key=lambda item: item[1], reverse=True)[:8]
        ],
        "status": status_counts,
    }
