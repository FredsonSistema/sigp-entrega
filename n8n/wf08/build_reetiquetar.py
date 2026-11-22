"""Gera o workflow "WF-08 utilitário - Reaplicar SIGp/Importado" (n8n_workflow_wf08_reetiquetar.json).

Coloca a etiqueta SIGp/Importado em toda mensagem do Gmail que o SIGp já tem em Notas recebidas
(inclusive descartadas). Não reprocessa nada e não altera notas: só etiqueta. Adicionar uma etiqueta que a
mensagem já tem não muda nada, então pode rodar quantas vezes quiser.

Motivo (14/11/2026): o utilitário "Liberar mensagens para reprocessar" tira SIGp/Importado de TODAS as
mensagens; a busca histórica reetiqueta só as que reprocessa (20 por vez), e as demais ficavam sem etiqueta.
Roda manualmente e todo dia às 06:00. Se quiser reprocessar uma mensagem, rode "Liberar" e logo depois a busca
histórica (antes das 06:00 seguintes).

Uso, na raiz do projeto:  python n8n/wf08/build_reetiquetar.py
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "n8n_workflow_wf08_reetiquetar.json"
GMAIL = {"gmailOAuth2": {"id": "6w8cHAuUwpPVa6tb", "name": "Gmail account"}}
CHAVE = {"parameters": [{"name": "X-API-Key", "value": "={{ $env.SIGP_API_KEY || '' }}"}]}

codigo_mensagens = r"""// Mensagens do Gmail que o SIGp já tem (todas as notas recebidas, inclusive descartadas).
const etiqueta = $input.all().map((i) => i.json).find((e) => e.name === 'SIGp/Importado');
if (!etiqueta) throw new Error('A etiqueta SIGp/Importado não existe nesta conta do Gmail.');
const notas = [
  ...($('Notas recebidas no SIGp').first().json.items || []),
  ...($('Notas descartadas no SIGp').first().json.items || []),
];
// IDs do Gmail são hexadecimais; registros de teste/manuais (sem mensagem no Gmail) ficam de fora.
const ids = [...new Set(notas.map((n) => String(n.gmail_message_id || '').trim()).filter((id) => /^[0-9a-f]{10,24}$/i.test(id)))];
return ids.map((messageId) => ({ json: { messageId, labelId: etiqueta.id } }));
"""
codigo_resumo = r"""const itens = $input.all();
const falhas = itens.filter((i) => i.json.error);
return [{ json: { mensagens: itens.length, falhas: falhas.length, erros: falhas.slice(0, 5).map((i) => String(i.json.error?.message || i.json.error).slice(0, 200)) } }];
"""

nos = [
    {"parameters": {}, "id": "reet_manual", "name": "Executar manualmente", "type": "n8n-nodes-base.manualTrigger",
     "typeVersion": 1, "position": [0, 200]},
    {"parameters": {"rule": {"interval": [{"field": "days", "triggerAtHour": 6}]}}, "id": "reet_diario",
     "name": "Todo dia às 06:00", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 400],
     "notes": "Rede de segurança: devolve SIGp/Importado às mensagens que já estão no SIGp."},
    {"parameters": {"url": "={{ $env.SIGP_API_URL + '/api/notas-recebidas' }}", "sendHeaders": True, "headerParameters": CHAVE,
                    "options": {"timeout": 30000}},
     "id": "reet_api", "name": "Notas recebidas no SIGp", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [240, 300], "executeOnce": True},
    {"parameters": {"url": "={{ $env.SIGP_API_URL + '/api/notas-recebidas?status=DESCARTADA' }}", "sendHeaders": True,
                    "headerParameters": CHAVE, "options": {"timeout": 30000}},
     "id": "reet_api_desc", "name": "Notas descartadas no SIGp", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [460, 300], "executeOnce": True},
    {"parameters": {"resource": "label", "returnAll": True}, "id": "reet_labels", "name": "Listar etiquetas Gmail",
     "type": "n8n-nodes-base.gmail", "typeVersion": 2.2, "position": [680, 300], "credentials": GMAIL, "executeOnce": True},
    {"parameters": {"mode": "runOnceForAllItems", "jsCode": codigo_mensagens}, "id": "reet_ids", "name": "Mensagens a etiquetar",
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [900, 300]},
    {"parameters": {"operation": "addLabels", "messageId": "={{ $json.messageId }}", "labelIds": ["={{ $json.labelId }}"]},
     "id": "reet_add", "name": "Aplicar SIGp/Importado", "type": "n8n-nodes-base.gmail", "typeVersion": 2.2,
     "position": [1120, 300], "credentials": GMAIL, "onError": "continueRegularOutput",
     "notes": "Mensagem apagada do Gmail: registra a falha e segue com as outras."},
    {"parameters": {"mode": "runOnceForAllItems", "jsCode": codigo_resumo}, "id": "reet_resumo", "name": "Resumo",
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1340, 300]},
]
liga = lambda destino: {"main": [[{"node": destino, "type": "main", "index": 0}]]}  # noqa: E731
wf = {
    "id": "sigpWF08Reetiquetar",
    "name": "WF-08 utilitário - Reaplicar SIGp/Importado",
    "nodes": nos,
    "connections": {
        "Executar manualmente": liga("Notas recebidas no SIGp"),
        "Todo dia às 06:00": liga("Notas recebidas no SIGp"),
        "Notas recebidas no SIGp": liga("Notas descartadas no SIGp"),
        "Notas descartadas no SIGp": liga("Listar etiquetas Gmail"),
        "Listar etiquetas Gmail": liga("Mensagens a etiquetar"),
        "Mensagens a etiquetar": liga("Aplicar SIGp/Importado"),
        "Aplicar SIGp/Importado": liga("Resumo"),
    },
    "settings": {"executionOrder": "v1"},
    "active": False,
    "pinData": {},
}
SAIDA.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Gerado: {SAIDA.name} ({len(nos)} nós)")
