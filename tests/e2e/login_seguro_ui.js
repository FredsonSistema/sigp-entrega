// Login no servidor: não há "criar usuário" nem "redefinir acesso" na tela; usuário inventado não entra; a chave
// antiga guardada no navegador é apagada e não dá acesso; senha temporária obriga a troca; sair encerra a sessão;
// aba nova pede login; a API recusa leitura sem login (API de TESTE). Substitui o teste antigo da chave (c1).
const { APP_URL, API_TEST_URL, API_TEST_KEY, launch, shot, visible, check, garantirPessoa, entrarComTemporaria } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await garantirPessoa('teste', 'admin');
    // Ataque relatado: chave de administrador guardada no navegador + usuário inventado.
    await page.goto(APP_URL);
    await page.evaluate((k) => {
      localStorage.setItem('sigp_api_key', k);
      localStorage.setItem('sigp_auth', JSON.stringify({ user: 'invasor', hash: 'x' }));
    }, API_TEST_KEY);
    await page.reload();
    await page.waitForSelector('#loginForm', { state: 'visible', timeout: 20000 });
    check(results, 'tela de login sem "criar usuário" nem "redefinir acesso"',
      !(await page.$('#setupForm')) && !(await page.$('#linkReset')) && !(await visible(page, '#primeiroAdminForm')));
    const restos = await page.evaluate(() => [localStorage.getItem('sigp_api_key'), localStorage.getItem('sigp_auth')]);
    check(results, 'chave e usuário antigos do navegador foram apagados', restos[0] === null && restos[1] === null, JSON.stringify(restos));
    const leitura = await page.evaluate(async (api) => (await fetch(`${api}/api/locais`)).status, API_TEST_URL);
    check(results, 'sem login a API recusa até a leitura (401)', leitura === 401, String(leitura));
    await page.fill('#li_user', 'invasor');
    await page.fill('#li_pass', 'qualquer-coisa');
    await page.click('#loginForm button[type=submit]');
    await page.waitForFunction(() => /incorretos/.test(document.getElementById('li_err').textContent), null, { timeout: 15000 });
    check(results, 'usuário inventado não entra (mensagem genérica)', !(await visible(page, '#appRoot')));
    await shot(page, 'login-01-recusado');
    // Senha temporária: troca obrigatória antes de qualquer coisa
    const temporaria = await garantirPessoa('teste', 'admin');
    await page.fill('#li_user', 'teste');
    await page.fill('#li_pass', temporaria);
    await page.click('#loginForm button[type=submit]');
    await page.waitForSelector('#trocaSenhaForm', { state: 'visible', timeout: 15000 });
    check(results, 'senha temporária leva à troca obrigatória, sem botão Cancelar', !(await visible(page, '#ts_cancelar')) && !(await visible(page, '#appRoot')));
    const bloqueada = await page.evaluate(async (api) => {
      const r = await fetch(`${api}/api/locais`);
      return [r.status, (await r.json()).trocarSenha];
    }, API_TEST_URL);
    check(results, 'antes de trocar, a API bloqueia tudo (403 trocarSenha)', bloqueada[0] === 403 && bloqueada[1] === true, bloqueada.join(' · '));
    await page.fill('#ts_atual', temporaria);
    await page.fill('#ts_nova', 'curta');
    await page.fill('#ts_nova2', 'curta');
    await page.click('#trocaSenhaForm button[type=submit]');
    await page.waitForFunction(() => /8 caracteres/.test(document.getElementById('ts_err').textContent), null, { timeout: 15000 });
    check(results, 'senha fraca é recusada com a regra', true);
    await page.fill('#ts_nova', 'Senha-e2e-2026!');
    await page.fill('#ts_nova2', 'Senha-e2e-2026!');
    await page.click('#trocaSenhaForm button[type=submit]');
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#appRoot')).display !== 'none', null, { timeout: 20000 });
    check(results, 'depois da troca, o app abre', true);
    const token = await page.evaluate(() => sessionStorage.getItem('sigp_sessao') || '');
    const naoGuardou = await page.evaluate(() => !Object.keys(localStorage).some((k) => /api_key|auth/.test(k)) && !localStorage.getItem('sigp_sessao'));
    check(results, 'sessão só nesta aba; nada de senha ou chave no localStorage', token.length > 20 && naoGuardou);
    // Aba nova pede login; recarregar a mesma aba mantém
    const outra = await context.newPage();
    await outra.goto(APP_URL);
    await outra.waitForSelector('#loginForm', { state: 'visible', timeout: 20000 });
    check(results, 'aba nova pede login', !(await visible(outra, '#appRoot')));
    await outra.close();
    await page.reload();
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#appRoot')).display !== 'none', null, { timeout: 20000 });
    check(results, 'recarregar a mesma aba continua logado', true);
    // Sair encerra a sessão no servidor
    await page.evaluate(() => document.getElementById('btnLogout').click());
    await page.waitForSelector('#loginForm', { state: 'visible', timeout: 20000 });
    const depois = await fetch(`${API_TEST_URL}/api/locais`, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.status);
    check(results, 'sair encerra a sessão no servidor (token antigo dá 401)', depois === 401, String(depois));
    await shot(page, 'login-02-saiu');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'login-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
