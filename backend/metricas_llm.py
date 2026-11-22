"""Métricas da LLM (etapa 5): acerto da triagem, dos campos lidos e do local sugerido, por mês.

A "verdade" é a decisão do operador:
- cobrança: nota ASSOCIADA ou resgatada da fila de ignorados;
- não é cobrança: descartada por uma pessoa com o motivo "não é cobrança" (descarte automático não conta).
Notas ainda sem decisão, ou descartadas por outro motivo (duplicada, ilegível...), ficam fora da acurácia.
"""
from __future__ import annotations

import json
import statistics
import urllib.request
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

TIPOS_COBRANCA = {"boleto_fatura", "fatura_e_nota", "nota_fiscal", "lembrete"}
OPERADOR_AUTOMATICO = "sigp-ia"
CAMPOS = ("emissorNome", "numero", "chave", "valorTotal", "dataVencimento")
PADRAO = "999999999"


def _mes(valor: Any) -> str:
    texto = str(valor or "")
    return texto[:7] if len(texto) >= 7 and texto[4] == "-" else ""


def _verdade(status: str, dados: Dict[str, Any]) -> Optional[bool]:
    if status == "ASSOCIADA":
        return True
    triagem = dados.get("triagem") or {}
    if triagem.get("resgatadoEm") and status != "DESCARTADA":
        return True
    descarte = dados.get("descarte") or {}
    if status == "DESCARTADA" and descarte.get("motivo") == "nao_cobranca" and descarte.get("operador") != OPERADOR_AUTOMATICO:
        return False
    return None


def _campo_igual(campo: str, lido: Any, final: Any) -> bool:
    if campo == "valorTotal":
        try:
            return abs(float(lido) - float(final)) <= 0.01
        except (TypeError, ValueError):
            return False
    if campo == "dataVencimento":
        return str(lido or "")[:10] == str(final or "")[:10] and bool(final)
    a = " ".join(str(lido or "").upper().split())
    b = " ".join(str(final or "").upper().split())
    if campo in ("numero", "chave") and b == PADRAO and a in ("", PADRAO):
        return True  # nada para ler: o padrão vale como acerto
    return a == b


def _pct(acertos: int, total: int) -> Optional[float]:
    return round(acertos / total, 3) if total else None


def _novo_mes() -> Dict[str, Any]:
    return {
        "documentos": 0, "niveis": {"alta": 0, "inconclusivo": 0, "baixa": 0, "sem_nivel": 0},
        "decididos": 0, "acertos": 0, "falsoPositivo": 0, "falsoNegativo": 0,
        "comExemplos": {"decididos": 0, "acertos": 0}, "semExemplos": {"decididos": 0, "acertos": 0},
        "descartesAutomaticos": 0, "iaErros": 0, "_duracoes": [], "_confiancas": [],
        "campos": {"total": 0, "corretos": 0, "porCampo": {c: {"total": 0, "corretos": 0} for c in CAMPOS}},
        "local": {"total": 0, "acertos": 0},
    }


