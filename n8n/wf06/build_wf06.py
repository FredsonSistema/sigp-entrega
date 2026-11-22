"""Gera o WF-06 com alertas em texto amigável (abertura escrita pela LLM local e conferida pelo código).
Base: n8n/wf06/base_wf06.json (cópia do WF-06 anterior, criada na primeira execução).
Fontes: alertas_lib.js (lógica), nos.js (nós Code), prompt_alerta.md e schema_alerta.json.
Mudanças: resumo às 08:00, janela de 5 dias, nó da LLM local, nó de conferência, e-mail pelo Gmail para os
e-mails de Configurações > Alertas por e-mail. Uso, na raiz do projeto:  python n8n/wf06/build_wf06.py   (idempotente)
"""
import json
import re
import shutil
import uuid
from pathlib import Path

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parents[1]
ATUAL = RAIZ / "n8n_workflow_wf06_vencimentos.json"
BASE = PASTA / "base_wf06.json"
CREDENCIAL_GMAIL = {"gmailOAuth2": {"id": "6w8cHAuUwpPVa6tb", "name": "Gmail account"}}  # a mesma do WF-08

if not BASE.exists():
    if "Conferir texto da IA" in ATUAL.read_text(encoding="utf-8"):
        raise SystemExit("O WF-06 atual já foi gerado por este script e a base sumiu; restaure n8n/wf06/base_wf06.json.")
    shutil.copyfile(ATUAL, BASE)
wf = json.loads(BASE.read_text(encoding="utf-8"))

lib = (PASTA / "alertas_lib.js").read_text(encoding="utf-8").strip()
fonte = (PASTA / "nos.js").read_text(encoding="utf-8")
troca = {
    "/*__LIB__*/": lib,
    "/*__PROMPT__*/": json.dumps((PASTA / "prompt_alerta.md").read_text(encoding="utf-8").strip(), ensure_ascii=False),
    "/*__SCHEMA__*/": json.dumps(json.loads((PASTA / "schema_alerta.json").read_text(encoding="utf-8")), ensure_ascii=False),
}
codigo = {}
for nome, corpo in re.findall(r"// ==== NO: (.+?)\n(.*?)// ==== FIM", fonte, flags=re.S):
    for marcador, valor in troca.items():
        corpo = corpo.replace(marcador, valor)
    codigo[nome.strip()] = corpo.strip() + "\n"


def no(nome):
    return next(n for n in wf["nodes"] if n["name"] == nome)


# Horário e janela (padrão combinado: 08:00, aviso a partir de 5 dias antes).
gatilho = no("Todo dia às 07:00")
gatilho["name"] = "Todo dia às 08:00"
gatilho["parameters"]["rule"]["interval"][0]["expression"] = "0 8 * * *"
no("Buscar alertas na API")["parameters"]["url"] = "={{ $env.SIGP_API_URL }}/api/alertas?dias=5"

no("Montar resumo diário")["parameters"]["jsCode"] = codigo["Montar resumo diário"]
gravar = no("Gravar resumo no SIG")
gravar["parameters"]["jsonBody"] = ("={{ JSON.stringify({ escopo: 'SIG', titulo: $json.titulo, referencia: $json.referencia, "
                                    "conteudo: $json.conteudo, modelo: $json.modelo, dados: $json.dados, origem: 'n8n' }) }}")
no("Repassar mensagem")["parameters"]["jsCode"] = "return [{ json: $('Conferir texto da IA').first().json }];\n"

gmail = no("Gmail - relatório")
gmail.pop("disabled", None)
gmail["credentials"] = CREDENCIAL_GMAIL
gmail["parameters"]["options"] = {"appendAttribution": False}
gmail["notes"] = "Envia para os e-mails de Configurações > Alertas por e-mail. Mesma conta Gmail do WF-08."
gmail["parameters"]["sendTo"] = "={{ $json.para }}"

for nome in ("Gravar resumo no SIG", "Repassar mensagem", "Gmail - relatório", "Telegram - alerta", "WhatsApp - alerta (Evolution API)"):
    no(nome)["position"][0] += 440
gmail["position"][0] += 660

