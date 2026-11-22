"""Situação 2 — a fatura do mês não chegou.

Para cada provedor de cada local que já teve fatura (nota lançada ou data de vencimento conhecida):
- o próximo vencimento é o último + a periodicidade do provedor (mensal por padrão; "sem_fatura" desliga);
- a chegada esperada é o vencimento menos a antecedência com que esse provedor costuma mandar a fatura
  (mediana do histórico: vencimento - data de recebimento do e-mail; sem histórico, 5 dias);
- a partir do dia seguinte à chegada esperada, sem fatura: FATURA_NAO_RECEBIDA (média; alta no vencimento);
- se uma fatura do provedor está na caixa sem associar: FATURA_NA_CAIXA (chegou, falta associar);
- já paga (pagoAte cobre o vencimento): sem alerta.
Se o SIGp não recebe nenhum documento do Gmail há mais de 3 dias, a falta pode ser da leitura e não do provedor:
um alerta LEITURA_GMAIL_PARADA e os de fatura não recebida baixam para severidade baixa.

Exemplo do usuário: fatura chegou em 17/11 com vencimento 20/11 (antecedência 3 dias). Próximo vencimento 20/12,
chegada esperada 17/12; em 18/12 sem e-mail: alerta médio; em 20/12: alto.
"""
from __future__ import annotations

import calendar
import statistics
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional

