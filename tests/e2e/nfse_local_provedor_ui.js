// Regra única pela interface: lançar uma NFS-e no modal da localidade e salvar o local
// preenche o provedor do local (nome, valor, data e dia de vencimento) na tela, no navegador e na API.
const { API_TEST_URL, launch, shot, check, loginFresh } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await loginFresh(page);
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.evaluate(() => document.getElementById('btnNew').click());
    await page.waitForSelector('#overlay.open');
    const nome = `Agência NFS-e ${Date.now()}`;
    await page.fill('#f_nome', nome);
    await page.fill('#f_cidade', 'Itabuna');
    // salva primeiro o local (sem provedor) para ter id
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    const id = await page.evaluate((n) => JSON.parse(localStorage.getItem('ti_agencias_v1')).find((l) => l.nome === n).id, nome);
    await page.evaluate((localId) => openModal(localId), id);
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="nf"]'); // formulário em abas

    // NFS-e na linha de nota do local (modal "Importar NF · Nota lançada"), preenchida à mão
    if (!(await page.locator('#notasFiscaisList button', { hasText: 'Nota lançada' }).count())) {
      await page.click('[data-nf-add-for="notasFiscaisList"]');
    }
    await page.locator('#notasFiscaisList button', { hasText: 'Nota lançada' }).first().click();
    await page.waitForSelector('#nfLocalEditorOverlay.open');
    const venc = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
    const set = (k, v) => page.fill(`#nfLocalEditorFields [data-nf-field="${k}"]`, v);
    await set('numero', String(Date.now()).slice(-7));
    await set('provedorNome', 'OPIX INTERNET LTDA');
    await set('valor', '119.90');
    await set('dataEmissao', '2026-11-01');
    await set('dataVencimento', venc);
    await page.click('#nfLocalEditorForm button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('nfLocalEditorOverlay').classList.contains('open'), null, { timeout: 8000 });
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    await page.waitForTimeout(4000); // sincronização assíncrona das notas + atualização do provedor

    const api = await page.evaluate(async ({ base, localId }) => (await (await fetch(`${base}/api/locais/item/${localId}`)).json()).item.provedores, { base: API_TEST_URL, localId: id });
    const p = api.find((x) => /OPIX/i.test(x.nome || ''));
    check(results, 'API: NFS-e criou o provedor com valor e vencimento', p && p.valor === '119.90' && p.dataVencimento === venc && p.diaVencimento === String(Number(venc.slice(-2))), JSON.stringify(p || api));
    const nav = await page.evaluate((localId) => JSON.parse(localStorage.getItem('ti_agencias_v1')).find((l) => l.id === localId).provedores, id);
    check(results, 'navegador: mesmo provedor no cadastro local', nav.some((x) => /OPIX/i.test(x.nome || '') && x.dataVencimento === venc), JSON.stringify(nav));

    await page.evaluate((localId) => openModal(localId), id);
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="nf"]'); // formulário em abas
    const linha = await page.evaluate(() => [...document.querySelectorAll('#provList .dyn-row')].map((r) => ({
      nome: r.querySelector('[data-f="nome"]').value, valor: r.querySelector('[data-f="valor"]').value, venc: r.querySelector('[data-f="dataVencimento"]').value,
    })));
    check(results, 'tela do local: linha do provedor preenchida sem digitar', linha.some((l) => /OPIX/i.test(l.nome) && l.valor === '119.90' && l.venc === venc), JSON.stringify(linha));
    await shot(page, 'fluxos-01-nfse-local');
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    await page.waitForTimeout(2500);
    const depois = await page.evaluate(async ({ base, localId }) => (await (await fetch(`${base}/api/locais/item/${localId}`)).json()).item.provedores, { base: API_TEST_URL, localId: id });
    check(results, 'salvar o local de novo não desfaz nem duplica', depois.filter((x) => /OPIX/i.test(x.nome || '')).length === 1 && depois.some((x) => x.dataVencimento === venc), JSON.stringify(depois));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'fluxos-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
