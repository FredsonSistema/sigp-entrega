from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List

from backend.dashboard import ELIGIBLE_PAYMENT_STATUSES, _amount, _parse_date, latest_reconciliations
from backend import fatura_esperada
from backend.provedores import mesma_empresa
from backend.reconciliation import payment_belongs_to_invoice

TIPOS_LOCAL = {"agencia": "Agência", "rodoviaria": "Rodoviária", "garagem": "Garagem"}


def _due_date(day: int, year: int, month: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def provider_due_status(
    dia_vencimento: Any, pago_ate: Any, today: date, window_days: int, data_vencimento: Any = None,
) -> Dict[str, Any] | None:
    """Mesma regra do navegador (providerDueStatus em agencias.html).

    1) Com a data da fatura atual (preenchida pela fatura PDF ou pela associação do Gmail), ela manda:
       sem pagamento que a cubra, vencida/vence hoje/vence em breve; paga, sem alerta.
    2) Sem a data, vale o dia de vencimento: ciclo mais recente vencido sem pagamento que cubra = VENCIDO.
    """
    due = _parse_date(data_vencimento)
    if due:
        paid_until = _parse_date(pago_ate)
        if paid_until and paid_until >= due:
            return None
        status = _date_status(due, today, window_days)
        return {"status": status, "vencimento": due.isoformat(), "dias": (due - today).days} if status else None
    try:
        day = int(dia_vencimento)
    except (TypeError, ValueError):
        return None
    if not 1 <= day <= 31:
        return None
    this_due = _due_date(day, today.year, today.month)
    most_recent = this_due if today >= this_due else _due_date(day, *_shift_month(today.year, today.month, -1))
    paid_until = _parse_date(pago_ate)
    covered = bool(paid_until and paid_until > most_recent)
    if not covered and today > most_recent:
        return {"status": "VENCIDO", "vencimento": most_recent.isoformat(), "dias": (most_recent - today).days}
    if not covered and today == most_recent:
        return {"status": "VENCE_HOJE", "vencimento": most_recent.isoformat(), "dias": 0}
    upcoming = this_due if today < this_due else _due_date(day, *_shift_month(today.year, today.month, 1))
    if today >= upcoming - timedelta(days=window_days):
        return {"status": "VENCE_EM_BREVE", "vencimento": upcoming.isoformat(), "dias": (upcoming - today).days}
    return None


def _date_status(due: date, today: date, window_days: int) -> str | None:
    if due < today:
        return "VENCIDO"
    if due == today:
        return "VENCE_HOJE"
    if due <= today + timedelta(days=window_days):
        return "VENCE_EM_BREVE"
    return None


SEVERIDADE = {"VENCIDO": "alta", "DIVERGENCIA": "alta", "VENCE_HOJE": "alta", "AGUARDANDO_FATURA": "media",
              "VENCE_EM_BREVE": "media", "FATURA_AUSENTE": "baixa", "PAGO_COM_ATRASO": "media", "PAGO": "info",
              "FATURA_NAO_RECEBIDA": "media", "FATURA_NA_CAIXA": "media", "LEITURA_GMAIL_PARADA": "alta"}
TIPOS_PADRAO = {"vencimento", "fatura_ausente", "divergencia", "pagamento", "fatura_nao_recebida"}


def build_alerts(
    locais: Iterable[Dict[str, Any]],
    launched_notes: Iterable[Dict[str, Any]],
    paid_notes: Iterable[Dict[str, Any]],
    reconciliations: Iterable[Dict[str, Any]],
    today: date,
    window_days: int = 7,
    tipos: set[str] | None = None,
    received_notes: Iterable[Dict[str, Any]] | None = None,
    ultima_leitura: str | None = None,
) -> List[Dict[str, Any]]:
    tipos = tipos or TIPOS_PADRAO
    alerts: list[Dict[str, Any]] = []
    locais = list(locais)
    local_names = {str(item["id"]): item for item in locais}

    def local_label(entity_type: str, entity_id: str, fallback: str = "") -> str:
        local = local_names.get(entity_id)
        name = (local or {}).get("nome") or fallback or entity_id or "Local não informado"
        tipo = TIPOS_LOCAL.get(entity_type, entity_type or "Local")
        # "Agência Itacaré" já diz o tipo: não vira "Agência Agência Itacaré".
        if str(name).strip().casefold().startswith(tipo.casefold()):
            return str(name).strip()
        return f"{tipo} {name}".strip()

    if "vencimento" in tipos:
        for local in locais:
            label = local_label(local.get("tipo", ""), str(local["id"]))
            for provider in local.get("provedores") or []:
                status = provider_due_status(
                    provider.get("diaVencimento"), provider.get("pagoAte"), today, window_days,
                    provider.get("dataVencimento"),
                )
                if not status:
                    continue
                alerts.append({
                    "tipo": "vencimento", "origem": "provedor", "status": status["status"],
                    "severidade": SEVERIDADE[status["status"]], "vencimento": status["vencimento"], "dias": status["dias"],
                    "entidadeTipo": local.get("tipo"), "entidadeId": local["id"], "local": label,
                    "provedor": provider.get("nome") or "", "valor": _amount(provider.get("valor")),
                    "mensagem": f"{label} · {provider.get('nome') or 'provedor'}: {status['status'].replace('_', ' ').lower()} ({status['vencimento']})",
                })
            due = _parse_date(local.get("vencimento_fatura"))
            status = _date_status(due, today, window_days) if due else None
            if status:
                alerts.append({
                    "tipo": "vencimento", "origem": "local", "status": status, "severidade": SEVERIDADE[status],
                    "vencimento": due.isoformat(), "dias": (due - today).days, "entidadeTipo": local.get("tipo"),
                    "entidadeId": local["id"], "local": label, "provedor": "", "valor": 0.0,
                    "mensagem": f"{label}: fatura {status.replace('_', ' ').lower()} ({due.isoformat()})",
                })

    launched = list(launched_notes)
    payments = [item for item in paid_notes if str(item.get("status") or "").upper() in ELIGIBLE_PAYMENT_STATUSES]
    latest = latest_reconciliations(reconciliations)

    for note in launched:
        note_id = str(note.get("id") or "")
        entity_type = str(note.get("entidade_tipo") or "")
        entity_id = str(note.get("entidade_id") or "")
        label = local_label(entity_type, entity_id, str(note.get("local_nome") or ""))
        base = {
            "notaLancadaId": note_id, "numero": note.get("numero") or "", "entidadeTipo": entity_type,
            "entidadeId": entity_id, "local": label, "provedor": note.get("provedor_nome") or "",
            "valor": _amount(note.get("valor_total")),
        }
        reconciliation_status = str((latest.get(note_id) or {}).get("status") or "").upper()
        paid_total = sum(_amount(p.get("valor_pago")) for p in payments if payment_belongs_to_invoice(note, p))
        balance = _amount(note.get("valor_total")) - paid_total

        if "vencimento" in tipos and balance > 0.01:
            due = _parse_date(note.get("data_vencimento"))
            status = _date_status(due, today, window_days) if due else None
            if status:
                alerts.append({**base, "tipo": "vencimento", "origem": "nota", "status": status,
                               "severidade": SEVERIDADE[status], "vencimento": due.isoformat(),
                               "dias": (due - today).days, "saldo": round(balance, 2),
                               "mensagem": f"Nota {base['numero'] or note_id} ({label}): {status.replace('_', ' ').lower()} com saldo de " + f"R$ {balance:.2f}".replace(".", ",")})

        if "fatura_ausente" in tipos and not note.get("fatura_anexada"):
            status = "AGUARDANDO_FATURA" if reconciliation_status == "AGUARDANDO_FATURA" else "FATURA_AUSENTE"
            alerts.append({**base, "tipo": "fatura_ausente", "origem": "nota", "status": status,
                           "severidade": SEVERIDADE[status],
                           "mensagem": f"Nota {base['numero'] or note_id} ({label}): fatura ainda não disponível"
                           + (" — pagamento conciliado aguardando a fatura" if status == "AGUARDANDO_FATURA" else "")})

        if "pagamento" in tipos:
            # Pagas nos últimos dias (janela do alerta): informa o pagamento e destaca o atraso.
            due = _parse_date(note.get("data_vencimento"))
            for payment in payments:
                if not payment_belongs_to_invoice(note, payment):
                    continue
                paid_day = _parse_date(payment.get("data_pagamento"))
                if not paid_day or not (today - timedelta(days=window_days) <= paid_day <= today):
                    continue
                atraso = (paid_day - due).days if due else 0
                status = "PAGO_COM_ATRASO" if atraso > 0 else "PAGO"
                valor_txt = f"R$ {_amount(payment.get('valor_pago')):.2f}".replace(".", ",")
                alerts.append({
                    **base, "tipo": "pagamento", "origem": "nota", "status": status, "severidade": SEVERIDADE[status],
                    "vencimento": due.isoformat() if due else "", "dataPagamento": paid_day.isoformat(),
                    "valorPago": _amount(payment.get("valor_pago")), "dias": (paid_day - today).days, "atrasoDias": max(atraso, 0),
                    "mensagem": f"Nota {base['numero'] or note_id} ({label}): paga em {paid_day.strftime('%d/%m/%Y')}, {valor_txt}"
                                + (f", {atraso} dia(s) após o vencimento" if atraso > 0 else ", no prazo"),
                })

        if "divergencia" in tipos and reconciliation_status == "DIVERGENCIA":
            alerts.append({**base, "tipo": "divergencia", "origem": "conciliacao", "status": "DIVERGENCIA",
                           "severidade": "alta", "observacao": (latest.get(note_id) or {}).get("observacao") or "",
                           "mensagem": f"Nota {base['numero'] or note_id} ({label}): conciliação divergente, requer correção manual"})

    # Situação 2: fatura do mês que não chegou (ou chegou e está na caixa sem associar).
    if "fatura_nao_recebida" in tipos and received_notes is not None:
        alerts.extend(fatura_esperada.alertas(
            locais, launched, received_notes, today, mesma_empresa,
            lambda local: local_label(local.get("tipo", ""), str(local["id"])), ultima_leitura,
        ))

    # A mesma cobrança não aparece duas vezes: se a nota (com saldo) já gerou alerta de vencimento, o alerta do
    # provedor do local para a mesma empresa e o mesmo vencimento é omitido.
    por_nota = [a for a in alerts if a["tipo"] == "vencimento" and a["origem"] == "nota"]
    alerts = [
        a for a in alerts
        if not (a["tipo"] == "vencimento" and a["origem"] == "provedor" and any(
            n["entidadeId"] == a["entidadeId"] and n["vencimento"] == a["vencimento"]
            and mesma_empresa(n.get("provedor"), a.get("provedor"))
            for n in por_nota
        ))
    ]
    order = {"alta": 0, "media": 1, "baixa": 2, "info": 3}
    alerts.sort(key=lambda item: (order.get(item["severidade"], 4), item.get("dias", 0), item.get("local", "")))
    return alerts
