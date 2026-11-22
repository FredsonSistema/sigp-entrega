// Aba "Painel da IA": métricas da LLM e saúde do banco, com backup pela tela (API de TESTE).
const { launch, shot, check, loginFresh } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  try {
    await loginFresh(page);
    await page.evaluate(() => document.querySelector('.tab[data-view="ia"]').click());
    await page.waitForSelector('#piaIA [data-role="acuracia"]', { timeout: 20000 });
    const textoIA = await page.locator('#piaIA').innerText();
    check(results, 'cartões da LLM: acerto, aprendizado, campos, local, tempo e memória',
      ['Acerto da triagem', 'Aprendizado', 'Campos sem correção', 'Local sugerido', 'Tempo por documento', 'Memória do modelo'].every((t) => textoIA.includes(t)));
    check(results, 'gráfico mensal com 6 meses', await page.locator('#piaIA .pia-bar').count() === 6);
    await page.selectOption('#piaMeses', '3');
    await page.waitForFunction(() => document.querySelectorAll('#piaIA .pia-bar').length === 3, null, { timeout: 15000 });
    check(results, 'trocar o período recalcula', true);
    await page.waitForSelector('#piaBanco [data-role="saude-status"]', { timeout: 15000 });
    await page.locator('#piaBanco [data-action="backup"]').click();
    await page.waitForFunction(() => /criado e verificado/.test(document.getElementById('piaBancoStatus').textContent), null, { timeout: 30000 });
    await page.waitForFunction(() => /há 0(,\d)? h/.test(document.querySelector('#piaBanco [data-role="backup"]')?.innerText || ''), null, { timeout: 15000 });
    const backup = await page.locator('#piaBanco [data-role="backup"]').innerText();
    check(results, 'backup pela tela: criado, verificado e mostrado como recente', /há 0(,\d)? h/.test(backup), backup.replace(/\s+/g, ' '));
    const status = await page.locator('#piaBanco [data-role="saude-status"]').innerText();
    check(results, 'saúde do banco com status', ['OK', 'Atenção'].includes(status.trim()), status);
    await page.locator('#piaBanco [data-action="completo"]').click();
    await page.waitForFunction(() => /verificação completa/.test(document.getElementById('piaBanco').innerText), null, { timeout: 30000 });
    check(results, 'verificação completa do banco', true);
    await shot(page, 'pia-01-painel');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'pia-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
