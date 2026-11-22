// Rede e IPs só com a permissão "Ver rede e IPs": o operador vê "🔒 restrito" na tabela e no formulário, e ao
// salvar o local a rede gravada continua lá (API de TESTE, dados fictícios).
const { launch, shot, check, loginFresh, apiAdmin } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  const REDE = { label: 'MK e2e', ipWireguard: '10.99.0.1' };
  let alvo = null;
  try {
    const todas = (await apiAdmin('/api/locais?tipo=rodoviaria')).json.items;
    alvo = todas[0];
    const comRede = todas.map((l) => (l.id === alvo.id ? { ...l, redes: [REDE] } : l));
    await apiAdmin('/api/locais/rodoviaria', { method: 'PUT', body: JSON.stringify({ items: comRede }) });
    // Operador: grupo padrão sem "rede.ver"
    await loginFresh(page, { usuario: 'operador.e2e', grupo: 'grp-operador', nome: 'Operador e2e' });
    await page.evaluate(() => document.querySelector('.tab[data-view="rv"]').click());
    await page.waitForFunction(() => /restrito/.test(document.getElementById('view_rv')?.textContent || ''), null, { timeout: 20000 });
    check(results, 'tabela mostra "🔒 restrito" para quem não tem a permissão', !(await page.locator('#view_rv').innerText()).includes('10.99.0.1'));
    const vazou = await page.evaluate(() => JSON.stringify(localStorage).includes('10.99.0.1'));
    check(results, 'o IP nem chega ao navegador do operador', !vazou);
    // Abre o local e salva sem mexer nas redes
    await page.evaluate((id) => { const linha = [...document.querySelectorAll('#view_rv tr')].find((tr) => tr.textContent.includes('restrito')); linha?.click(); }, alvo.id);
    await page.waitForFunction(() => /restritos ao seu perfil/.test(document.body.textContent), null, { timeout: 15000 });
    check(results, 'formulário avisa que a rede é restrita (sem campo para editar)', true);
    await shot(page, 'redes-01-operador');
    const depois = (await apiAdmin(`/api/locais/item/${alvo.id}`)).json.item;
    check(results, 'para o administrador a rede continua gravada', JSON.stringify(depois.redes).includes('10.99.0.1'));
    const operador = (await apiAdmin('/api/acesso/usuarios')).json.items.find((u) => u.usuario === 'operador.e2e');
    check(results, 'grupo Operador não tem "Ver rede e IPs" por padrão', !operador.permissoes.includes('rede.ver'));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'redes-erro').catch(() => {});
  } finally {
    if (alvo) {
      const todas = (await apiAdmin('/api/locais?tipo=rodoviaria')).json.items;
      await apiAdmin('/api/locais/rodoviaria', { method: 'PUT', body: JSON.stringify({ items: todas.map((l) => (l.id === alvo.id ? { ...l, redes: alvo.redes || [] } : l)) }) });
    }
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
