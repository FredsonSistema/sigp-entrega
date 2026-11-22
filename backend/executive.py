from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable

from backend.dashboard import _amount, _month_keys, _parse_date, latest_reconciliations

TIPOS_LOCAL = {"agencia": "Agência", "rodoviaria": "Rodoviária", "garagem": "Garagem"}


def validacao_por_nota(analises_sig: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Situação atual da validação do gerente por nota (referência), pela análise SIG mais recente que conta.

    Uma nova análise do mesmo ciclo (ex.: um documento mudou) volta a ficar PENDENTE e o ciclo deixa de
    estar validado até o gerente decidir de novo.
    """
    situacao: Dict[str, tuple[str, str]] = {}
    for analise in analises_sig:
        status = str(analise.get("status_validacao") or "")
        referencia = str(analise.get("referencia") or "")
        if not referencia or status not in {"PENDENTE", "VALIDADA", "CORRIGIDA", "DEVOLVIDA"}:
            continue
        criada = str(analise.get("created_at") or "")
        if referencia not in situacao or criada > situacao[referencia][0]:
            situacao[referencia] = (criada, status)
    return {referencia: status for referencia, (_criada, status) in situacao.items()}


def build_sie_summary(
    launched_notes: Iterable[Dict[str, Any]],
    reconciliations: Iterable[Dict[str, Any]],
    start_date: str,
    end_date: str,
    validacoes: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Visão executiva: só entram ciclos fechados (lançada + paga + fatura com MATCH) VALIDADOS pelo gerente.

    ``validacoes`` = ``validacao_por_nota(...)``. Ciclos fechados ainda sem decisão aparecem à parte
    ("aguardando o gerente"); devolvidos não entram.
    """
    validacoes = validacoes or {}
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    latest = latest_reconciliations(reconciliations)
    in_period = [
        note for note in launched_notes
        if (issued := _parse_date(note.get("data_emissao"))) and start <= issued <= end
    ]
    def is_closed(note: Dict[str, Any]) -> bool:
        row = latest.get(str(note.get("id"))) or {}
        # Conciliações anteriores à regra de 3 vias (fatura_match nulo) não contam como ciclo fechado.
        return str(row.get("status") or "").upper() == "MATCH" and row.get("fatura_match") in (1, True)

    fechados_pela_regra = [note for note in in_period if is_closed(note)]
    situacao = lambda note: validacoes.get(str(note.get("id")), "")  # noqa: E731
    closed = [note for note in fechados_pela_regra if situacao(note) in {"VALIDADA", "CORRIGIDA"}]
    aguardando = [note for note in fechados_pela_regra if situacao(note) not in {"VALIDADA", "CORRIGIDA", "DEVOLVIDA"}]
    devolvidos = [note for note in fechados_pela_regra if situacao(note) == "DEVOLVIDA"]
    open_divergences = [
        note for note in in_period
        if str((latest.get(str(note.get("id"))) or {}).get("status") or "").upper() == "DIVERGENCIA"
    ]

    monthly = {month: 0.0 for month in _month_keys(start, end)}
    by_local: dict[str, float] = {}
    by_provider: dict[str, float] = {}
    for note in closed:
        amount = _amount(note.get("valor_total"))
        month = str(note.get("data_emissao") or "")[:7]
        if month in monthly:
            monthly[month] += amount
        local = f"{TIPOS_LOCAL.get(str(note.get('entidade_tipo') or ''), 'Local')} {note.get('local_nome') or note.get('entidade_id') or ''}".strip()
        by_local[local] = by_local.get(local, 0.0) + amount
        provider = str(note.get("provedor_nome") or "Sem provedor").strip()
        by_provider[provider] = by_provider.get(provider, 0.0) + amount

    closed_total = sum(_amount(note.get("valor_total")) for note in closed)
    months = list(monthly.items())
    filled = [(month, value) for month, value in months if value > 0]
    variation = None
    if len(filled) >= 2 and filled[-2][1] > 0:
        variation = {
            "mesAtual": filled[-1][0], "mesAnterior": filled[-2][0],
            "percentual": round((filled[-1][1] - filled[-2][1]) / filled[-2][1] * 100, 1),
        }
    return {
        "periodo": {"inicio": start.isoformat(), "fim": end.isoformat()},
        "indicadores": {
            "ciclosFechados": len(closed),
            "valorFechado": round(closed_total, 2),
            "custoMedioPorCiclo": round(closed_total / len(closed), 2) if closed else 0.0,
            "notasNoPeriodo": len(in_period),
            "taxaFechamento": round(len(closed) / len(in_period) * 100, 1) if in_period else 0.0,
            "divergenciasAbertas": len(open_divergences),
            "valorEmDivergencia": round(sum(_amount(n.get("valor_total")) for n in open_divergences), 2),
            "locaisAtendidos": len(by_local),
            "aguardandoGerente": len(aguardando),
            "valorAguardandoGerente": round(sum(_amount(n.get("valor_total")) for n in aguardando), 2),
            "devolvidosPeloGerente": len(devolvidos),
        },
        "variacaoMensal": variation,
        "mensal": [{"mes": month, "valor": round(value, 2)} for month, value in months],
        "porLocal": [{"nome": k, "valor": round(v, 2)} for k, v in sorted(by_local.items(), key=lambda i: i[1], reverse=True)[:10]],
        "porProvedor": [{"nome": k, "valor": round(v, 2)} for k, v in sorted(by_provider.items(), key=lambda i: i[1], reverse=True)[:10]],
    }