wf["nodes"] += [
    {
        "parameters": {
            "method": "POST",
            "url": "={{ ($env.SIGP_OLLAMA_URL || 'http://ollama:11434') + '/api/chat' }}",
            "sendBody": True, "specifyBody": "json", "contentType": "json",
            "jsonBody": "={{ JSON.stringify($json.ollamaBody) }}",
            "options": {"timeout": 180000},
        },
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "sigpWF06/llm")), "name": "LLM local — texto amigável (Ollama)", "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2, "position": [860, 300], "onError": "continueRegularOutput",
        "notes": "LLM local (nenhum dado sai da rede). Escreve só a abertura do e-mail. Falha ou demora: texto padrão.",
    },
    {
        "parameters": {"jsCode": codigo["Conferir texto da IA"]},
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "sigpWF06/conferir")), "name": "Conferir texto da IA", "type": "n8n-nodes-base.code", "typeVersion": 2,
        "position": [1080, 300],
        "notes": "Números, datas, links e pagamentos da abertura conferidos com os fatos. Se não bater, texto padrão.",
    },
    {
        "parameters": {
            "method": "GET",
            "url": "={{ $env.SIGP_API_URL }}/api/configuracoes/alertas",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "X-API-Key", "value": "={{ $env.SIGP_API_KEY || '' }}"}]},
            "options": {"response": {"response": {"fullResponse": True, "neverError": True}}},
        },
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "sigpWF06/destinatarios")), "name": "Buscar destinatários", "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2, "position": [1740, 140],
        "notes": "Configurações > Alertas por e-mail (sem lista salva, vale SIGP_RELATORIO_EMAIL do .env).",
    },
    {
        "parameters": {"jsCode": codigo["Juntar destinatários"]},
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "sigpWF06/juntar-destinatarios")), "name": "Juntar destinatários",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1960, 140],
        "notes": "Sem e-mail configurado: não envia (o resumo já está gravado no SIG).",
    },
]

c = wf["connections"]
c["Todo dia às 08:00"] = c.pop("Todo dia às 07:00")
c["Montar resumo diário"] = {"main": [[{"node": "LLM local — texto amigável (Ollama)", "type": "main", "index": 0}]]}
c["LLM local — texto amigável (Ollama)"] = {"main": [[{"node": "Conferir texto da IA", "type": "main", "index": 0}]]}
c["Conferir texto da IA"] = {"main": [[{"node": "Gravar resumo no SIG", "type": "main", "index": 0}]]}
saidas = c["Repassar mensagem"]["main"][0]
for s in saidas:
    if s["node"] == "Gmail - relatório":
        s["node"] = "Buscar destinatários"
c["Buscar destinatários"] = {"main": [[{"node": "Juntar destinatários", "type": "main", "index": 0}]]}
c["Juntar destinatários"] = {"main": [[{"node": "Gmail - relatório", "type": "main", "index": 0}]]}

wf["name"] = "SIGp - WF-06 Vencimentos e alertas diários (texto amigável pela IA local)"
ATUAL.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"WF-06 gerado: {ATUAL.name} ({len(wf['nodes'])} nós). Base: {BASE.relative_to(RAIZ)}")

# Utilitário: o mesmo resumo sob demanda (n8n execute --id=sigpWF06Agora000), sem o reenvio de 15 em 15 minutos.
agora = json.loads(json.dumps(wf))
agora["id"] = "sigpWF06Agora000"
agora["name"] = "WF-06 utilitário - gerar resumo de alertas agora"
agora["active"] = False
fora = {"Todo dia às 08:00", "A cada 15 minutos", "Reenviar eventos pendentes"}
agora["nodes"] = [n for n in agora["nodes"] if n["name"] not in fora]
for n in agora["nodes"]:
    n["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sigpWF06Agora000/{n['name']}"))
agora["nodes"].append({"parameters": {"inputSource": "passthrough"}, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "sigpWF06Agora000/gatilho")),
                       "name": "Gerar agora", "type": "n8n-nodes-base.executeWorkflowTrigger", "typeVersion": 1.1, "position": [200, 300]})
ca = agora["connections"]
for nome in fora:
    ca.pop(nome, None)
ca["Gerar agora"] = {"main": [[{"node": "Buscar alertas na API", "type": "main", "index": 0}]]}
for k in ("versionId", "meta", "pinData", "staticData", "triggerCount", "shared", "tags"):
    agora.pop(k, None)
(PASTA / "n8n_workflow_wf06_agora.json").write_text(json.dumps(agora, ensure_ascii=False, indent=2), encoding="utf-8")
print("Utilitário gerado: n8n/wf06/n8n_workflow_wf06_agora.json")
