"""Gera n8n_workflow_wf10_entrada_manual.json: o documento enviado pela tela (Notas recebidas > Adicionar documento)
passa pela MESMA leitura, regras e IA de um e-mail.

As etapas OCR local -> regras do SIGp -> exemplos -> extração e pedido à IA -> Qwen -> decisão -> gravar na caixa são
copiadas do WF-08 já gerado (n8n_workflow_wf08_gmail_inbox.json), sem mudar nada: rode antes o build_wf08.ps1.
O que muda é só a entrada (webhook chamado pela API do SIGp, em vez do Gmail) e o fim (não há etiqueta no Gmail).
O nó que monta o documento tem o mesmo nome do WF-08 ("Recuperar itens e etiquetas") porque as etapas copiadas o leem.

Uso, na raiz do projeto:  python n8n/wf10/build_wf10.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WF08 = RAIZ / "n8n_workflow_wf08_gmail_inbox.json"
SAIDA = RAIZ / "n8n_workflow_wf10_entrada_manual.json"
LIB_XML = RAIZ / "n8n" / "lib" / "xml_fiscal.js"
ID = "sigpWF10EntradaMan"
WEBHOOK = "sigp-entrada-manual"
# Etapas do WF-08 usadas como estão (na ordem do fluxo).
COPIADAS = [
    "OCR local", "Classificar com regras do SIGp", "Buscar exemplos no SIGp", "Extrair campos e montar pedido à IA",
    "Classificar com Qwen (Ollama local)", "Consolidar decisão", "Salvar na caixa SIGp",
]
CABECALHO_API = {"parameters": [{"name": "X-API-Key", "value": "={{ $env.SIGP_API_KEY }}"}]}

CODIGO_CONFERIR = r"""// Gerado por n8n/wf10/build_wf10.py.
// Só a API do SIGp chama este webhook: o pedido traz a mesma SIGP_API_KEY que o n8n tem. Sem ela, nada é lido.
const cabecalhos = $json.headers || {};
let esperada = '';
try { esperada = String($env.SIGP_API_KEY || ''); } catch (e) { /* acesso a $env bloqueado */ }
if (!esperada || String(cabecalhos['x-api-key'] || '') !== esperada) {
  throw new Error('Pedido sem a chave do SIGp: recusado.');
}
const id = String(($json.body || {}).notaRecebidaId || '');
if (!/^nrec-[0-9a-f]{32}$/.test(id)) throw new Error('notaRecebidaId inválido.');
return [{ json: { notaRecebidaId: id } }];
"""

CODIGO_MONTAR = r"""

