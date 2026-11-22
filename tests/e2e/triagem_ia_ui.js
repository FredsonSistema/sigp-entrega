// Etapa 2 — triagem pela IA: resumo da última leitura, fila "Ignorados pela IA", resgatar e confirmar em lote (API de TESTE).
const { API_TEST_URL, launch, shot, check, loginFresh, abrirNota } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await loginFresh(page);
    const execucao = `exec-ui-${Date.now()}`;
    const ids = await page.evaluate(async ({ api, execucao }) => {
      const criar = async (n, decisao, motivo) => {
        const form = new FormData();
        form.append('gmailMessageId', `${execucao}-${n}`);
        form.append('dadosExtracao', JSON.stringify({
          emissorNome: n === 'c' ? 'Provedor Fibra Teste' : 'Hotel Teste', valorTotal: 10, dataVencimento: '2026-12-10', decisaoIA: decisao,
          triagem: { decisao, execucaoId: execucao, em: new Date().toISOString(), motivo, confianca: 0.91, tipoDocumento: decisao === 'ignorar' ? 'outro' : 'boleto_fatura' },
        }));
        form.append('arquivo', new Blob(['%PDF-1.4 teste'], { type: 'application/pdf' }), `${n}.pdf`);
        return (await (await fetch(`${api}/api/notas-recebidas`, { method: 'POST', body: form })).json()).item.id;
      };
      return { a: await criar('a', 'ignorar', 'Recibo de hotel, não é internet.'), b: await criar('b', 'ignorar', 'Propaganda.'), c: await criar('c', 'importar', 'Boleto de internet.') };
    }, { api: API_TEST_URL, execucao });

    await page.evaluate(() => document.querySelector('[data-view="notas-recebidas"]').click());
    await page.waitForSelector('#notasRecebidasTriagem b', { timeout: 20000 });
    const resumo = await page.locator('#notasRecebidasTriagem').innerText();
    check(results, 'resumo da última leitura: 3 documentos, 1 para a caixa, 2 ignorados', /3 documento\(s\).*1 para a caixa, 2 ignorado/.test(resumo.replace(/\s+/g, ' ')), resumo.trim().slice(0, 140));
    await page.waitForFunction((i) => document.querySelector(`[data-note-id="${i}"]`), ids.a, { timeout: 15000 });
    check(results, '"Todos" mostra os ignorados na lista "Baixa probabilidade", na mesma aba',
      await page.locator(`[data-note-id="${ids.a}"]`).getAttribute('data-group') === 'baixa'
      && await page.locator(`[data-note-id="${ids.c}"]`).count() === 1);
    await shot(page, 'tri-01-resumo');

    await page.locator('#notasRecebidasTriagem [data-action="show-ignored"]').click();
    await abrirNota(page, ids.a, 15000);
    await page.locator(`[data-note-id="${ids.a}"] [data-role="triage"]`).waitFor({ timeout: 15000 });
    const bloco = await page.locator(`[data-note-id="${ids.a}"] [data-role="triage"]`).innerText();
    check(results, 'cartão ignorado mostra o motivo e a confiança da IA', /hotel/i.test(bloco) && /91%/.test(bloco), bloco.split('\n')[0]);
    check(results, 'ignorado não mostra "Validar nota no local"', await page.locator(`[data-note-id="${ids.a}"] [data-action="compare"]`).isHidden());
    await page.locator(`[data-note-id="${ids.a}"]`).scrollIntoViewIfNeeded();
    await shot(page, 'tri-02-ignorados');

    await page.locator(`[data-note-id="${ids.a}"] [data-action="rescue"]`).click();
    await page.waitForFunction((id) => !document.querySelector(`[data-note-id="${id}"]`), ids.a, { timeout: 15000 });
    await page.locator('#notasRecebidasTriagem [data-action="ignore-confirm-all"]').click();
    await page.waitForFunction(() => /confirmado\(s\) como "não é cobrança"/.test(document.getElementById('notasRecebidasStatus').textContent), null, { timeout: 15000 });
    const estados = await page.evaluate(async ({ api, ids }) => {
      const um = async (id) => {
        for (const s of ['AGUARDANDO_ASSOCIACAO', 'DESCARTADA', 'IGNORADA_IA']) {
          const r = await (await fetch(`${api}/api/notas-recebidas?status=${s}`)).json();
          if ((r.items || []).some((i) => i.id === id)) return s;
        }
        return '?';
      };
      return { a: await um(ids.a), b: await um(ids.b) };
    }, { api: API_TEST_URL, ids });
    check(results, 'resgatado volta para a caixa; confirmado vira descartado', estados.a === 'AGUARDANDO_ASSOCIACAO' && estados.b === 'DESCARTADA', JSON.stringify(estados));
    await shot(page, 'tri-03-confirmados');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'tri-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
