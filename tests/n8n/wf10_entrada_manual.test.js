// WF-10 (entrada manual): as etapas de leitura e IA são as do WF-08, sem mudança; não há Gmail; a entrada confere a
// chave do SIGp e monta o documento no mesmo formato do anexo de e-mail.
// Uso: node tests/n8n/wf10_entrada_manual.test.js n8n_workflow_wf10_entrada_manual.json n8n_workflow_wf08_gmail_inbox.json
const fs = require('fs');
const wf = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const wf08 = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
let falhas = 0; const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) falhas++; };
const no = (w, n) => w.nodes.find((x) => x.name === n);
const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;

// 1. Etapas copiadas idênticas às do WF-08 (parâmetros iguais: mudar o WF-08 sem gerar o WF-10 de novo quebra aqui).
for (const nome of wf.meta.etapasDoWf08) {
  const a = no(wf, nome); const b = no(wf08, nome);
  ok(a && b && JSON.stringify(a.parameters) === JSON.stringify(b.parameters), `etapa igual ao WF-08: ${nome}`);
}
ok(!wf.nodes.some((n) => n.type === 'n8n-nodes-base.gmail' || n.credentials), 'nenhum nó do Gmail nem credencial');
const hook = wf.nodes.find((n) => n.type === 'n8n-nodes-base.webhook');
ok(hook && hook.parameters.path === 'sigp-entrada-manual' && hook.parameters.httpMethod === 'POST' && hook.parameters.responseMode === 'onReceived',
  'webhook POST /webhook/sigp-entrada-manual responde ao receber');
// Fluxo em linha: entrada -> conferir -> baixar -> montar -> etapas do WF-08 -> gravar.
let atual = hook.name; const visitados = [atual];
while (wf.connections[atual]) { atual = wf.connections[atual].main[0][0].node; visitados.push(atual); }
ok(visitados.length === wf.nodes.length && atual === 'Salvar na caixa SIGp', `fluxo em linha até gravar (${visitados.length} nós)`);
ok(wf.id === 'sigpWF10EntradaMan' && wf.active === false, 'id fixo e inativo no arquivo (o instalador publica)');

// 2. Conferir pedido: só com a chave do SIGp.
const conferir = (headers, body, env = { SIGP_API_KEY: 'chave-certa' }) =>
  new Function('$json', '$env', no(wf, 'Conferir pedido').parameters.jsCode)({ headers, body }, env);
const id = 'nrec-' + 'a'.repeat(32);
ok(conferir({ 'x-api-key': 'chave-certa' }, { notaRecebidaId: id })[0].json.notaRecebidaId === id, 'com a chave: segue');
const recusa = (f) => { try { f(); return false; } catch (e) { return true; } };
ok(recusa(() => conferir({}, { notaRecebidaId: id })), 'sem a chave: recusado');
ok(recusa(() => conferir({ 'x-api-key': 'outra' }, { notaRecebidaId: id })), 'chave errada: recusado');
ok(recusa(() => conferir({ 'x-api-key': '' }, { notaRecebidaId: id }, { SIGP_API_KEY: '' })), 'n8n sem SIGP_API_KEY: recusado');
ok(recusa(() => conferir({ 'x-api-key': 'chave-certa' }, { notaRecebidaId: '../x' })), 'id fora do formato: recusado');

// 3. Montar o documento como o WF-08 monta o anexo de e-mail.
(async () => {
  const montar = (j) => new AsyncFunction('$input', 'Buffer', no(wf, 'Recuperar itens e etiquetas').parameters.jsCode).call(
    { helpers: { prepareBinaryData: async (buf, nome, mime) => ({ fileName: nome, mimeType: mime, tamanho: buf.length }) } },
    { first: () => ({ json: j }) }, Buffer);
  const xml = fs.readFileSync('docs/XML para testes/01-ITABUNA-7001001-CONNECT-FIBRA.xml', 'utf8');
  const base = { ok: true, gmailMessageId: 'manual-x', gmailAttachmentId: 'manual', assunto: 'Entrada manual: f.pdf', remetente: 'Entrada manual (ana)',
    recebidaEm: '2026-11-24T10:00:00+00:00', corpo: 'entregue no balcão', nomeArquivo: 'f.pdf', mimeType: 'application/pdf',
    arquivoBase64: Buffer.from('%PDF-1.4 x').toString('base64') };
  let [r] = await montar({ ...base, soXml: false, xmlTexto: xml, xmlNomeArquivo: 'n.xml' });
  ok(r.binary.data.tamanho === 10 && r.binary.data.mimeType === 'application/pdf', 'PDF vira o binário "data" (como o anexo)');
  ok(r.json.origemBusca === 'manual' && r.json.semAnexo === false && r.json.corpo === 'entregue no balcão', 'observação faz o papel do corpo do e-mail');
  ok(r.json.xmlFiscal && r.json.xmlFiscal.ok && r.json.xmlFiscal.numero === '7001001' && r.json.xmlTexto === xml, 'PDF + XML: XML lido acompanha');
  const campos08 = ['gmailMessageId', 'gmailThreadId', 'assunto', 'remetente', 'recebidaEm', 'corpo', 'origemBusca', 'semAnexo', 'soXml',
    'gmailAttachmentId', 'nomeArquivo', 'xmlTexto', 'xmlNomeArquivo', 'xmlFiscal', 'xmlInvalidos', 'etiquetas'];
  ok(campos08.every((c) => c in r.json), 'mesmos campos do item do WF-08');
  [r] = await montar({ ...base, soXml: false, xmlTexto: '<x>não é nota</x>', xmlNomeArquivo: 'ruim.xml' });
  ok(r.json.xmlFiscal === null && r.json.xmlInvalidos.length === 1 && r.json.xmlTexto === '', 'PDF + XML inválido: vira aviso, como no e-mail');
  [r] = await montar({ ...base, soXml: true, nomeArquivo: 'n.xml', mimeType: 'application/xml', arquivoBase64: Buffer.from(xml).toString('base64'), xmlTexto: xml, xmlNomeArquivo: 'n.xml' });
  ok(r.json.soXml && r.json.xmlFiscal.ok && r.binary.data.mimeType === 'application/xml', 'só XML: o XML é o documento');
  ok(await montar({ ok: false }).then(() => false, () => true), 'resposta sem documento: erro');
  console.log(falhas ? `${falhas} falha(s)` : 'todos os testes passaram');
  process.exit(falhas ? 1 : 0);
})();
