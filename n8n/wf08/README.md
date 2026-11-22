# WF-08 v2 — Faturas de provedores do Gmail com IA local

Fonte do workflow `n8n_workflow_wf08_gmail_inbox.json` (raiz do projeto). Não edite os nós Code no editor do n8n: edite os arquivos desta pasta e gere o JSON de novo.

| Arquivo | Conteúdo |
|---|---|
| `prompt_classificacao.md` | Instruções do Qwen (prompt de sistema). |
| `schema_classificacao.json` | JSON Schema da resposta, enviado ao Ollama em `format`. |
| `wf08_lib.js` | Destinatário pela empresa do grupo, pedido à IA e regra de decisão. A extração por regras vem de `n8n/lib/extrator.js` (a mesma do WF-03 e do SIGp), colada antes desta lib pelo build. |
| `build_wf08.ps1` | Gera o JSON do workflow. Os remetentes e a busca do Gmail não ficam aqui: vêm do SIGp a cada leitura. |
| `testes_wf08.js` | Testes da `wf08_lib.js` com dados fictícios. |
| `verificar_sintaxe.js` | Confere a sintaxe dos nós Code e as conexões do JSON gerado. |

## Fluxo

```text
A cada 5 min: busca do SIGp → Gmail (só o que chegou desde a última leitura) | busca histórica manual (busca do SIGp, 20 por vez)
  → Preparar anexos PDF (um item por PDF; sem PDF → etiqueta SIGp/Sem-anexo)
  → OCR local → Regras do SIGp (/classificar) → Extrair campos por regras
  → Qwen 2.5 3B no Ollama local (JSON Schema, temperatura 0)
  → Consolidar decisão
      ├─ ignorar (IA segura de que não é cobrança + regras sem evidência + sem boleto) → SIGp/Ignorado
      └─ importar → POST /api/notas-recebidas → SIGp/Importado
```

XML da nota fiscal (`n8n/lib/xml_fiscal.js`, colado nos nós pelo build): "Preparar anexos PDF" lê os `.xml` da mensagem e liga cada um à fatura PDF
(um XML vale para todos os PDFs; com vários, decide o número da nota no nome do PDF). XML sem PDF entra sozinho, em Revisão. "Consolidar decisão" aplica a
prioridade do XML nos campos fiscais e registra as divergências; documento com XML nunca é ignorado. O SIGp guarda os dois arquivos.

Regras de decisão (`consolidar` em `wf08_lib.js`):

- Valor e vencimento lidos da **linha digitável** do boleto prevalecem sobre a IA. Divergência manda para Revisão.
- A IA não pode apontar empresa do grupo como provedor nem endereço como cliente (`EMPRESAS_DO_GRUPO`).
- Falha no OCR, no Ollama ou resposta inválida: o documento é importado em Revisão, nunca ignorado.
- Nada é apagado no Gmail. Para reprocessar uma mensagem, remova a etiqueta `SIGp/...` dela.

## Instalação

1. No Gmail da caixa monitorada, crie as etiquetas **`SIGp/Importado`**, **`SIGp/Ignorado`** e **`SIGp/Sem-anexo`**.
2. Ollama na rede do SIGp (já previsto em `docs/entrega-academica/sqlserver/compose.academic.yml`, alias `ollama`) e modelo baixado:
   ```powershell
   docker compose -f docs/entrega-academica/sqlserver/compose.academic.yml --env-file docs/entrega-academica/sqlserver/.env.academic up -d ollama-academic
   docker exec sigp_ollama_academic ollama pull qwen2.5:3b
   ```
   Opcional no `.env`: `SIGP_OLLAMA_URL` (padrão `http://ollama:11434`) e `SIGP_OLLAMA_MODEL` (padrão `qwen2.5:3b`).
3. Remetentes da busca: no SIGp, **Configurações > E-mail das faturas** (domínio do provedor ou e-mail; o padrão são os domínios dos provedores, em `backend/config_email_faturas.py`). O WF-08 pede a busca pronta em `GET /api/configuracoes/email-faturas` a cada leitura: trocar na tela vale em até 5 minutos, sem abrir o n8n. E-mail pessoal (de teste) fica só no banco, nunca neste repositório.
4. Gere, teste e importe:
   ```powershell
   pwsh -File n8n\wf08\build_wf08.ps1
   Get-Content n8n\lib\extrator.js, n8n\wf08\wf08_lib.js, n8n\wf08\testes_wf08.js -Raw | docker exec -i sigp_n8n node
   docker cp n8n_workflow_wf08_gmail_inbox.json sigp_n8n:/tmp/wf08.json
   Get-Content n8n\wf08\verificar_sintaxe.js -Raw | docker exec -i sigp_n8n node
   docker exec sigp_n8n n8n import:workflow --input=/tmp/wf08.json
   ```
   O JSON usa o mesmo ID do WF-08 atual (`5sQcHD7eYRgHxqgK`): a importação **substitui** a versão publicada e a deixa inativa.
5. No editor, confira a credencial Gmail nos 6 nós Gmail, rode **Executar busca histórica manual** e revise o resultado na aba Notas recebidas antes de ativar.

## Primeiro lote real (10/11/2026, execução 1554)

20 mensagens, 26 PDFs, 27 minutos (cerca de 58 s por PDF no Qwen; OCR e IA processam **um PDF por vez** no laço "Um PDF por vez", porque em paralelo o OCR devolve 503 e o Ollama estoura o tempo).

- 17 PDFs foram para **Aguardando associação**, com valor e vencimento conferidos pela linha digitável.
- 9 ficaram em **Revisão**: 3 PDFs da Brisanet que o OCR não conseguiu abrir (provável senha), notas fiscais da Vox classificadas como "lembrete" por causa do assunto do e-mail, uma nota de hotel (fora do escopo) e um boleto em que a IA leu o valor errado (a divergência foi detectada).

Reprocessar (sem tirar etiquetas): abra `WF-08 utilitário - Reprocessar mensagens (sem tirar etiquetas)` (`n8n/wf08/n8n_workflow_wf08_reprocessar.json`,
gerado por `n8n/wf08/build_reprocessar.py`), edite a busca do Gmail e o limite no nó "Escolher mensagens" (padrão: `label:sigp-importado newer_than:3d`, 20)
e execute. As mensagens vão ao WF-08 pelo gatilho "Reprocessamento (chamado pelo utilitário)" e seguem o mesmo caminho (OCR, regras, IA, XML).
Nenhuma etiqueta é removida. A API só atualiza a extração de notas ainda não associadas, descartadas ou em análise (o que você já conferiu não é apagado).
O antigo "Liberar mensagens para reprocessar" (tirava SIGp/Importado de todas as mensagens) está em `n8n_workflow_wf08_reprocessar.legado.json`.
Rede de segurança: `WF-08 utilitário - Reaplicar SIGp/Importado` (`build_reetiquetar.py`) roda todo dia às 06:00 e etiqueta toda mensagem que já está no SIGp.

## Desempenho medido no teste inicial (CPU, sem GPU, 10/11/2026)

Com 7 PDFs reais, o qwen2.5:3b levou de 14 a 98 s por documento (a primeira chamada inclui carregar o modelo). Acertou o tipo nos 7; provedor e cliente precisaram das salvaguardas acima. Por isso o gatilho roda a cada 5 minutos e o lote histórico tem 20 mensagens.
