// Topo em menus agrupados e responsáveis com ícones de e-mail e WhatsApp (API de TESTE).
const { launch, shot, check, loginFresh } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  const erros = [];
  page.on('pageerror', (e) => erros.push(e.message));
  try {
    await loginFresh(page);
    const grupos = await page.locator('.topo-linha .menu-btn').allInnerTexts();
    check(results, 'topo com os menus agrupados', ['Cadastros', 'Financeiro', 'Conciliação', 'Operação', 'Análise'].every((g) => grupos.includes(g)), grupos.join(' | '));
    await page.click('.menu-btn:has-text("Conciliação")');
    await page.locator('.menu-grupo.aberto .tab[data-view="sig"]').click();
    await page.waitForFunction(() => document.getElementById('view_sig').style.display !== 'none');
    check(results, 'menu abre a tela e marca o grupo ativo', await page.locator('.menu-grupo.ativo .menu-btn').innerText() === 'Conciliação');
    await page.waitForSelector('.sig-kpis .dash-card', { timeout: 15000 });
    await shot(page, 'topo-01-sig');
    await page.click('.menu-btn:has-text("Cadastros")');
    await page.locator('.menu-grupo.aberto .tab[data-view="agencias"]').click();
    check(results, 'barra da tela (busca, + Nova) na segunda linha', await page.locator('.topo-subbarra #toolbarAgencias #btnNew').isVisible());
    await page.click('#btnNew');
    await page.waitForSelector('#overlay.open');
    await page.click('#overlay [data-loc-tab="resp"]');
    const linha = page.locator('#respList .dyn-row').first();
    const email = linha.locator('button[title="Enviar e-mail"]');
    const whats = linha.locator('button[title="Abrir WhatsApp"]');
    check(results, 'linha do responsável tem ícones de e-mail e WhatsApp', await email.count() === 1 && await whats.count() === 1);
    check(results, 'ícones desativados sem e-mail e telefone', await email.isDisabled() && await whats.isDisabled());
    await linha.locator('[data-f="nome"]').fill('Responsável Teste');
    await linha.locator('[data-f="telefone"]').fill('73999990000');
    await linha.locator('[data-f="email"]').fill('teste@exemplo.com.br');
    check(results, 'ícones ativam ao preencher', await email.isEnabled() && await whats.isEnabled());
    check(results, 'cabeçalho da tabela de responsáveis', /Nome.*Telefone.*E-mail/s.test(await page.locator('#overlay .resp-cab').innerText()));
    await shot(page, 'topo-02-responsaveis');
    await page.click('#btnCancel');
    check(results, 'sem erro de JavaScript', !erros.length, erros.join(' | ').slice(0, 200));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'topo-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
