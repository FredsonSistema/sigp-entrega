from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict


def safe_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace("R$", "").replace(" ", "").strip()
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        return float(cleaned)
    except Exception:
        return 0.0


def normalize_json_payload(payload: Any) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else json.loads(str(payload))
    doc = data.get("documento") if isinstance(data, dict) and isinstance(data.get("documento"), dict) else data
    return {
        "id": str(doc.get("id") or doc.get("chave") or "manual-import"),
        "chave": str(doc.get("chave") or "").strip(),
        "numero": str(doc.get("numero") or "").strip(),
        "serie": str(doc.get("serie") or "").strip(),
        "provedorNome": str(doc.get("provedorNome") or doc.get("provedor") or "").strip(),
        "localNome": str(doc.get("localNome") or doc.get("local_nome") or "").strip(),
        "localCidade": str(doc.get("localCidade") or doc.get("local_cidade") or "").strip(),
        "municipioCodigo": str(doc.get("municipioCodigo") or doc.get("municipio_codigo") or "").strip(),
        "valor": safe_float(doc.get("valorTotal") or doc.get("valor") or 0),
        "dataEmissao": str(doc.get("dataEmissao") or doc.get("data_emissao") or "").strip(),
        "dataVencimento": str(doc.get("dataVencimento") or doc.get("data_vencimento") or "").strip(),
        "status": str(doc.get("status") or "PENDENTE").upper(),
        "observacao": str(doc.get("observacao") or "").strip(),
        "origem": str(doc.get("origem") or "json").strip(),
        "servicos": normalize_service_items(doc.get("servicos") or doc.get("serviceItems") or []),
    }


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def xml_find(parent: ET.Element, *names: str) -> ET.Element | None:
    wanted = {name.casefold() for name in names}
    return next((node for node in parent.iter() if xml_local_name(node.tag).casefold() in wanted), None)


def xml_get_text(parent: ET.Element, *names: str) -> str:
    wanted = {name.casefold(): name.casefold() for name in names}
    matches = {
        xml_local_name(node.tag).casefold(): node
        for node in parent.iter()
        if xml_local_name(node.tag).casefold() in wanted
    }
    for name in names:
        node = matches.get(name.casefold())
        if node is not None:
            return (node.text or "").strip()
    return ""


