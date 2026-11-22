// Configurações em páginas: cada página do menu lateral abre, cabe na tela (sem rolagem horizontal) e mostra os
// cartões do desenho novo (Usuários e integrações, Grupos de permissão, Auditoria, API e n8n, Servidor e serviços).
const { launch, shot, check, loginFresh } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await page.setViewportSize({ width: 1366, height: 820 });
    await loginFresh(page);
    await page.evaluate(() => document.querySelector('.tab[data-view="config"]').click());
    await page.waitForSelector('#view_config .cfg-nav-item', { state: 'attached', timeout: 20000 });
    await page.waitForSelector('#cfgUsuarios .cfg-tabela', { state: 'attached', timeout: 20000 });
    await page.waitForSelector('#cfgIntegracao .cfg-status-row', { state: 'attached', timeout: 20000 });
    await page.waitForSelector('#cfgMarcadores .mk-cards', { state: 'attached', timeout: 20000 });
    await page.waitForSelector('#cfgQualidade .cfg-acc', { state: 'attached', timeout: 20000 });
    const itens = await page.locator('#view_config .cfg-nav-item > span:first-child').allInnerTexts();
    const esperados = ['Usuários e integrações', 'Grupos de permissão', 'Auditoria de acesso', 'API e n8n', 'Servidor e serviços'];
    check(results, 'menu tem as páginas de acesso e integrações', esperados.every((e) => itens.includes(e)), itens.join(' | '));
    const ids = await page.locator('#view_config .cfg-nav-item').evaluateAll((bs) => bs.map((b) => b.dataset.cfgPagina));
    const largas = [];
    for (const id of ids) {
      await page.evaluate((i) => window.SIGP_CONFIG_LAYOUT.ir(i), id);
      await page.waitForTimeout(150);
      const m = await page.evaluate(() => {
        const c = document.querySelector('#view_config .cfg-conteudo');
        const pag = document.querySelector('#view_config .cfg-pagina:not([hidden])');
        const r = pag.getBoundingClientRect();
        return { doc: document.documentElement.scrollWidth - document.documentElement.clientWidth, cont: c.scrollWidth - c.clientWidth, dir: Math.round(r.right), janela: window.innerWidth };
      });
      if (m.doc > 1 || m.cont > 1 || m.dir > m.janela) largas.push(`${id}: ${JSON.stringify(m)}`);
      await shot(page, `cfg-pagina-${id}`);
    }
    check(results, 'nenhuma página sai da tela na horizontal', !largas.length, largas.join(' ; ') || `${ids.length} páginas`);
    // Grupos: cabeçalho da matriz não cobre as linhas (fica no topo da própria caixa)
    await page.evaluate(() => window.SIGP_CONFIG_LAYOUT.ir('grupos'));
    const cab = await page.evaluate(() => {
      const th = document.querySelector('#cfgPermissoes .perm-tabela thead th');
      const tw = th.closest('.cfg-tw');
      const linha = document.querySelector('#cfgPermissoes .perm-tabela tbody tr');
      return { th: Math.round(th.getBoundingClientRect().top - tw.getBoundingClientRect().top), sobre: th.getBoundingClientRect().bottom > linha.getBoundingClientRect().top + 1 };
    });
    check(results, 'cabeçalho da matriz no topo da caixa, sem cobrir linhas', cab.th === 0 && !cab.sobre, JSON.stringify(cab));
    check(results, 'grupos em acordeão com seções de permissões', (await page.locator('#cfgPermissoes details.cfg-acc[data-grupo]').count()) >= 4);
    // Usuários: tabela e lista de integrações; contagem no menu
    check(results, 'usuários em tabela', (await page.locator('#cfgUsuarios .cfg-tabela tbody tr[data-usuario]').count()) >= 1);
    check(results, 'integrações em lista com a chave do servidor', /Chave do servidor/.test(await page.locator('#cfgUsuarios .cfg-list').innerText()));
    check(results, 'menu mostra a contagem de usuários', /^\d+$/.test(await page.locator('[data-cfg-n="usuarios"]').innerText()));
    // Auditoria: filtro por resultado
    await page.evaluate(() => window.SIGP_CONFIG_LAYOUT.ir('auditoria'));
    const total = await page.locator('#cfgAuditoria tbody tr').count();
    await page.selectOption('#cfgAuditoria [data-aud-filtro="resultado"]', 'permitido');
    const permitidos = await page.locator('#cfgAuditoria tbody tr').allInnerTexts();
    check(results, 'auditoria filtra por resultado', permitidos.length >= 1 && permitidos.every((t) => /permitido/.test(t)), `${permitidos.length} de ${total}`);
    // API e n8n: quatro cartões de estado; Servidor: variáveis do .env com estado
    check(results, 'API e n8n com quatro cartões de estado', (await page.locator('#cfgIntegracao .cfg-st').count()) === 4);
    const env = await page.locator('#cfgServidor .cfg-kv-linha').allInnerTexts();
    check(results, 'servidor lista as variáveis do .env e do n8n', env.some((t) => /SIGP_API_KEY/.test(t) && /definida/.test(t)) && env.some((t) => /SIGP_OLLAMA_URL/.test(t)), `${env.length} linhas`);
    // Marcadores: cartões com ações em ícone
    await page.evaluate(() => window.SIGP_CONFIG_LAYOUT.ir('marcadores'));
    const grade = await page.evaluate(() => getComputedStyle(document.querySelector('#cfgMarcadores .mk-cards')).gridTemplateColumns.split(' ').length);
    check(results, 'marcadores em duas colunas', grade === 2, String(grade));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'cfg-paginas-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
