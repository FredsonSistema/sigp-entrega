"""Base fictícia do pacote da entrega: locais, provedores e algumas faturas recebidas, todos inventados.

Roda dentro do container da API (a chave SIGP_API_KEY já está no ambiente dele) e grava pela própria API, como a tela
e o n8n fazem:
    docker exec sigp_api python /app/entrega/base_ficticia.py
Recusa rodar se o banco já tiver locais: dado fictício nunca se mistura com dado real (use --forcar só num banco de teste).
Nada aqui é de uma empresa real: nomes, CNPJs, e-mails e valores são inventados.
"""
from __future__ import annotations

import io
import json
import os
import sys
import uuid
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = os.environ.get("SIGP_API_INTERNA", "http://127.0.0.1:5001")
CHAVE = os.environ.get("SIGP_API_KEY", "")

PROVEDORES = {
    "netfibra": {"nome": "NETFIBRA TELECOM FICTICIA LTDA", "email": "netfibra-ficticia.com.br", "contato": "(73) 3000-0001"},
    "conecta": {"nome": "CONECTA ALFA FICTICIA LTDA", "email": "conecta-alfa-ficticia.com.br", "contato": "(73) 3000-0002"},
    "veloz": {"nome": "VELOZNET FICTICIA EIRELI", "email": "veloznet-ficticia.com.br", "contato": "(73) 3000-0003"},
}
LOCAIS = {
    "agencia": [
        ("demo-ag-01", "Agência Centro Fictícia", "Itabuna", "Av. Exemplo, 100", [("netfibra", 10, 189.90)]),
        ("demo-ag-02", "Agência Praia Fictícia", "Ilhéus", "Rua Exemplo, 200", [("conecta", 15, 450.00)]),
        ("demo-ag-03", "Agência Serra Fictícia", "Jequié", "Praça Exemplo, 300", [("veloz", 22, 89.90), ("netfibra", 10, 129.90)]),
    ],
    "rodoviaria": [
        ("demo-rv-01", "Rodoviária Norte Fictícia", "Itabuna", "Terminal Exemplo, s/n", [("conecta", 15, 450.00)]),
        ("demo-rv-02", "Rodoviária Litoral Fictícia", "Ilhéus", "Terminal Exemplo, 2", [("veloz", 22, 99.90)]),
    ],
    "garagem": [
        ("demo-gr-01", "Garagem Sul Fictícia", "Itabuna", "Rodovia Exemplo, km 1", [("veloz", 22, 89.90)]),
    ],
}


def chamar(metodo: str, caminho: str, corpo: bytes | None = None, tipo: str = "application/json") -> dict:
    pedido = Request(f"{API}{caminho}", data=corpo, method=metodo, headers={"X-API-Key": CHAVE, **({"Content-Type": tipo} if corpo else {})})
    try:
        with urlopen(pedido, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        raise SystemExit(f"{metodo} {caminho}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}") from e


def local(lid: str, nome: str, cidade: str, endereco: str, provs: list) -> dict:
    return {
        "id": lid, "nome": nome, "cidade": cidade, "endereco": endereco, "numero": "", "cep": "", "obs": "Dado fictício (base de demonstração).",
        "ativo": True, "vencimentoFatura": "", "marcadores": [], "redes": [], "historicoVisitas": [],
        "responsaveis": [{"nome": "Responsável Fictício", "email": "responsavel@exemplo.com.br", "telefone": "(73) 99999-0000"}],
        "provedores": [{"id": f"{lid}-{chave}", "nome": PROVEDORES[chave]["nome"], "email": PROVEDORES[chave]["email"],
                        "contato": PROVEDORES[chave]["contato"], "diaVencimento": dia, "valor": valor} for chave, dia, valor in provs],
    }


def pdf(linhas: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for l in linhas:
        c.drawString(50, y, l)
        y -= 18
    c.save()
    return buf.getvalue()


def multipart(campos: dict, nome_arquivo: str, conteudo: bytes) -> tuple[bytes, str]:
    limite = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
    partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; filename=\"{nome_arquivo}\"\r\n"
                  "Content-Type: application/pdf\r\n\r\n".encode("utf-8") + conteudo + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def main() -> None:
    if not CHAVE:
        raise SystemExit("SIGP_API_KEY não está no ambiente do container.")
    existentes = chamar("GET", "/api/locais").get("items", [])
    reais = [i for i in existentes if not str(i.get("id", "")).startswith("demo-")]
    if reais and "--forcar" not in sys.argv:
        raise SystemExit(f"O banco já tem {len(reais)} local(is) que não são da base fictícia: nada foi gravado. "
                         "A base fictícia só entra num banco vazio.")
    for tipo, itens in LOCAIS.items():
        chamar("PUT", f"/api/locais/{tipo}", json.dumps({"items": [local(*i) for i in itens]}).encode("utf-8"))
    hoje = date.today()
    faturas = [
        ("demo-msg-01", "faturamento@netfibra-ficticia.com.br", "Sua fatura de internet chegou", "netfibra", 189.90, 10,
         "Link dedicado 200 Mbps - Agência Centro Fictícia"),
        ("demo-msg-02", "cobranca@conecta-alfa-ficticia.com.br", "Fatura e NFCom do mês", "conecta", 450.00, 15,
         "Link principal fibra 300 Mbps - Rodoviária Norte Fictícia"),
        ("demo-msg-03", "faturas@veloznet-ficticia.com.br", "Boleto disponível", "veloz", 104.90, 22,
         "Internet fibra 50 Mb + IP adicional - Garagem Sul Fictícia (valor acima do contratado)"),
    ]
    for mid, remetente, assunto, prov, valor, dias, servico in faturas:
        venc = (hoje + timedelta(days=dias)).isoformat()
        p = PROVEDORES[prov]
        conteudo = pdf([p["nome"], "CNPJ 00.000.000/0001-00 (fictício)", "FATURA DE SERVIÇOS DE INTERNET",
                        "Cliente: EMPRESA EXEMPLO TRANSPORTES LTDA (fictícia)", f"Serviço: {servico}",
                        f"Vencimento: {date.fromisoformat(venc).strftime('%d/%m/%Y')}",
                        f"Total a pagar: R$ {valor:.2f}".replace(".", ","), "Documento fictício para demonstração do SIGp."])
        corpo, tipo = multipart({"gmailMessageId": mid, "gmailAttachmentId": "default", "assunto": assunto, "remetente": remetente,
                                 "recebidaEm": hoje.isoformat(), "corpo": "Documento fictício.",
                                 "dadosExtracao": json.dumps({"emissorNome": p["nome"], "valorTotal": valor, "dataVencimento": venc})},
                                f"fatura-{mid}.pdf", conteudo)
        chamar("POST", "/api/notas-recebidas", corpo, tipo)
    total = sum(len(v) for v in LOCAIS.values())
    print(f"Base fictícia gravada: {total} locais, {len(PROVEDORES)} provedores e {len(faturas)} faturas em Notas recebidas.")


if __name__ == "__main__":
    main()
