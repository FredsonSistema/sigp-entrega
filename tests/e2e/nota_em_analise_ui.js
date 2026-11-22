// Aba Notas recebidas: "Deixar em análise" grava o status, aparece no filtro próprio e volta para a fila (API de TESTE).
const { API_TEST_URL, launch, shot, check, loginFresh, abrirNota } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  try {
    await loginFresh(page);
    // Nota própria do teste (a base de teste não depende de sobrar nota aguardando associação).
    const noteId = await page.evaluate(async (api) => {
      const form = new FormData();
      form.append('gmailMessageId', `msg-analise-${Date.now()}`);
      form.append('dadosExtracao', JSON.stringify({ emissorNome: 'Provedor Teste Análise', valorTotal: 99.9, dataVencimento: '2026-12-10' }));
      form.append('arquivo', new Blob(['%PDF-1.4 teste'], { type: 'application/pdf' }), 'fatura-analise.pdf');
      return (await (await fetch(`${api}/api/notas-recebidas`, { method: 'POST', body: form })).json()).item.id;
    }, API_TEST_URL);
    await page.evaluate(() => document.querySelector('[data-view="notas-recebidas"]').click());
    await page.selectOption('#notasRecebidasFiltro', 'AGUARDANDO_ASSOCIACAO');
    const card = await abrirNota(page, noteId);
    check(results, 'botão "Deixar em análise" no lugar de "Manter na caixa"',
      await card.locator('[data-action="analysis"]').count() === 1 && !/Manter na caixa/.test(await card.innerText()));
    check(results, 'formulário fica oculto até clicar', await card.locator('[data-role="analysis-form"]').isHidden());
    await card.locator('[data-action="analysis"]').click();
    await card.locator('[data-role="analysis-note"]').fill('confirmar o local com o gerente');
    await card.scrollIntoViewIfNeeded();
    await shot(page, 'ea-01-form');
    await card.locator('[data-action="analysis-confirm"]').click();
    await page.waitForFunction((id) => !document.querySelector(`[data-note-id="${id}"]`), noteId, { timeout: 15000 });
    check(results, 'sai do filtro "Aguardando associação"', true);

    await page.selectOption('#notasRecebidasFiltro', 'EM_ANALISE');
    const emAnalise = await abrirNota(page, noteId, 15000);
    const texto = await emAnalise.innerText();
    check(results, 'filtro "Em análise" mostra a nota com a observação', /Em análise desde/.test(texto) && /gerente/.test(texto), texto.split('\n')[0]);
    check(results, 'em análise ainda pode ser associada ou descartada',
      await emAnalise.locator('[data-action="compare"]').count() === 1 && await emAnalise.locator('[data-action="discard"]').count() === 1);
    await emAnalise.scrollIntoViewIfNeeded();
    await shot(page, 'ea-02-em-analise');

    // Recarregar a página mantém o status (antes, "Manter na caixa" não gravava nada).
    await page.reload();
    // Logo após recarregar, a tela ainda pode estar iniciando: clica de novo até a aba abrir.
    for (let tentativa = 0; tentativa < 10; tentativa += 1) {
      await page.evaluate(() => document.querySelector('.tab[data-view="notas-recebidas"]').click());
      if (await page.locator('#notasRecebidasFiltro').isVisible()) break;
      await page.waitForTimeout(1000);
    }
    await page.waitForSelector('#notasRecebidasFiltro', { state: 'visible', timeout: 10000 });
    await page.selectOption('#notasRecebidasFiltro', 'EM_ANALISE');
    await abrirNota(page, noteId);
    check(results, 'status continua após recarregar a página', true);

    await page.locator(`[data-note-id="${noteId}"] [data-action="release"]`).click();
    await page.waitForFunction((id) => !document.querySelector(`[data-note-id="${id}"]`), noteId, { timeout: 15000 });
    await page.selectOption('#notasRecebidasFiltro', 'AGUARDANDO_ASSOCIACAO');
    await abrirNota(page, noteId, 15000);
    check(results, '"Voltar para a fila" devolve a nota para Aguardando associação', true);
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'ea-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
