// Aba Notas recebidas: aviso do valor padrão, emissão opcional e botão Descartar/Restaurar.
const { API_TEST_URL, launch, shot, check, loginFresh, abrirNota } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  try {
    await loginFresh(page);
    // Nota própria do teste (não depende de sobrar nota aguardando associação na base de teste).
    const noteId = await page.evaluate(async (api) => {
      const form = new FormData();
      form.append('gmailMessageId', `msg-descarte-${Date.now()}`);
      form.append('dadosExtracao', JSON.stringify({ emissorNome: 'Provedor Teste Descarte', numero: '4455', valorTotal: 50, dataVencimento: '2026-12-10' }));
      form.append('arquivo', new Blob(['%PDF-1.4 teste'], { type: 'application/pdf' }), 'fatura-descarte.pdf');
      return (await (await fetch(`${api}/api/notas-recebidas`, { method: 'POST', body: form })).json()).item.id;
    }, API_TEST_URL);
    await page.evaluate(() => document.querySelector('[data-view="notas-recebidas"]').click());
    const card = await abrirNota(page, noteId);
    check(results, 'cartão tem o botão "Descartar nota"', await card.locator('[data-action="discard"]').count() === 1);
    check(results, 'emissão deixou de ser obrigatória', !(await card.locator('[data-role="issue-date"]').getAttribute('required')));
    const dica = await card.locator('label:has([data-role="number"]) .nr-tip').getAttribute('title');
    check(results, 'número mostra a regra do valor padrão (ⓘ)', /999999999/.test(dica), dica.trim());
    await card.scrollIntoViewIfNeeded();
    await shot(page, 'nr-01-cartao');

    await card.locator('[data-action="discard"]').click();
    await card.locator('[data-role="discard-reason"]').selectOption('fora_escopo');
    await card.locator('[data-role="discard-detail"]').fill('boleto de hotel');
    await shot(page, 'nr-02-form-descarte');
    await card.locator('[data-action="discard-confirm"]').click();
    await page.waitForFunction((id) => !document.querySelector(`[data-note-id="${id}"]`), noteId, { timeout: 15000 });
    check(results, 'descartada sai da fila "Todos"', true);

    await page.selectOption('#notasRecebidasFiltro', 'DESCARTADA');
    const desc = await abrirNota(page, noteId, 15000);
    const aviso = await desc.locator('[role="note"]').textContent();
    check(results, 'filtro Descartada mostra a nota e o motivo', /Fora do escopo/.test(aviso) && /hotel/.test(aviso), aviso.trim());
    await desc.scrollIntoViewIfNeeded();
    await shot(page, 'nr-03-descartada');
    await desc.locator('[data-action="restore"]').click();
    await page.waitForFunction((id) => !document.querySelector(`[data-note-id="${id}"]`), noteId, { timeout: 15000 });
    check(results, 'restaurar devolve a nota para a caixa', true);
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'nr-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
