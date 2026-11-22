// Perfis e permissões: o administrador adiciona uma pessoa (nome, usuário, perfil Leitura) e recebe a senha
// temporária; a pessoa entra, é obrigada a trocar a senha, vê o nome e o perfil, não vê abas sem permissão e a API
// recusa as gravações dela (API de TESTE).
const { API_TEST_URL, launch, shot, check, loginFresh, entrarComTemporaria } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await loginFresh(page);
    await page.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgPermissoes'); });
    await page.waitForSelector('#cfgPermissoes details.cfg-acc[data-grupo]', { timeout: 20000 });
    const paginas = await page.locator('#view_config .cfg-nav-grupo', { hasText: 'Acesso' }).locator('.cfg-nav-item > span:first-child').allInnerTexts();
    check(results, 'três páginas: usuários e integrações, grupos e auditoria', paginas.join('|') === 'Usuários e integrações|Grupos de permissão|Auditoria de acesso', paginas.join(' | '));
    check(results, 'chip mostra o usuário e "Administrador"', (await page.locator('#perfilAtivo').innerText()) === 'teste · Administrador', await page.locator('#perfilAtivo').innerText());
    // Catálogo: todas as funcionalidades com a matriz por grupo
    const linhas = await page.locator('#cfgPermissoes .perm-tabela tbody tr:not(.cfg-tr-area)').count();
    check(results, 'catálogo lista as funcionalidades do sistema (25+)', linhas >= 25, `${linhas} funcionalidades`);
    // Adicionar usuário: só nome, usuário e perfil
    const usuario = `auditoria${Date.now() % 100000000}`;
    const nome = `Auditoria ${usuario.slice(-4)}`;
    await page.evaluate(() => window.SIGP_CONFIG_LAYOUT.irPara('#cfgUsuarios'));
    await page.locator('#cfgUsuarios [data-alterna="novo:usuario"]').first().click();
    await page.fill('#permNovoNome', nome);
    await page.fill('#permNovoUsuario', usuario);
    await page.selectOption('#permNovoGrupo', 'grp-leitura');
    await page.locator('#cfgUsuarios [data-acao="criar-usuario"]').click();
    await page.waitForSelector('#permChaveNova [data-chave]', { timeout: 15000 });
    const temporaria = await page.locator('#permChaveNova [data-chave]').innerText();
    check(results, 'senha temporária aparece uma vez para entregar', /^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$/.test(temporaria), temporaria.replace(/./g, '•'));
    check(results, 'pessoa nova aparece aguardando a troca da senha', /aguardando a troca/.test(await page.locator('#cfgUsuarios tr[data-usuario]', { hasText: nome }).innerText()));
    await shot(page, 'perm-01-admin');
    // Ajuste individual: permitir "Ordens de serviço" só para esta pessoa
    await page.locator('#cfgUsuarios tr[data-usuario]', { hasText: nome }).locator('[data-alterna^="usr:"]').click();
    const linha = page.locator('#cfgUsuarios tr.perm-editor');
    await linha.locator('details.nr-disc', { hasText: 'Ajustes individuais' }).locator(':scope > summary').click();
    await linha.locator('details[data-abre^="aj:"]', { hasText: 'Operação do dia a dia' }).locator(':scope > summary').click();
    await linha.locator('[data-ajuste="os.usar"]').selectOption('permitir');
    await linha.locator('[data-acao="salvar-usuario"]').click();
    await page.waitForFunction(() => /Usuário salvo/.test(document.querySelector('#cfgUsuarios [data-perm-status]')?.textContent || ''), null, { timeout: 15000 });
    check(results, 'ajuste individual salvo', true);
    // A pessoa entra num navegador novo: obrigada a trocar a senha antes de tudo
    const ctx2 = (await launch()).context;
    const p2 = await ctx2.newPage();
    await entrarComTemporaria(p2, usuario, temporaria, 'Minha-senha-forte-1');
    await p2.waitForFunction(() => document.getElementById('perfilAtivo')?.textContent, null, { timeout: 15000 });
    check(results, 'chip mostra o usuário e o perfil', (await p2.locator('#perfilAtivo').innerText()) === `${usuario} · Leitura`, await p2.locator('#perfilAtivo').innerText());
    const abas = await p2.evaluate(() => Object.fromEntries([...document.querySelectorAll('.tab[data-view]')].map((t) => [t.dataset.view, !t.hidden])));
    check(results, 'abas: vê notas e OS (ajuste), não vê agenda pessoal', abas.notas && abas.os && !abas['agenda-pessoal'], JSON.stringify(abas));
    const gravar = await p2.evaluate(async (api) => {
      const r = await fetch(`${api}/api/locais/agencia/item`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nome: 'X', cidade: 'Y' }) });
      return [r.status, (await r.json()).error];
    }, API_TEST_URL);
    check(results, 'API recusa gravação do perfil Leitura com mensagem clara', gravar[0] === 403 && /Leitura/.test(gravar[1]), gravar.join(' · '));
    await p2.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgUsuarios'); });
    await p2.waitForSelector('#cfgUsuarios [data-trocar-senha]', { timeout: 15000 });
    check(results, 'pessoa vê o próprio perfil, sem poder editar', /Só o administrador altera/.test(await p2.locator('#cfgUsuarios').innerText()));
    await shot(p2, 'perm-02-usuario');
    await ctx2.browser().close();
    // Auditoria registra a recusa e o login
    await page.reload();
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#appRoot')).display !== 'none', null, { timeout: 20000 });
    await page.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgAuditoria'); });
    await page.waitForSelector('#cfgAuditoria [data-aud-linhas] tr', { timeout: 20000 });
    const aud = await page.locator('#cfgAuditoria').innerText();
    check(results, 'auditoria mostra o login e a recusa da pessoa', aud.includes(usuario) && /negado \(403\)/.test(aud) && /entrou/.test(aud));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'perm-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