PERIODOS = {"mensal": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12}
ANTECEDENCIA_PADRAO = 5
DIAS_LEITURA_PARADA = 3
PENDENTES = ("AGUARDANDO_ASSOCIACAO", "REVISAO", "EM_ANALISE")
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _data(valor: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        return None


def _somar_meses(base: date, meses: int, dia: int) -> date:
    indice = base.year * 12 + base.month - 1 + meses
    ano, mes = indice // 12, indice % 12 + 1
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def _antecedencia(recebidas: List[Dict[str, Any]]) -> Optional[int]:
    dias = []
    for r in recebidas:
        venc = _data((r.get("dados") or {}).get("dataVencimento"))
        chegada = _data(r.get("recebida_em") or r.get("created_at"))
        if venc and chegada and 0 <= (venc - chegada).days <= 40:
            dias.append((venc - chegada).days)
    return round(statistics.median(dias)) if dias else None


def alertas(
    locais: Iterable[Dict[str, Any]],
    lancadas: Iterable[Dict[str, Any]],
    recebidas: Iterable[Dict[str, Any]],
    hoje: date,
    mesma_empresa: Callable[[Any, Any], bool],
    rotulo_local: Callable[[Dict[str, Any]], str],
    ultima_leitura: Optional[str] = None,
) -> List[Dict[str, Any]]:
    lancadas, recebidas = list(lancadas), list(recebidas)
    saida: List[Dict[str, Any]] = []
    leitura = _data(ultima_leitura)
    parada = bool(leitura and (hoje - leitura).days > DIAS_LEITURA_PARADA)
    if parada:
        saida.append({
            "tipo": "fatura_nao_recebida", "origem": "gmail", "status": "LEITURA_GMAIL_PARADA", "severidade": "alta",
            "vencimento": "", "dias": (leitura - hoje).days, "entidadeTipo": "", "entidadeId": "", "local": "", "provedor": "",
            "valor": 0.0,
            "mensagem": f"Nenhum documento novo do Gmail desde {leitura.strftime('%d/%m/%Y')}: confira o WF-08 antes de cobrar os provedores.",
        })
    associadas = [r for r in recebidas if r.get("status") == "ASSOCIADA"]
    pendentes = [r for r in recebidas if r.get("status") in PENDENTES]
    for local in locais:
        if local.get("ativo") is False:
            continue
        for prov in local.get("provedores") or []:
            if not isinstance(prov, dict) or not str(prov.get("nome") or "").strip():
                continue
            periodo = str(prov.get("periodicidade") or "mensal").strip().lower()
            if periodo in ("sem_fatura", "nenhuma", "nao"):
                continue
            passo = PERIODOS.get(periodo, 1)
            nome = str(prov["nome"])
            do_local = [n for n in lancadas if str(n.get("entidade_id") or "") == str(local["id"])
                        and mesma_empresa(n.get("provedor_nome"), nome)]
            vencs = [d for d in (_data(n.get("data_vencimento")) for n in do_local) if d]
            if _data(prov.get("dataVencimento")):
                vencs.append(_data(prov.get("dataVencimento")))
            if not vencs:
                continue  # sem histórico ainda: começa a acompanhar depois da primeira fatura
            ultimo = max(vencs)
            try:
                dia = int(prov.get("diaVencimento") or ultimo.day)
            except (TypeError, ValueError):
                dia = ultimo.day
            hist_local = [r for r in associadas if str(r.get("entidade_id") or "") == str(local["id"])
                          and mesma_empresa((r.get("dados") or {}).get("emissorNome"), nome)]
            hist_prov = [r for r in associadas if mesma_empresa((r.get("dados") or {}).get("emissorNome"), nome)]
            antecedencia = _antecedencia(hist_local) or _antecedencia(hist_prov) or ANTECEDENCIA_PADRAO
            proximo = _somar_meses(ultimo, passo, dia)
            esperado = proximo - timedelta(days=antecedencia)
            if hoje <= esperado:
                continue
            pago_ate = _data(prov.get("pagoAte"))
            if pago_ate and pago_ate >= proximo:
                continue
            ciclos = 1
            while ciclos < 6 and hoje > _somar_meses(ultimo, passo * (ciclos + 1), dia) - timedelta(days=antecedencia):
                ciclos += 1
            mes = f"{MESES[proximo.month - 1]}/{proximo.year}"
            rotulo = rotulo_local(local)
            base = {
                "tipo": "fatura_nao_recebida", "origem": "provedor", "vencimento": proximo.isoformat(),
                "esperadaEm": esperado.isoformat(), "dias": (proximo - hoje).days, "antecedenciaDias": antecedencia,
                "ciclosSemFatura": ciclos, "entidadeTipo": local.get("tipo"), "entidadeId": local["id"], "local": rotulo,
                "provedor": nome, "valor": float(str(prov.get("valor") or 0).replace(",", ".") or 0),
            }
            na_caixa = next((r for r in pendentes if mesma_empresa((r.get("dados") or {}).get("emissorNome"), nome) and (
                (_data((r.get("dados") or {}).get("dataVencimento")) and abs((_data(r["dados"]["dataVencimento"]) - proximo).days) <= 12)
                or (not (r.get("dados") or {}).get("dataVencimento") and (_data(r.get("recebida_em")) or date.min) >= esperado - timedelta(days=10))
            )), None)
            if na_caixa:
                chegou = _data(na_caixa.get("recebida_em") or na_caixa.get("created_at"))
                quando = f" em {chegou.strftime('%d/%m')}" if chegou else ""
                saida.append({**base, "status": "FATURA_NA_CAIXA", "severidade": "media", "notaRecebidaId": na_caixa.get("id"),
                              "mensagem": f"{rotulo} · {nome}: a fatura de {mes} chegou{quando} e está em Notas recebidas sem associar."})
                continue
            severidade = "alta" if hoje >= proximo else "media"
            mensagem = (f"{rotulo} · {nome}: a fatura de {mes} não chegou (esperada até {esperado.strftime('%d/%m')}, "
                        f"vence {proximo.strftime('%d/%m')})" + (f"; {ciclos} meses sem fatura" if ciclos > 1 else "") + ".")
            if parada:
                severidade = "baixa"
                mensagem += " A leitura do Gmail está parada: confira antes de cobrar o provedor."
            saida.append({**base, "status": "FATURA_NAO_RECEBIDA", "severidade": severidade, "mensagem": mensagem})
    return saida


def ultima_leitura_gmail(recebidas: Iterable[Dict[str, Any]]) -> Optional[str]:
    datas = [str(r.get("created_at") or "") for r in recebidas if str(r.get("gmail_message_id") or "")]
    return max(datas) if datas else None


def agora() -> datetime:
    return datetime.now()
