# API SIGp

API Flask (servida por waitress) que é a fonte única de locais, notas, pagamentos, faturas, conciliações, correções, alertas e análises do SIGp. Roda no container `sigp_api` (`docker compose up -d --build api`), na porta `5001` publicada só em `127.0.0.1`; o n8n a chama por `http://api:5001`. Persistência SQLite em `backend/data/sigp.db` (volume montado).

## Responsabilidades

- Normalizar e persistir notas lançadas e pagas, com origem (`manual`, `n8n`, `praxio`…), `sistemaOrigem` e `idExterno` (reenvio do mesmo documento externo atualiza em vez de duplicar).
- Conciliar em 3 vias (lançada + paga + fatura) e avisar o n8n a cada mudança de status.
- Guardar faturas PDF e refazer a conciliação quando uma fatura é anexada.
- Aceitar correções manuais auditadas (antes/depois, usuário e motivo).
- Manter agências, rodoviárias e garagens (com provedores e dia de vencimento) sincronizadas a partir da interface.
- Calcular alertas (vencimentos, fatura ausente, divergência) e os resumos do SIG e do SIE.
- Guardar as análises de IA gravadas pelo n8n.

## Endpoints

| Rota | Uso |
|---|---|
| `GET /api/health` | Saúde e configuração (autenticação, regra de fatura, eventos). |
| `POST /api/auth/verify` | Valida a chave `X-API-Key` sem alterar dados; usado pela tela de configuração da interface. |
| `GET/POST /api/notas/lancadas` | Lista / grava nota lançada (`dados`, `entidadeTipo`, `entidadeId`, `origem`, `sistemaOrigem`, `idExterno`). |
| `GET/POST /api/notas/pagas` | Lista / grava pagamento. Com `notaLancadaId` (ou quando só uma nota lançada corresponde) já concilia e devolve `conciliacao`. |
| `PATCH /api/notas/lancadas/<id>`, `PATCH /api/notas/pagas/<id>` | Correção manual: `{campos: {...}, usuario, motivo}`. Reconcilia em seguida. 409 se a nova chave já existir. |
| `GET /api/notas/lancadas/<id>/correcoes`, `GET /api/notas/pagas/<id>/correcoes` | Histórico de correções. |
| `POST /api/notas/conciliar` | Concilia um par `{notaLancadaId, notaPagaId}`. |
| `POST /api/notas/reconciliar` | Reaplica a regra atual a todas as conciliações existentes. |
| `GET /api/notas/conciliacoes` | Lista conciliações. |
| `GET/POST /api/faturas`, `DELETE /api/faturas/<id>`, `GET /api/faturas/<id>/arquivo` | Faturas PDF por local (opcionalmente ligadas a uma nota); no upload, `descricao` é opcional. Excluir também remove o PDF e atualiza as conciliações ligadas. |
| `POST /api/faturas/<id>/vincular` | Vincula uma fatura existente a `{ "notaLancadaId": "...", "descricao": "..." }`. Exige descrição revisada e nota do mesmo local; 404 se não encontrar os registros, 409 para vínculo conflitante. Recalcula emissor, valor e vencimento, atualiza conciliações e registra evento; não cria pagamento. |
| `GET/POST /api/notas-recebidas`, `GET /api/notas-recebidas/<id>/arquivo` | Caixa de entrada de PDFs fiscais recebidos. O `POST` é multipart (`gmailMessageId`, `gmailAttachmentId`, `arquivo`, `dadosExtracao` JSON e metadados opcionais); a combinação mensagem/anexo é idempotente e permite vários PDFs no mesmo e-mail. PDFs ficam em `backend/data/notas_recebidas/`. |
| `POST /api/notas-recebidas/<id>/extrair` | Envia o PDF armazenado ao OCR interno e devolve sugestões de campos para revisão. Não grava nota nem fatura; a gravação ocorre somente após a associação confirmada. |
| `POST /api/notas-recebidas/classificar` | Classifica assunto, remetente, nome do arquivo e texto OCR com termos fiscais/de internet e nomes de provedores cadastrados nos locais. Devolve categoria, confiança e evidências; é uma regra explicável, não um modelo treinado, e não descarta PDFs. |
| `POST /api/notas-recebidas/<id>/comparar` | Com `{ "entidadeTipo": "...", "entidadeId": "...", "dados": {...} }`, compara os campos revisados com notas do local selecionado. Identificador igual ou mesmo provedor e vencimento apontam nota candidata; outros vencimentos permanecem como notas separadas. Não grava alterações. |
| `PATCH /api/notas-recebidas/<id>/associar` | Associa com `{ "entidadeTipo": "agencia\|rodoviaria\|garagem", "entidadeId": "...", "operador": "...", "dados": {...} }`. Se houver divergência, exige `{ "notaLancadaId": "...", "confirmarAtualizacao": true }`; sem aceite devolve HTTP 409 e os campos divergentes. A interface também permite manter a nota recebida na caixa, sem associar. Ao confirmar, atualiza a nota escolhida e a fatura local, copia o PDF para o fluxo do SIG e reconcilia somente com pagamentos já existentes. Devolve a etiqueta Gmail hierárquica `SIGp/<tipo>/<local>` e deixa sua aplicação pendente para o n8n. |
| `GET /api/notas-recebidas?etiquetaPendente=1`, `POST /api/notas-recebidas/<id>/confirmar-etiqueta` | Fila de etiquetas para o workflow Gmail; o n8n confirma `{ "ok": true }` após aplicar a etiqueta ou informa `{ "ok": false, "erro": "..." }`. |
| `POST /api/locais/<tipo>/item` | Cria um local mínimo para permitir a associação; body `{ "nome": "...", "cidade": "..." }`. Tipos permitidos: `agencia`, `rodoviaria`, `garagem`. |
| `POST/GET/DELETE /api/notas/lancadas/<id>/fatura` (+ `/arquivo`) | Rota legada de fatura por nota; `DELETE` remove o anexo e atualiza as conciliações. |
| `GET /api/locais?tipo=`, `GET /api/locais/item/<id>`, `PUT /api/locais/<tipo>` | Locais; o `PUT` recebe o retrato completo do tipo e inativa (não apaga) quem não vier. |
| `GET /api/alertas?dias=7&tipo=vencimento,fatura_ausente,divergencia&hoje=AAAA-MM-DD` | Alertas ordenados por severidade. |
| `GET /api/sig/resumo?inicio&fim&entidadeTipo&provedor&status` | Indicadores gerenciais (máx. 36 meses). |
| `GET /api/sie/resumo?inicio&fim` | Indicadores executivos, só ciclos fechados em 3 vias, com as últimas análises SIE e uma lista separada das notas recebidas por Gmail em andamento; esta lista não altera os indicadores de fechamento. |
| `GET/POST /api/analises?escopo=SIG\|SIE` | Análises gravadas pelo n8n (`escopo`, `conteudo`, `titulo`, `referencia`, `modelo`, `dados`). |
| `GET /api/eventos?status=`, `POST /api/eventos/reenviar` | Fila de eventos para o n8n e reenvio de pendentes/falhas. |
| `POST /api/sie/webhook` | Legado: só registra o evento em `api_events`. |

