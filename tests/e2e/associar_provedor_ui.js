// P2-04 pela interface: associar em Notas recebidas atualiza o provedor do local no navegador e na API,
// e editar/salvar o local depois não desfaz a atualização.
const { API_TEST_URL, launch, shot, check, loginFresh, abrirNota } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await loginFresh(page);
    // Local novo pela API, com o provedor "Brisanet" já cadastrado (sem valor nem vencimento).
    const local = await page.evaluate(async (api) => {
      const r = await fetch(`${api}/api/locais/agencia/item`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome: `Agência UI ${Date.now()}`, cidade: 'Ilhéus' }),
      });
      return (await r.json()).item;
    }, API_TEST_URL);
    await page.evaluate(({ local }) => {
      const list = JSON.parse(localStorage.getItem('ti_agencias_v1') || '[]');
      list.push({ ...local, provedores: [{ id: 'prov-ui-1', nome: 'Brisanet' }] });
      localStorage.setItem('ti_agencias_v1', JSON.stringify(list));
    }, { local });
    await page.evaluate(() => window.SIGP_API.persistLocation('ti_agencias_v1'));

    await page.evaluate(() => document.querySelector('[data-view="notas-recebidas"]').click());
    await page.waitForSelector('#notasRecebidasLista [data-note-id]', { state: 'attached', timeout: 20000 });
    // Nota própria do teste (não depende do que sobrou na base de teste).
    const noteId = await page.evaluate(async (api) => {
      const form = new FormData();
      form.append('gmailMessageId', `msg-p204-${Date.now()}`);
      form.append('dadosExtracao', JSON.stringify({ emissorNome: 'Brisanet', valorTotal: 10, dataVencimento: '2026-12-10' }));
      form.append('arquivo', new Blob(['%PDF-1.4 teste'], { type: 'application/pdf' }), 'fatura-p204.pdf');
      return (await (await fetch(`${api}/api/notas-recebidas`, { method: 'POST', body: form })).json()).item.id;
    }, API_TEST_URL);
    await page.click('#notasRecebidasAtualizar');
    const card = await abrirNota(page, noteId);
    const venc = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
    await card.locator('[data-role="issuer"]').fill('BRISANET SERVICOS DE TELECOMUNICACOES LTDA');
    await card.locator('[data-role="amount"]').fill('149.90');
    await card.locator('[data-role="due-date"]').fill(venc);
    await card.locator('[data-role="type"]').selectOption('agencia');
    await card.locator('[data-role="location"]').selectOption(local.id);
    await card.locator('[data-action="compare"]').click();
    await card.locator('[data-action="commit"]').waitFor({ timeout: 15000 });
    await card.locator('[data-action="commit"]').click();
    await page.waitForFunction(() => /Provedor .* (atualizado|criado)/.test(document.getElementById('notasRecebidasStatus').textContent), null, { timeout: 20000 });
    const msg = await page.textContent('#notasRecebidasStatus');
    check(results, 'mensagem informa a atualização do provedor', /Brisanet.*atualizado/.test(msg), msg.trim().slice(0, 140));
    await shot(page, 'p204-01-associado');

    const noNavegador = await page.evaluate((id) => {
      const l = JSON.parse(localStorage.getItem('ti_agencias_v1') || '[]').find((x) => x.id === id);
      return l && l.provedores;
    }, local.id);
    const p = (noNavegador || []).find((x) => x.id === 'prov-ui-1');
    check(results, 'navegador: provedor existente atualizado (sem duplicar)', noNavegador.length === 1 && p && p.valor === '149.90' && p.dataVencimento === venc, JSON.stringify(noNavegador));

    // Abrir o local e salvar de novo não pode desfazer a atualização.
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.evaluate((id) => openModal(id), local.id);
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="rede"]'); // formulário em abas
    const linha = await page.evaluate(() => {
      const r = document.querySelector('#provList .dyn-row');
      return { nome: r.querySelector('[data-f="nome"]').value, valor: r.querySelector('[data-f="valor"]').value, dia: r.querySelector('[data-f="diaVencimento"]').value, venc: r.querySelector('[data-f="dataVencimento"]').value, dot: r.querySelector('.dyn-status-dot')?.title || '' };
    });
    check(results, 'tela do local mostra nome, valor, dia e data de vencimento', linha.nome === 'Brisanet' && linha.valor === '149.90' && linha.venc === venc && linha.dia === String(Number(venc.slice(-2))), JSON.stringify(linha));
    check(results, 'indicador do provedor: fatura vence em breve', /vence/i.test(linha.dot), linha.dot);
    await shot(page, 'p204-02-local');
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    await page.waitForTimeout(1500);
    const naApi = await page.evaluate(async ({ api, id }) => (await (await fetch(`${api}/api/locais/item/${id}`)).json()).item.provedores, { api: API_TEST_URL, id: local.id });
    const pa = naApi.find((x) => x.id === 'prov-ui-1');
    check(results, 'API, depois de salvar o local: atualização preservada', pa && pa.valor === '149.90' && pa.dataVencimento === venc, JSON.stringify(pa));
    const alertas = await page.evaluate(async ({ api, id }) => (await (await fetch(`${api}/api/alertas?dias=7&tipo=vencimento`)).json()).items.filter((a) => a.entidadeId === id), { api: API_TEST_URL, id: local.id });
    // Desde a C-05 o alerta do provedor não repete o da nota do mesmo local: vale qualquer um dos dois.
    check(results, 'alerta de vencimento gerado (nota ou provedor, sem duplicar)', alertas.some((a) => ['provedor', 'nota'].includes(a.origem) && a.vencimento === venc) && alertas.filter((a) => a.vencimento === venc).length === 1, JSON.stringify(alertas.map((a) => [a.origem, a.status, a.vencimento])));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'p204-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();