def normalize_service_items(items: Any) -> list[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = str(item.get("descricao") or item.get("description") or "").strip()
        if not description:
            continue
        normalized.append({
            "id": str(item.get("id") or ""),
            "codigo": str(item.get("codigo") or item.get("codigoServico") or "").strip(),
            "descricao": description,
            "quantidade": safe_float(item.get("quantidade") or 0),
            "valorUnitario": safe_float(item.get("valorUnitario") or 0),
            "valorTotal": safe_float(item.get("valorTotal") or item.get("valor") or 0),
            "classificacao": str(item.get("classificacao") or "PENDENTE").upper(),
        })
    return normalized


def extract_due_date_xinfcomp(text: str) -> str:
    match = re.search(
        r"\bvencimento\b\s*(?:da\s+nota\s*)?[:\-]?\s*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})",
        text or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    value = match.group(1)
    if re.match(r"^\d{4}-", value):
        return value
    day, month, year = value.split("/")
    return f"{year}-{month}-{day}"


def normalize_xml_payload(xml_text: str) -> Dict[str, Any]:
    text = str(xml_text or "").strip()
    if not text:
        raise ValueError("XML vazio")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("XML inválido") from exc

    inf_nfse = xml_find(root, "InfNfse")
    if inf_nfse is None:
        inf_nfse = root
    prestador = xml_find(inf_nfse, "PrestadorServico")
    if prestador is None:
        prestador = inf_nfse
    tomador = xml_find(inf_nfse, "TomadorServico")
    if tomador is None:
        tomador = inf_nfse
    tomador_endereco = xml_find(tomador, "Endereco")
    if tomador_endereco is None:
        tomador_endereco = tomador
    declaracao = xml_find(inf_nfse, "InfDeclaracaoPrestacaoServico")
    if declaracao is None:
        declaracao = inf_nfse
    servico = xml_find(declaracao, "Servico")
    if servico is None:
        servico = declaracao
    chave = xml_get_text(inf_nfse, "CodigoVerificacao", "chNFe", "chave", "cNFe")
    if not chave and inf_nfse is not root:
        chave = str(inf_nfse.get("Id") or "").removeprefix("NFS")
    numero = xml_get_text(inf_nfse, "Numero", "nNF", "nDoc")
    serie = xml_get_text(declaracao, "Serie")
    provedor = xml_get_text(prestador, "NomeFantasia", "RazaoSocial", "xNome")
    local_nome = xml_get_text(tomador, "RazaoSocial", "xNome") or ", ".join(
        value for value in (xml_get_text(tomador_endereco, "Endereco"), xml_get_text(tomador_endereco, "Numero")) if value
    )
    local_cidade = (
        xml_get_text(inf_nfse, "xLocalidadeInc")
        or xml_get_text(tomador_endereco, "xMun", "Municipio", "Cidade")
        or xml_get_text(tomador_endereco, "CodigoMunicipio")
    )
    municipio_codigo = xml_get_text(tomador_endereco, "CodigoMunicipio")
    valor_total = safe_float(xml_get_text(inf_nfse, "ValorLiquidoNfse", "ValorServicos", "vNF", "vTotNF"))
    data_emissao = xml_get_text(inf_nfse, "DataEmissao", "dEmi", "dhEmi")
    data_vencimento = xml_get_text(inf_nfse, "DataVencimento", "dVen") or extract_due_date_xinfcomp(
        xml_get_text(inf_nfse, "xInfComp")
    )
    codigo_servico = xml_get_text(servico, "ItemListaServico", "CodigoTributacaoMunicipio")

    servicos = []
    for node in servico.iter():
        if xml_local_name(node.tag).casefold() != "itensservico":
            continue
        descricao = xml_get_text(node, "Discriminacao", "Descricao", "Description")
        if not descricao:
            continue
        servicos.append({
            "codigo": codigo_servico,
            "descricao": descricao,
            "quantidade": safe_float(xml_get_text(node, "Quantidade", "qCom")),
            "valorUnitario": safe_float(xml_get_text(node, "ValorUnitario", "vUnCom")),
            "valorTotal": safe_float(xml_get_text(node, "ValorTotal", "vProd")),
            "classificacao": "PENDENTE",
        })

    if not servicos:
        descricao = xml_get_text(servico, "Discriminacao")
        if descricao:
            servicos.append({
                "codigo": codigo_servico,
                "descricao": descricao,
                "quantidade": 1,
                "valorUnitario": valor_total,
                "valorTotal": valor_total,
                "classificacao": "PENDENTE",
            })

    return {
        "id": chave or numero or "manual-import",
        "chave": chave,
        "numero": numero,
        "serie": serie,
        "provedorNome": provedor,
        "localNome": local_nome,
        "localCidade": local_cidade,
        "municipioCodigo": municipio_codigo,
        "valor": valor_total,
        "dataEmissao": data_emissao,
        "dataVencimento": data_vencimento,
        "status": "PENDENTE",
        "observacao": "Importado via XML",
        "origem": "xml",
        "servicos": servicos,
    }


def normalize_nota(raw_payload: Any, source: str = "json") -> Dict[str, Any]:
    if source.lower() == "xml":
        return normalize_xml_payload(str(raw_payload))
    if isinstance(raw_payload, str):
        try:
            return normalize_json_payload(json.loads(raw_payload))
        except Exception:
            return normalize_json_payload({"chave": raw_payload})
    if isinstance(raw_payload, dict):
        return normalize_json_payload(raw_payload)
    raise ValueError("Formato de payload inválido")
