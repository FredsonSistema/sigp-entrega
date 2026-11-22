// Situação da conta: selo automático pelos alertas (não é marcador e não fica gravado no local), filtro
// "Situação da conta", some quando o pagamento é confirmado e fica oculto para quem não vê o SIG.
// API de TESTE; dados fictícios criados e removidos aqui.
const { launch, shot, check, loginFresh, apiAdmin } = require('./lib');

const iso = (deslocamento) => { const d = new Date(); d.setDate(d.getDate() + deslocamento); return d.toISOString().slice(0, 10); };

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  const errosJs = [];
  page.on('pageerror', (e) => errosJs.push(e.message));
  const T = `${Date.now() % 1000000}`;
  const VENC = iso(-10);
  const ag = (await apiAdmin('/api/locais?tipo=agencia')).json.items;
  const atrasada = { id: `sc-${T}-1`, nome: `SC E2E Atrasada ${T}`, cidade: 'Cidade SC', provedores: [{ id: 'scp1', nome: 'Provedor SC', valor: '99.90', dataVencimento: VENC }] };
  const emDia = { id: `sc-${T}-2`, nome: `SC E2E Em dia ${T}`, cidade: 'Cidade SC', provedores: [{ id: 'scp2', nome: 'Provedor SC', valor: '50', dataVencimento: iso(30) }] };
  const linhas = async () => page.locator('#tbody tr').allInnerTexts();
  try {
    await apiAdmin('/api/locais/agencia', { method: 'PUT', body: JSON.stringify({ items: [...ag, atrasada, emDia] }) });
    await loginFresh(page);
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.waitForFunction(() => !document.getElementById('filtroSituacao').hidden, null, { timeout: 20000 });
    await page.fill('#search', T); // só as deste teste (sobras de execuções interrompidas não contam)
    await page.waitForFunction((n) => [...document.querySelectorAll('#tbody tr')].some((tr) => tr.textContent.includes(n) && tr.textContent.includes('Vencida')), atrasada.nome, { timeout: 15000 });
    const todas = await linhas();
    check(results, 'selo "Vencida" no local com conta vencida', todas.some((l) => l.includes(atrasada.nome) && l.includes('Vencida')));
    check(results, 'local em dia sem selo', todas.some((l) => l.includes(emDia.nome) && !/Vencida|Vence hoje|A vencer/.test(l)));
    await page.selectOption('#filtroSituacao', 'vencida');
    let filtradas = await linhas();
    check(results, 'filtro "Vencida" mostra só o atrasado', filtradas.length === 1 && filtradas[0].includes(atrasada.nome), filtradas.join(' | ').slice(0, 160));
    await page.selectOption('#filtroSituacao', 'em_dia');
    filtradas = await linhas();
    check(results, 'filtro "Sem pendência" mostra só o em dia', filtradas.length === 1 && filtradas[0].includes(emDia.nome), filtradas.join(' | ').slice(0, 160));
    await page.selectOption('#filtroSituacao', '');
    await shot(page, 'situacao-01-lista');
    const item = (await apiAdmin(`/api/locais/item/${atrasada.id}`)).json.item;
    check(results, 'situação não fica gravada no local', !JSON.stringify(item).includes('Vencida') && !('situacao' in item) && !(item.marcadores || []).length);

    // Pagamento confirmado: a situação some sozinha
    const atual = (await apiAdmin('/api/locais?tipo=agencia')).json.items.map((l) => (l.id === atrasada.id
      ? { ...l, provedores: l.provedores.map((p) => ({ ...p, pagoAte: VENC })) } : l));
    await apiAdmin('/api/locais/agencia', { method: 'PUT', body: JSON.stringify({ items: atual }) });
    await page.evaluate(() => window.SIGP_SITUACAO_CONTA.carregar());
    await page.waitForFunction((n) => [...document.querySelectorAll('#tbody tr')].some((tr) => tr.textContent.includes(n) && !tr.textContent.includes('Vencida')), atrasada.nome, { timeout: 15000 });
    check(results, 'pagamento confirmado tira o selo', true);

    // Sem permissão do SIG: sem selo e sem filtro
    const grupo = (await apiAdmin('/api/acesso/grupos', { method: 'POST', body: JSON.stringify({ nome: `Só locais ${T}`, permissoes: ['locais.ver', 'tela.basico'] }) })).json.item;
    await page.evaluate(() => sessionStorage.clear());
    await loginFresh(page, { usuario: `sc.e2e${T}`, grupo: grupo.id, nome: 'SC e2e' });
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.waitForTimeout(2500);
    check(results, 'sem erro de JavaScript na tela', !errosJs.length, errosJs.join(' | ').slice(0, 200));
    check(results, 'sem permissão do SIG o filtro fica oculto', await page.evaluate(() => document.getElementById('filtroSituacao').hidden));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'situacao-erro').catch(() => {});
  } finally {
    await apiAdmin('/api/locais/agencia', { method: 'PUT', body: JSON.stringify({ items: ag }) }).catch(() => {});
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
