// Código dos nós Code do WF-06 (alertas com texto amigável). build_wf06.py copia cada bloco para o nó e troca
// /*__LIB__*/ por alertas_lib.js, /*__PROMPT__*/ por prompt_alerta.md e /*__SCHEMA__*/ por schema_alerta.json.
// ==== NO: Montar resumo diário
// Fatos do dia calculados pelo SIGp; sem alertas, encerra sem notificar.
/*__LIB__*/
const fatos = montarFatos($input.first().json.body);
if (!fatos) return [];
const modelo = $env.SIGP_OLLAMA_MODEL || 'qwen2.5:3b';
return [{ json: { fatos, modelo, inicio: Date.now(), ollamaBody: montarPedidoLLM(fatos, /*__PROMPT__*/, /*__SCHEMA__*/, modelo) } }];
// ==== FIM
// ==== NO: Conferir texto da IA
// A abertura da LLM só é usada se passar na conferência; senão, vai o texto padrão. A lista vem da API.
/*__LIB__*/
const base = $('Montar resumo diário').first().json;
const escolha = escolherAbertura($input.first().json, base.fatos);
return [{ json: montarMensagem(base.fatos, escolha, base.modelo, Date.now() - base.inicio) }];
// ==== FIM
// ==== NO: Juntar destinatários
// Lista de Configurações > Alertas por e-mail (GET /api/configuracoes/alertas). Sem e-mail: não envia.
const r = $input.first().json || {};
const emails = (r.statusCode === 200 && Array.isArray(r.body?.emails)) ? r.body.emails : [];
if (!emails.length) return [];
return [{ json: { ...$('Repassar mensagem').first().json, para: emails.join(',') } }];
// ==== FIM
