"""Gera o utilitário "WF-08 utilitário - Reprocessar mensagens" (n8n/wf08/n8n_workflow_wf08_reprocessar.json).

Substitui o antigo "Liberar mensagens para reprocessar", que tirava SIGp/Importado de TODAS as mensagens
(a etiqueta servia de trava e precisava ser removida). Agora o próprio n8n reprocessa: este utilitário busca
as mensagens escolhidas no Gmail e as entrega ao WF-08 (gatilho "Reprocessamento (chamado pelo utilitário)").
Nenhuma etiqueta é removida; o WF-08 reaplica SIGp/Importado (sem efeito se já existe).

A API do SIGp só atualiza a extração de notas que ainda não foram associadas, descartadas ou postas em análise:
o reprocessamento nunca apaga o que o usuário já conferiu.

Uso, na raiz do projeto:  python n8n/wf08/build_reprocessar.py
Versão anterior: n8n/wf08/n8n_workflow_wf08_reprocessar.legado.json
"""
import json
import shutil
from pathlib import Path

PASTA = Path(__file__).resolve().parent
SAIDA = PASTA / "n8n_workflow_wf08_reprocessar.json"
LEGADO = PASTA / "n8n_workflow_wf08_reprocessar.legado.json"
GMAIL = {"gmailOAuth2": {"id": "6w8cHAuUwpPVa6tb", "name": "Gmail account"}}
WF08 = "5sQcHD7eYRgHxqgK"

if SAIDA.exists() and not LEGADO.exists():
    shutil.copyfile(SAIDA, LEGADO)

escolher = r"""// ESCOLHA AQUI as mensagens a reprocessar (busca do Gmail) e o máximo por execução.
// Exemplos:
//   'label:sigp-importado newer_than:3d'            importadas nos últimos 3 dias (padrão)
//   'from:minasonline.net.br newer_than:30d'        de um provedor
//   'rfc822msgid:<id-da-mensagem@provedor>'         uma mensagem específica
//   'label:sigp-importado subject:fatura after:2026/11/01'
// Nenhuma etiqueta é removida. Notas já associadas, descartadas ou em análise não têm os dados trocados.
const busca = 'label:sigp-importado newer_than:3d';
const limite = 20; // o OCR e a IA local processam um PDF por vez (cerca de 1 minuto cada)
return [{ json: { busca, limite } }];
"""
marcar = r"""// Mensagens escolhidas, marcadas como reprocessamento (aparece em dadosExtracao.classificacao.origemBusca).
const itens = $input.all().filter((i) => i.json && i.json.id);
if (!itens.length) throw new Error(`Nenhuma mensagem encontrada para a busca: ${$('Escolher mensagens').first().json.busca}`);
return itens.map((i) => ({ json: { ...i.json, origemBusca: 'reprocessamento' }, binary: i.binary }));
"""

nos = [
    {"parameters": {}, "id": "repr_manual", "name": "Executar manualmente", "type": "n8n-nodes-base.manualTrigger",
     "typeVersion": 1, "position": [0, 300]},
    {"parameters": {"mode": "runOnceForAllItems", "jsCode": escolher}, "id": "repr_escolher", "name": "Escolher mensagens",
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 300],
     "notes": "Edite a busca do Gmail e o limite neste nó antes de executar."},
    {"parameters": {"resource": "message", "operation": "getAll", "returnAll": False, "limit": "={{ $json.limite }}",
                    "simple": False, "filters": {"q": "={{ $json.busca }}", "readStatus": "both"},
                    "options": {"downloadAttachments": True, "dataPropertyAttachmentsPrefixName": "attachment_"}},
     "id": "repr_buscar", "name": "Buscar mensagens no Gmail", "type": "n8n-nodes-base.gmail", "typeVersion": 2.2,
     "position": [440, 300], "credentials": GMAIL},
    {"parameters": {"mode": "runOnceForAllItems", "jsCode": marcar}, "id": "repr_marcar", "name": "Marcar reprocessamento",
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, 300]},
    {"parameters": {"source": "database", "workflowId": {"__rl": True, "mode": "id", "value": WF08},
                    "options": {"waitForSubWorkflow": True}},
     "id": "repr_wf08", "name": "Reprocessar no WF-08", "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2,
     "position": [880, 300],
     "notes": "Mesmo caminho das mensagens novas: OCR, regras, IA local, XML e gravação no SIGp. Etiquetas não são removidas."},
]
liga = lambda destino: {"main": [[{"node": destino, "type": "main", "index": 0}]]}  # noqa: E731
wf = {
    "id": "sigpWF08Reprocessa",
    "name": "WF-08 utilitário - Reprocessar mensagens (sem tirar etiquetas)",
    "nodes": nos,
    "connections": {
        "Executar manualmente": liga("Escolher mensagens"),
        "Escolher mensagens": liga("Buscar mensagens no Gmail"),
        "Buscar mensagens no Gmail": liga("Marcar reprocessamento"),
        "Marcar reprocessamento": liga("Reprocessar no WF-08"),
    },
    "settings": {"executionOrder": "v1"},
    "active": False,
    "pinData": {},
}
SAIDA.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Gerado: {SAIDA.name} ({len(nos)} nós)")