### Status de conciliação

`PENDENTE` (dados insuficientes ou serviço não revisado) → `PAGO_PARCIAL` → `AGUARDANDO_FATURA` (lançada e paga conferem) → `MATCH` (fatura conferida). `DIVERGENCIA` quando identidade, local, valor, serviço ou fatura não batem. Pagamento integral após o vencimento grava a nota paga como `PAGO_COM_ATRASO`.

## Configuração

Variáveis lidas pela API (no Compose, vêm do `.env`; ver `../.env.example`): `SIGP_API_KEY`, `SIGP_CORS_ORIGINS`, `SIGP_EXIGIR_FATURA`, `SIGP_N8N_EVENTOS_URL`, `SIGP_N8N_TOKEN`, `SIGP_OCR_URL` (padrão interno `http://ocr:5002/extract`), além de `SIGP_HOST`/`SIGP_PORT` (padrão `127.0.0.1:5001` fora do container) e `SIGP_DEBUG=1` para o servidor de desenvolvimento do Flask.

## Executar fora do Docker e testar

```powershell
.\.venv-1\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-1\Scripts\python.exe -m backend.app           # 127.0.0.1:5001 (pare o container sigp_api antes)
.\.venv-1\Scripts\python.exe -m unittest discover -s tests
```

## Limitações conhecidas

- SQLite atende o uso local monousuário; backup, restore e uso multiusuário precisam de desenho próprio.
- O painel legado `/sie` (porta `5000`, `buscador_nfse.py`) é um painel de conciliação com banco separado; não é o SIE executivo.
- Há chaves fiscais duplicadas no histórico; a API bloqueia novas duplicações e o SIG exclui os grupos ambíguos até revisão.
