"""Regra única: aplicar uma fatura associada ao provedor de internet do local.

Usada na associação das Notas recebidas (Gmail). É a mesma regra que o modal da fatura do provedor
aplica no navegador (``updateProviderInvoice`` em agencias.html): nome, valor, data e dia de vencimento
e a fatura atual. Esses são os campos que os alertas de vencimento leem (``backend/alerts.py``).

Regras:
- O provedor é encontrado pelo nome normalizado (exato; senão, um nome contém o outro, se for único).
- Sem correspondência: cria o provedor no local.
- Mais de uma correspondência parcial: não altera nada e devolve aviso (evita atualizar o provedor errado).
- Fatura mais antiga que a atual do provedor: fica só no histórico; não volta o vencimento para trás.
"""
from __future__ import annotations

import re
from functools import lru_cache
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

_SUFIXOS = re.compile(r"\b(ltda|ltd|s\s*/?\s*a|sa|me|epp|eireli|mei|cia|companhia)\b")


def normalizar_nome_provedor(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "").casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = _SUFIXOS.sub(" ", re.sub(r"[^a-z0-9/ ]", " ", texto))
    return re.sub(r"[^a-z0-9]", "", texto)


def encontrar_provedor(provedores: List[Dict[str, Any]], nome: str) -> Tuple[Optional[int], str]:
    """Devolve (índice, motivo). Índice None com motivo 'ambiguo' ou 'nao_encontrado'."""
    alvo = normalizar_nome_provedor(nome)
    if not alvo:
        return None, "nao_encontrado"
    nomes = [normalizar_nome_provedor(p.get("nome") if isinstance(p, dict) else p) for p in provedores]
    exatos = [i for i, n in enumerate(nomes) if n and n == alvo]
    if exatos:
        return exatos[0], "exato"
    parciais = [i for i, n in enumerate(nomes) if len(n) >= 3 and (n in alvo or alvo in n)]
    if len(parciais) == 1:
        return parciais[0], "parcial"
    if parciais:
        return None, "ambiguo"
    # Mesma empresa com razão social diferente (ex.: "OPIX INTERNET" x "OPIX SERVICOS DE TECNOLOGIA"):
    # primeira palavra significativa igual, se só um provedor do local tiver essa palavra.
    marca = marca_provedor(nome)
    if marca:
        por_marca = [i for i, p in enumerate(provedores) if marca_provedor(p.get("nome") if isinstance(p, dict) else p) == marca]
        if len(por_marca) == 1:
            return por_marca[0], "marca"
        if por_marca:
            return None, "ambiguo"
    return None, "nao_encontrado"


def mesma_empresa(nome_a: Any, nome_b: Any) -> bool:
    """Mesma regra de correspondência do provedor: nome igual, um contém o outro ou mesma marca."""
    if not str(nome_a or "").strip() or not str(nome_b or "").strip():
        return False
    return _mesma_empresa(str(nome_a), str(nome_b))


@lru_cache(maxsize=20000)
def _mesma_empresa(nome_a: str, nome_b: str) -> bool:
    # Função pura dos dois nomes: guardada em cache (a lista de notas recebidas compara milhares de pares).
    return encontrar_provedor([{"nome": nome_b}], nome_a)[0] is not None


def competencia(data_vencimento: Any) -> str:
    """Mês da cobrança (AAAA-MM) a partir do vencimento. Notas recorrentes: uma por mês, por provedor e local."""
    texto = str(data_vencimento or "").strip()
    return texto[:7] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto[:10]) else ""


_GENERICAS = {
    "internet", "telecom", "telecomunicacoes", "telecomunicacao", "comunicacao", "comunicacoes", "servicos",
    "servico", "provedor", "fibra", "net", "rede", "redes", "tecnologia", "solucoes", "informatica", "digital",
    "conectividade", "conexao", "banda", "larga", "link", "dados", "grupo", "empresa", "comercio", "assessoria",
    "brasil", "nordeste", "bahia", "de", "da", "do", "das", "dos", "e",
}


def marca_provedor(valor: Any) -> str:
    """Primeira palavra significativa do nome (>= 3 letras, não genérica). Ex.: "OPIX SERVICOS..." -> "opix"."""
    texto = unicodedata.normalize("NFKD", str(valor or "").casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = _SUFIXOS.sub(" ", re.sub(r"[^a-z0-9/ ]", " ", texto))
    for palavra in re.findall(r"[a-z0-9]+", texto):
        if len(palavra) >= 3 and palavra not in _GENERICAS and not palavra.isdigit():
            return palavra
    return ""


def aplicar_fatura_no_provedor(
    provedores: List[Any], *, nome: str, valor: float, data_vencimento: str, fatura_id: str = "",
    provedor_id: str = "",
) -> Dict[str, Any]:
    """Aplica a fatura/nota à lista (não altera a lista recebida). Devolve o resultado com a lista nova.

    ``provedor_id`` (quando a tela informa a linha do provedor) tem prioridade sobre o nome.
    Sem ``fatura_id`` (nota lançada sem PDF), a fatura atual do provedor é mantida.
    """
    lista = [dict(p) if isinstance(p, dict) else {"nome": str(p)} for p in (provedores or [])]
    por_id = next((i for i, p in enumerate(lista) if provedor_id and str(p.get("id") or "") == provedor_id), None)
    indice, motivo = (por_id, "id") if por_id is not None else encontrar_provedor(lista, nome)
    if motivo == "ambiguo":
        return {"provedores": lista, "provedor": None, "acao": "ambiguo",
                "aviso": f"Mais de um provedor do local parece com “{nome}”; nenhum foi alterado."}
    if indice is None:
        lista.append({"id": f"prov-{uuid4().hex[:12]}", "nome": nome.strip()[:300]})
        indice, acao = len(lista) - 1, "criado"
    else:
        acao = "atualizado"
    provedor = lista[indice]
    atual = str(provedor.get("dataVencimento") or "")
    if atual and data_vencimento and data_vencimento < atual:
        # Só ocorre com provedor existente (um criado agora não tem vencimento): a lista fica como estava.
        return {"provedores": lista, "provedor": provedor, "acao": "historico",
                "aviso": f"A fatura vence antes da fatura atual do provedor ({atual}); ficou só no histórico."}
    if not str(provedor.get("nome") or "").strip():
        provedor["nome"] = nome.strip()[:300]
    provedor["valor"] = f"{float(valor):.2f}"
    provedor["dataVencimento"] = data_vencimento
    if data_vencimento:
        provedor["diaVencimento"] = str(int(data_vencimento[-2:]))
    if fatura_id:
        provedor["faturaAtualId"] = fatura_id
    provedor.setdefault("id", f"prov-{uuid4().hex[:12]}")
    return {"provedores": lista, "provedor": provedor, "acao": acao, "aviso": ""}
