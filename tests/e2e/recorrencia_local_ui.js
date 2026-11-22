// Recorrência pela tela: duas NFS-e do mesmo provedor e mês no mesmo local (a segunda sem número)
// viram uma só nota (atualizada), uma só linha na tela e um aviso; o mês seguinte vira nota nova.
const { API_TEST_URL, launch, shot, check, loginFresh } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  const toasts = [];
  try {
    await loginFresh(page);
    await page.exposeFunction('registrarToast', (t) => toasts.push(t));
    await page.evaluate(() => {
      const original = window.toast;
      window.toast = (msg, ...rest) => { window.registrarToast(String(msg)); return original(msg, ...rest); };
    });
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.evaluate(() => document.getElementById('btnNew').click());
    await page.waitForSelector('#overlay.open');
    const nome = `Agência Recorrência ${Date.now()}`;
    await page.fill('#f_nome', nome);
    await page.fill('#f_cidade', 'Itabuna');

    async function lancarNota(numero, venc, valor, provedor) {
      await page.click('#overlay [data-loc-tab="nf"]'); // formulário em abas
      if (!(await page.locator('#notasFiscaisList .nf-local-row').count())) {
        await page.click('[data-nf-add-for="notasFiscaisList"]');
      }
      // a última linha é a nova (o local novo já abre com uma linha vazia; nos demais casos o teste adiciona uma)
      await page.locator('#notasFiscaisList button', { hasText: 'Nota lançada' }).last().click();
      await page.waitForSelector('#nfLocalEditorOverlay.open');
      const set = (k, v) => page.fill(`#nfLocalEditorFields [data-nf-field="${k}"]`, v);
      await set('numero', numero);
      await set('provedorNome', provedor);
      await set('valor', valor);
      await set('dataEmissao', venc.slice(0, 8) + '01');
      await set('dataVencimento', venc);
      await page.click('#nfLocalEditorForm button[type=submit]');
      await page.waitForFunction(() => !document.getElementById('nfLocalEditorOverlay').classList.contains('open'));
    }

    await lancarNota('302500', '2026-11-10', '119.90', 'OPIX INTERNET');
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    await page.waitForTimeout(3000);
    const id = await page.evaluate((n) => JSON.parse(localStorage.getItem('ti_agencias_v1')).find((l) => l.nome === n).id, nome);

    // Mesmo mês, sem número, outro nome da mesma empresa (o boleto do mesmo mês)
    await page.evaluate((localId) => openModal(localId), id);
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="nf"]'); // formulário em abas
    await page.click('[data-nf-add-for="notasFiscaisList"]');
    await lancarNota('', '2026-11-10', '120.50', 'OPIX SERVICOS DE TECNOLOGIA EIRELI');
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    await page.waitForTimeout(4000);

    const api = await page.evaluate(async ({ base, localId }) => (await (await fetch(`${base}/api/notas/lancadas`)).json()).items.filter((n) => (n.entidade_id || n.entidadeId) === localId), { base: API_TEST_URL, localId: id });
    check(results, 'API: o mês ficou com UMA nota (atualizada, não duplicada)', api.length === 1, JSON.stringify(api.map((n) => [n.numero, n.valor_total, n.data_vencimento])));
    check(results, 'API: número real 302500 mantido e valor substituído', api[0] && api[0].numero === '302500' && Number(api[0].valor_total) === 120.5, JSON.stringify(api[0] && [api[0].numero, api[0].valor_total]));
    const linhas = await page.evaluate((localId) => (JSON.parse(localStorage.getItem('ti_agencias_v1')).find((l) => l.id === localId).notasFiscais || []).filter((r) => r.notaLancada).length, id);
    check(results, 'tela: uma única linha de nota para o mês', linhas === 1, `linhas com nota: ${linhas}`);
    check(results, 'aviso de que a nota do mês foi atualizada', toasts.some((t) => /Nota do mesmo mês já existia/.test(t)), toasts.slice(-3).join(' | '));

    // Mês seguinte: nota nova
    await page.evaluate((localId) => openModal(localId), id);
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="nf"]'); // formulário em abas
    await page.click('[data-nf-add-for="notasFiscaisList"]');
    await lancarNota('', '2026-12-10', '129.90', 'OPIX INTERNET');
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    await page.waitForTimeout(4000);
    const api2 = await page.evaluate(async ({ base, localId }) => (await (await fetch(`${base}/api/notas/lancadas`)).json()).items.filter((n) => (n.entidade_id || n.entidadeId) === localId), { base: API_TEST_URL, localId: id });
    check(results, 'mês seguinte: nota nova (2 notas no local)', api2.length === 2, JSON.stringify(api2.map((n) => n.data_vencimento)));
    const prov = await page.evaluate(async ({ base, localId }) => (await (await fetch(`${base}/api/locais/item/${localId}`)).json()).item.provedores, { base: API_TEST_URL, localId: id });
    check(results, 'provedor: um só, com a fatura de dezembro', prov.length === 1 && prov[0].dataVencimento === '2026-12-10' && prov[0].valor === '129.90', JSON.stringify(prov));
    await page.evaluate((localId) => openModal(localId), id);
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="nf"]'); // formulário em abas
    await shot(page, 'recorrencia-01-local');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'recorrencia-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();