// ---- nó: Recuperar itens e etiquetas (WF-10) ----
// Gerado por n8n/wf10/build_wf10.py. Monta o documento enviado pela tela no MESMO formato que o WF-08 monta de um
// anexo de e-mail ("Preparar anexos PDF" + "Recuperar itens e etiquetas"), para as etapas copiadas lerem igual.
// Não há etiquetas: o documento não veio do Gmail.
const j = $input.first().json || {};
if (!j.ok || !j.arquivoBase64) throw new Error('O SIGp não devolveu o documento da entrada manual.');
const binario = await this.helpers.prepareBinaryData(Buffer.from(String(j.arquivoBase64), 'base64'), String(j.nomeArquivo || 'documento'), String(j.mimeType || 'application/pdf'));
const soXml = Boolean(j.soXml);
const xmlTexto = String(j.xmlTexto || '');
const xmlNome = String(j.xmlNomeArquivo || j.nomeArquivo || '');
const lido = xmlTexto ? XmlFiscalSIGp.lerXmlFiscal(xmlTexto) : null;
return [{
  json: {
    gmailMessageId: String(j.gmailMessageId || ''),
    gmailThreadId: '',
    assunto: String(j.assunto || '').slice(0, 500),
    remetente: String(j.remetente || '').slice(0, 500),
    recebidaEm: String(j.recebidaEm || ''),
    corpo: String(j.corpo || '').slice(0, 1500),
    origemBusca: 'manual',
    semAnexo: false,
    soXml,
    gmailAttachmentId: String(j.gmailAttachmentId || 'manual'),
    nomeArquivo: String(j.nomeArquivo || ''),
    // Como no WF-08: com PDF, o XML válido acompanha e o inválido vira aviso; só XML, ele é o próprio documento.
    xmlTexto: soXml || (lido && lido.ok) ? xmlTexto : '',
    xmlNomeArquivo: soXml || (lido && lido.ok) ? xmlNome : '',
    xmlFiscal: soXml ? lido : (lido && lido.ok ? lido : null),
    xmlInvalidos: !soXml && lido && !lido.ok ? [`${xmlNome}: ${lido.erro}`] : [],
    etiquetas: {},
  },
  binary: { data: binario },
  pairedItem: { item: 0 },
}];
"""


def construir() -> dict:
    wf08 = json.loads(WF08.read_text(encoding="utf-8"))
    por_nome = {n["name"]: n for n in wf08["nodes"]}
    faltando = [n for n in COPIADAS if n not in por_nome]
    if faltando:
        raise SystemExit(f"O WF-08 gerado não tem as etapas {faltando}. Rode pwsh -File n8n/wf08/build_wf08.ps1.")
    nos = [
        {
            "parameters": {"httpMethod": "POST", "path": WEBHOOK, "responseMode": "onReceived", "options": {}},
            "id": "wf10_webhook", "name": "Entrada manual (pedido do SIGp)", "type": "n8n-nodes-base.webhook",
            "typeVersion": 2, "position": [0, 300], "webhookId": "b7f1c2a4-0e5d-4c8a-9a61-5f3e2d1c0a10",
            "notes": "A API do SIGp chama ao receber um documento pela tela (POST /api/notas-recebidas/manual). Responde na hora; a IA grava depois.",
        },
        {
            "parameters": {"mode": "runOnceForAllItems", "jsCode": CODIGO_CONFERIR},
            "id": "wf10_conferir", "name": "Conferir pedido", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 300],
        },
        {
            "parameters": {
                "method": "GET",
                "url": "={{ $env.SIGP_API_URL + '/api/notas-recebidas/' + $json.notaRecebidaId + '/entrada-manual' }}",
                "sendHeaders": True, "headerParameters": CABECALHO_API, "options": {"timeout": 60000},
            },
            "id": "wf10_baixar", "name": "Baixar documento do SIGp", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": [440, 300], "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000,
        },
        {
            "parameters": {"mode": "runOnceForAllItems", "jsCode": LIB_XML.read_text(encoding="utf-8") + CODIGO_MONTAR},
            "id": "wf10_montar", "name": "Recuperar itens e etiquetas", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, 300],
            "notes": "Mesmo nome do nó do WF-08: as etapas copiadas leem o documento por ele.",
        },
    ]
    x = 880
    for nome in COPIADAS:
        no = copy.deepcopy(por_nome[nome])
        no["id"] = "wf10_" + no["id"].removeprefix("wf08_")
        no["position"] = [x, 300]
        no.pop("credentials", None)
        nos.append(no)
        x += 220
    if any(n["type"] == "n8n-nodes-base.gmail" for n in nos):
        raise SystemExit("O WF-10 não pode ter nó do Gmail.")
    sequencia = ["Entrada manual (pedido do SIGp)", "Conferir pedido", "Baixar documento do SIGp", "Recuperar itens e etiquetas"] + COPIADAS
    conexoes = {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(sequencia, sequencia[1:])}
    return {
        "id": ID,
        "name": "WF-10 - Entrada manual de notas (mesma leitura e IA do e-mail)",
        "nodes": nos,
        "connections": conexoes,
        "active": False,
        "settings": copy.deepcopy(wf08.get("settings") or {"executionOrder": "v1"}),
        "pinData": {},
        "meta": {"geradoPor": "n8n/wf10/build_wf10.py", "etapasDoWf08": COPIADAS},
    }


if __name__ == "__main__":
    wf = construir()
    SAIDA.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ok: {SAIDA.name} ({len(wf['nodes'])} nós; {len(COPIADAS)} etapas copiadas do WF-08)")
