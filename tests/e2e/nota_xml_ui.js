// Fatura PDF + XML da nota (como o WF-08 envia): cartão mostra o XML, associa e o XML aparece na nota do local.
// Usa a API de TESTE. O XML é lido aqui pela mesma lib do n8n (n8n/lib/xml_fiscal.js).
const fs = require('fs');
const path = require('path');
const { API_TEST_URL, launch, shot, check, loginFresh, abrirNota } = require('./lib');
const XF = require('../../n8n/lib/xml_fiscal.js');

const ARQUIVO = path.join(__dirname, '..', '..', 'docs', 'XML para testes', '01-ITABUNA-7001001-CONNECT-FIBRA.xml');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await loginFresh(page);
    // Chave única por execução: a mesma nota paga duas vezes (mesma chave, valor e data) é duplicidade real.
    const original = fs.readFileSync(ARQUIVO, 'utf8');
    const chaveBase = XF.lerXmlFiscal(original).chave;
    const xmlTexto = original.split(chaveBase).join(chaveBase.slice(0, -13) + String(Date.now()).slice(-13));
    const lido = XF.lerXmlFiscal(xmlTexto);
    // Leitura do PDF com valor diferente (100) e sem número: o XML deve prevalecer e a divergência aparecer.
    const dados = { ...XF.aplicarPrioridadeXml({ emissorNome: 'CONNECT', numero: '999999999', valorTotal: 100, dataVencimento: lido.dataVencimento }, lido), xmlFiscal: lido };
    const sufixo = Date.now();
    const { local, item } = await page.evaluate(async ({ api, xmlTexto, dados, sufixo }) => {
      const local = (await (await fetch(`${api}/api/locais/agencia/item`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome: `Agência XML ${sufixo}`, cidade: 'Itabuna' }),
      })).json()).item;
      const form = new FormData();
      form.append('gmailMessageId', `msg-xml-ui-${sufixo}`);
      form.append('gmailAttachmentId', 'a1');
      form.append('assunto', 'Fatura CONNECT FIBRA + NFS-e');
      form.append('dadosExtracao', JSON.stringify(dados));
      form.append('xml', new Blob([xmlTexto], { type: 'application/xml' }), 'nfse-7001001.xml');
      form.append('arquivo', new Blob(['%PDF-1.4 fatura de teste'], { type: 'application/pdf' }), 'fatura-7001001.pdf');
      const item = (await (await fetch(`${api}/api/notas-recebidas`, { method: 'POST', body: form })).json()).item;
      return { local, item };
    }, { api: API_TEST_URL, xmlTexto, dados, sufixo });
    check(results, 'API recebeu PDF + XML', Boolean(item && item.xmlUrl), item && item.xmlUrl);
    await page.evaluate((l) => {
      const list = JSON.parse(localStorage.getItem('ti_agencias_v1') || '[]');
      list.push({ ...l, notasFiscais: [] });
      localStorage.setItem('ti_agencias_v1', JSON.stringify(list));
    }, local);

    await page.evaluate(() => document.querySelector('[data-view="notas-recebidas"]').click());
    const card = await abrirNota(page, item.id);
    const info = await card.locator('[data-role="xml-info"]').innerText();
    check(results, 'cartão mostra o XML (tipo, número, emissor, valor)', /NFS-e/.test(info) && /7001001/.test(info) && /CONNECT FIBRA TELECOM LTDA/.test(info) && /89,90/.test(info), info.split('\n')[1]);
    check(results, 'cartão avisa a divergência PDF × XML (vale o XML)', /Valor:.*PDF.*100,00.*XML.*89,90/.test(info.replace(/\s+/g, ' ')), info.replace(/\s+/g, ' ').slice(-140));
    check(results, 'campos já vêm com os valores do XML', await card.locator('[data-role="number"]').inputValue() === '7001001'
      && Number(String(await card.locator('[data-role="amount"]').inputValue()).replace(',', '.')) === 89.9);
    const href = await card.locator('[data-role="xml-info"] a', { hasText: 'Baixar XML' }).getAttribute('href');
    const baixado = await page.evaluate(async (u) => (await fetch(u)).text(), href);
    check(results, '"Baixar XML" devolve o arquivo original', baixado === xmlTexto);
    check(results, 'PDF continua disponível', await card.locator('a', { hasText: 'Abrir / imprimir PDF' }).count() === 1);
    await card.scrollIntoViewIfNeeded();
    await shot(page, 'xml-01-cartao');

    await card.locator('[data-role="type"]').selectOption('agencia');
    await card.locator('[data-role="location"]').selectOption(local.id);
    await card.locator('[data-action="compare"]').click();
    await card.locator('[data-action="commit"]').waitFor({ timeout: 15000 });
    await card.locator('[data-action="commit"]').click();
    // O documento do e-mail vira NOTA DISPONÍVEL do local; nota lançada (e paga) vem só do financeiro.
    await page.waitForFunction(() => /Nota disponível associada/.test(document.getElementById('notasRecebidasStatus')?.textContent || ''), null, { timeout: 20000 });
    const api = (u, opcoes) => page.evaluate(async ({ base, u, opcoes }) => (await (await fetch(`${base}${u}`, opcoes)).json()), { base: API_TEST_URL, u, opcoes });
    const nota = ((await api(`/api/notas-disponiveis?entidadeTipo=agencia&entidadeId=${local.id}`)).items || [])[0] || {};
    check(results, 'nota disponível com número e valor do XML', nota.numero === '7001001' && Number(nota.valor_total) === 89.9, JSON.stringify([nota.numero, nota.valor_total]));
    check(results, 'nota disponível tem os itens de serviço do XML', (nota.servicos || []).some((s) => /FIBRA OPTICA/.test(s.descricao)));
    check(results, 'chave lida do XML tem prioridade', nota.chave === lido.chave, nota.chave);
    const xmlDaNota = await page.evaluate(async ({ base, u }) => (await fetch(`${base}${u}`)).text(), { base: API_TEST_URL, u: nota.documentos?.[0]?.xmlUrl || '/x' });
    check(results, 'XML original guardado com a nota disponível', xmlDaNota === xmlTexto);
    const lancadas = ((await api('/api/notas/lancadas')).items || []).filter((n) => n.entidade_id === local.id);
    check(results, 'nenhuma nota lançada foi criada (é do financeiro)', lancadas.length === 0, JSON.stringify(lancadas.map((n) => n.id)));
    const linhas = await page.evaluate((id) => (JSON.parse(localStorage.getItem('ti_agencias_v1')).find((x) => x.id === id).notasFiscais || []).length, local.id);
    check(results, 'o local não ganhou linha de "nota lançada"', linhas === 0, String(linhas));
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.evaluate((id) => openModal(id), local.id);
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="nf"]'); // formulário em abas
    const cartao = page.locator('#ndList .nd-card').first();
    await cartao.waitFor({ timeout: 10000 });
    const textoCartao = await cartao.innerText();
    check(results, 'local mostra a nota disponível com PDF e XML, aguardando o financeiro',
      /AGUARDANDO O FINANCEIRO/.test(textoCartao) && /XML/.test(textoCartao) && /fatura-7001001\.pdf/.test(textoCartao), textoCartao.replace(/\s+/g, ' ').slice(0, 160));
    await cartao.scrollIntoViewIfNeeded();
    await shot(page, 'xml-02-nota-disponivel');
    await page.click('#btnCancel');
    // O financeiro lança a nota (mesma chave): liga à nota disponível; com a nota paga, o ciclo fecha com todas as evidências.
    const finId = `fin-xml-${sufixo}`;
    const base = { chave: lido.chave, numero: '7001001', serie: '1', provedorNome: 'CONNECT FIBRA TELECOM LTDA', dataEmissao: '2026-11-10', dataVencimento: lido.dataVencimento };
    const lanc = await api('/api/notas/lancadas', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: finId, source: 'json', entidadeTipo: 'agencia', entidadeId: local.id, dados: { ...base, valor: 89.9 } }) });
    check(results, 'nota lançada do financeiro se liga à nota disponível', lanc.ok && lanc.notaDisponivelId === nota.id, JSON.stringify([lanc.ok, lanc.notaDisponivelId, lanc.error]));
    const paga = await api('/api/notas/pagas', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: `fin-paga-${sufixo}`, source: 'json', entidadeTipo: 'agencia', entidadeId: local.id, valorPago: 89.9,
        dataPagamento: '2026-11-15', notaLancadaId: finId, dados: { ...base, valor: 89.9 } }) });
    check(results, 'nota paga do financeiro gravada', paga.ok, paga.error || '');
    const conc = ((await api('/api/notas/conciliacoes')).items || []).filter((c) => c.nota_lancada_id === finId).map((c) => c.status);
    check(results, 'conciliação fecha em MATCH (lançada + paga do financeiro + fatura do e-mail)', conc.includes('MATCH'), JSON.stringify(conc));
    await page.evaluate((id) => openModal(id), local.id);
    await page.waitForFunction(() => /LANÇADA PELO FINANCEIRO/.test(document.getElementById('ndList')?.textContent || ''), null, { timeout: 10000 });
    check(results, 'local mostra a nota disponível ligada à lançada', true);
    await shot(page, 'xml-03-ligada-ao-financeiro');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'xml-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