def calcular(notas: Iterable[Dict[str, Any]], feedbacks: Iterable[Dict[str, Any]], meses: int = 6,
             hoje: Optional[date] = None) -> Dict[str, Any]:
    hoje = hoje or date.today()
    indice = hoje.year * 12 + hoje.month - 1
    janela = [f"{(indice - i) // 12:04d}-{(indice - i) % 12 + 1:02d}" for i in range(meses - 1, -1, -1)]
    por_mes: Dict[str, Dict[str, Any]] = defaultdict(_novo_mes)

    for nota in notas:
        mes = _mes(nota.get("recebida_em")) or _mes(nota.get("created_at"))
        if mes not in janela:
            continue
        dados = nota.get("dados") or {}
        classificacao = dados.get("classificacao") or {}
        ia = classificacao.get("ia") or {}
        triagem = dados.get("triagem") or {}
        m = por_mes[mes]
        m["documentos"] += 1
        nivel = triagem.get("probabilidade")
        m["niveis"][nivel if nivel in ("alta", "inconclusivo", "baixa") else "sem_nivel"] += 1
        if (dados.get("descarte") or {}).get("operador") == OPERADOR_AUTOMATICO:
            m["descartesAutomaticos"] += 1
        if ia.get("erro"):
            m["iaErros"] += 1
        if isinstance(ia.get("duracaoMs"), (int, float)) and ia["duracaoMs"] > 0:
            m["_duracoes"].append(float(ia["duracaoMs"]))
        tipo = str(ia.get("tipoDocumento") or "")
        verdade = _verdade(str(nota.get("status") or ""), dados)
        if verdade is None or not tipo or ia.get("erro"):
            continue
        try:
            m["_confiancas"].append(float(ia.get("confianca") or 0))
        except (TypeError, ValueError):
            pass
        acertou = (tipo in TIPOS_COBRANCA) == verdade
        m["decididos"] += 1
        m["acertos"] += int(acertou)
        if not acertou:
            m["falsoPositivo" if tipo in TIPOS_COBRANCA else "falsoNegativo"] += 1
        grupo = m["comExemplos" if ia.get("exemplosUsados") else "semExemplos"]
        grupo["decididos"] += 1
        grupo["acertos"] += int(acertou)

    for fb in feedbacks:
        if fb.get("tipo") != "associada":
            continue
        mes = _mes(fb.get("created_at"))
        if mes not in janela:
            continue
        m = por_mes[mes]
        lidos, finais = fb.get("extraidos") or {}, fb.get("finais") or {}
        for campo in CAMPOS:
            if campo not in finais:
                continue
            certo = _campo_igual(campo, lidos.get(campo), finais.get(campo))
            m["campos"]["total"] += 1
            m["campos"]["corretos"] += int(certo)
            m["campos"]["porCampo"][campo]["total"] += 1
            m["campos"]["porCampo"][campo]["corretos"] += int(certo)
        sugestao = str(finais.get("sugestaoLocalId") or "")
        if "sugestaoLocalId" in finais:
            m["local"]["total"] += 1
            m["local"]["acertos"] += int(bool(sugestao) and sugestao == str(fb.get("entidade_id") or ""))

    def fechar(m: Dict[str, Any]) -> Dict[str, Any]:
        duracoes, confiancas = m.pop("_duracoes"), m.pop("_confiancas")
        m["acuracia"] = _pct(m["acertos"], m["decididos"])
        for grupo in (m["comExemplos"], m["semExemplos"]):
            grupo["acuracia"] = _pct(grupo["acertos"], grupo["decididos"])
        m["campos"]["acuracia"] = _pct(m["campos"]["corretos"], m["campos"]["total"])
        for valor in m["campos"]["porCampo"].values():
            valor["acuracia"] = _pct(valor["corretos"], valor["total"])
        m["local"]["acuracia"] = _pct(m["local"]["acertos"], m["local"]["total"])
        m["tempoMedianoMs"] = round(statistics.median(duracoes)) if duracoes else None
        m["tempoP95Ms"] = round(sorted(duracoes)[max(0, int(len(duracoes) * 0.95) - 1)]) if duracoes else None
        m["confiancaMedia"] = round(statistics.mean(confiancas), 3) if confiancas else None
        return m

    mensal = []
    total = _novo_mes()
    for mes in janela:
        m = por_mes.get(mes) or _novo_mes()
        for chave in ("documentos", "decididos", "acertos", "falsoPositivo", "falsoNegativo", "descartesAutomaticos", "iaErros"):
            total[chave] += m[chave]
        for nivel, n in m["niveis"].items():
            total["niveis"][nivel] += n
        for g in ("comExemplos", "semExemplos"):
            total[g]["decididos"] += m[g]["decididos"]
            total[g]["acertos"] += m[g]["acertos"]
        total["campos"]["total"] += m["campos"]["total"]
        total["campos"]["corretos"] += m["campos"]["corretos"]
        for c in CAMPOS:
            total["campos"]["porCampo"][c]["total"] += m["campos"]["porCampo"][c]["total"]
            total["campos"]["porCampo"][c]["corretos"] += m["campos"]["porCampo"][c]["corretos"]
        total["local"]["total"] += m["local"]["total"]
        total["local"]["acertos"] += m["local"]["acertos"]
        total["_duracoes"] += m["_duracoes"]
        total["_confiancas"] += m["_confiancas"]
        mensal.append({"mes": mes, **fechar(m)})
    return {"periodo": {"inicio": janela[0], "fim": janela[-1], "meses": meses}, "total": fechar(total), "mensal": mensal}


def estado_modelo(ollama_url: str, modelo: str, timeout: float = 3.0) -> Dict[str, Any]:
    """Modelos carregados na memória e instalados no Ollama local (sem custo por token)."""
    base = ollama_url.rstrip("/")

    def get(caminho: str) -> Dict[str, Any]:
        with urllib.request.urlopen(f"{base}{caminho}", timeout=timeout) as resposta:  # noqa: S310 (URL interna fixa)
            return json.loads(resposta.read().decode("utf-8"))

    try:
        carregados = get("/api/ps").get("models") or []
        instalados = get("/api/tags").get("models") or []
    except (OSError, ValueError) as erro:
        return {"disponivel": False, "modeloConfigurado": modelo, "erro": str(erro)[:200]}
    return {
        "disponivel": True,
        "modeloConfigurado": modelo,
        "carregados": [{"nome": m.get("name"), "memoriaBytes": m.get("size"), "vramBytes": m.get("size_vram"),
                        "expiraEm": m.get("expires_at")} for m in carregados],
        "memoriaEmUsoBytes": sum(int(m.get("size") or 0) for m in carregados),
        "instalados": [{"nome": m.get("name"), "discoBytes": m.get("size")} for m in instalados],
    }


def resumo_textual(metricas: Dict[str, Any]) -> List[str]:
    """Frases curtas para o topo do painel."""
    t = metricas["total"]
    frases = []
    if t["decididos"]:
        frases.append(f"Triagem: {t['acertos']} de {t['decididos']} documentos decididos certos ({round(t['acuracia'] * 100)}%).")
    if t["campos"]["total"]:
        frases.append(f"Campos lidos: {t['campos']['corretos']} de {t['campos']['total']} sem correção ({round(t['campos']['acuracia'] * 100)}%).")
    return frases
