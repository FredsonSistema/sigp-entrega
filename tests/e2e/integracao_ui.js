// Configurações > Integração: grupos recolhíveis, balões de ajuda (o que é, para que serve, como configurar,
// onde achar), gravação na configuração única e estado do servidor sem segredos (API de TESTE).
const { API_TEST_URL, launch, shot, check, loginFresh } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await loginFresh(page);
    const env = await page.evaluate(() => window.SIGP_ENV || null);
    check(results, 'padrões da instalação chegam por /sigp-env.js (vindos do .env)', Boolean(env && env.apiUrl && env.n8nUrl), JSON.stringify(env));
    await page.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgIntegracao'); });
    await page.waitForSelector('#cfgIntegracao .cfg-status-row', { timeout: 20000 });
    const grupos = await page.locator('#cfgIntegracao .cfg-cartao-h h2').allInnerTexts();
    check(results, 'cartões: endereços, webhooks do n8n e webhook de contas', grupos.join('|') === 'Endereços|Webhooks do n8n|Webhook de contas de provedores', grupos.join(' | '));
    const campoApi = page.locator('#cfgIntegracao [data-cfg="apiUrl"]');
    check(results, 'endereço da API vem da configuração (a de teste)', await campoApi.inputValue() === API_TEST_URL, await campoApi.inputValue());
    // Balão de ajuda do endereço da API
    const ajuda = page.locator('#cfgIntegracao .cfg-campo', { has: page.locator('[data-cfg="apiUrl"]') }).locator('[data-cfg-help]');
    await ajuda.click();
    const balao = await page.locator(`#${await ajuda.getAttribute('aria-controls')}`).innerText();
    check(results, 'balão com o que é, para que serve, como configurar e onde achar',
      ['O que é:', 'Para que serve:', 'Como configurar:', 'Onde achar:'].every((p) => balao.includes(p)), balao.split('\n')[0]);
    await shot(page, 'int-01-balao');
    await page.keyboard.press('Escape');
    check(results, 'Esc fecha o balão', await ajuda.getAttribute('aria-expanded') === 'false');
    // Webhook: caminho vira URL completa com o endereço do n8n
    await page.locator('#cfgIntegracao [data-cfg="n8nUrl"]').fill('http://n8n.exemplo.local:5678/');
    await page.locator('#cfgIntegracao [data-cfg="webhookNotaLancada"]').fill('nota-lancada-teste');
    await page.locator('#cfgIntegracao [data-cfg-salvar]').click();
    await page.waitForFunction(() => /Integração salva/.test(document.querySelector('#cfgIntegracao [data-cfg-status]')?.textContent || ''), null, { timeout: 15000 });
    const url = await page.evaluate(() => window.SIGP_CONFIG.webhookUrl('webhookNotaLancada'));
    check(results, 'salvar: caminho do webhook vira URL completa (sem barra dupla)', url === 'http://n8n.exemplo.local:5678/webhook/nota-lancada-teste', url);
    check(results, 'endereço inválido é recusado', await page.evaluate(async () => {
      document.querySelector('#cfgIntegracao [data-cfg="apiUrl"]').value = 'api-sem-http';
      document.querySelector('#cfgIntegracao [data-cfg-salvar]').click();
      await new Promise((r) => setTimeout(r, 300));
      return /inválido/.test(document.querySelector('#cfgIntegracao [data-cfg-status]').textContent) && window.SIGP_CONFIG.apiUrl() !== 'api-sem-http';
    }));
    // Estado do servidor: segredo aparece só como definida/não definida
    await page.evaluate(() => window.SIGP_CONFIG_LAYOUT.irPara('#cfgServidor'));
    const servidor = await page.locator('#cfgServidor').innerText();
    const linhaChave = await page.locator('#cfgServidor .cfg-kv-linha', { hasText: 'SIGP_API_KEY' }).first().innerText();
    check(results, 'servidor: SIGP_API_KEY "definida" sem mostrar o valor', /definida/.test(linhaChave) && !servidor.includes('chave-de-teste-e2e'), linhaChave.replace(/\s+/g, ' '));
    await shot(page, 'int-02-servidor');
    // Webhook de contas: bloco antigo preservado dentro do grupo 3, com fila e log
    await page.evaluate(() => window.SIGP_CONFIG_LAYOUT.irPara('#cfgIntegracao'));
    check(results, 'cartão do webhook de contas tem o webhook de contas com fila', await page.locator('#cfgGrupoContas #wh_url').isVisible() && await page.locator('#cfgGrupoContas #wh_filaResumo').isVisible());
    // Restaurar padrões da instalação
    await page.locator('#cfgIntegracao [data-cfg-restaurar]').click();
    await page.waitForFunction(() => /padrões da instalação/.test(document.querySelector('#cfgIntegracao [data-cfg-status]')?.textContent || ''), null, { timeout: 15000 });
    const depois = await page.evaluate(() => [window.SIGP_CONFIG.n8nUrl(), window.SIGP_CONFIG.get('webhookNotaLancada'), (window.SIGP_ENV || {}).n8nUrl]);
    check(results, 'restaurar volta aos padrões da instalação', depois[0] === depois[2] && depois[1] === 'sigp-nota-lancada', JSON.stringify(depois));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'int-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
