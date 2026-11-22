// Configurações > E-mail das faturas: lista padrão, adicionar e-mail ou domínio, recusar operador do Gmail, remover,
// salvar no banco (a busca que o WF-08 lê muda), voltar ao padrão, instruções de troca de responsável e perfil sem
// permissão (API de TESTE, endereços fictícios).
const { API_TEST_URL, API_TEST_KEY, launch, shot, check, loginFresh } = require('./lib');
const ROTA = '/api/configuracoes/email-faturas';
const api = (caminho, opcoes = {}) => fetch(`${API_TEST_URL}${caminho}`, {
  ...opcoes, headers: { 'Content-Type': 'application/json', 'X-API-Key': API_TEST_KEY, ...(opcoes.headers || {}) },
}).then((r) => r.json());

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  let padrao = [];
  try {
    padrao = (await api(ROTA)).padrao;
    await api(ROTA, { method: 'PUT', body: JSON.stringify({ remetentes: padrao }) });
    await loginFresh(page);
    await page.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgEmailFaturas'); });
    const box = page.locator('#cfgEmailFaturas');
    await box.locator('[data-ef-salvar]').waitFor({ timeout: 20000 });
    const iniciais = await box.locator('.cfg-alertas-lista li > span:first-child').allInnerTexts();
    check(results, 'mostra os domínios dos provedores', iniciais.length === padrao.length && iniciais.includes('brisanet.com.br'), `${iniciais.length}`);

    for (const ruim of ['a.com.br) OR (label:inbox', 'label:sigp-importado', 'sem-ponto']) {
      await box.locator('#cfgEfNovo').fill(ruim);
      await box.locator('[data-ef-adicionar]').click();
      check(results, `recusa na tela: ${ruim}`, /inválido/.test(await box.locator('[data-ef-status]').innerText()));
    }
    await box.locator('#cfgEfNovo').fill('Teste.Colaborador@Exemplo.com.br, @novo-provedor.net.br');
    await box.locator('#cfgEfNovo').press('Enter');
    const depois = await box.locator('.cfg-alertas-lista li').allInnerTexts();
    check(results, 'adiciona e-mail e domínio em minúsculas, marcados como extra',
      depois.some((t) => /teste\.colaborador@exemplo\.com\.br\s+extra/.test(t)) && depois.some((t) => /^novo-provedor\.net\.br\s+extra/.test(t)));
    await box.locator('[data-ef-remover="0"]').click();
    await box.locator('[data-ef-salvar]').click();
    await page.waitForFunction(() => /Salvo\./.test(document.querySelector('#cfgEmailFaturas [data-ef-status]')?.textContent || ''), null, { timeout: 15000 });
    await box.locator('[data-ef-ajuda] summary').click();
    await shot(page, 'email-faturas-01-salvo');
    const lido = await api(ROTA);
    check(results, 'salvo no banco sem o removido e com os extras', lido.origem === 'tela' && lido.remetentes.length === padrao.length + 1
      && !lido.remetentes.includes(padrao[0]) && lido.remetentes.includes('teste.colaborador@exemplo.com.br'), JSON.stringify(lido.remetentes.slice(-2)));
    check(results, 'a busca que o WF-08 lê já tem o novo remetente',
      /from:\(.*teste\.colaborador@exemplo\.com\.br OR novo-provedor\.net\.br\) subject:/.test(lido.consulta) && !lido.consulta.includes(`from:(${padrao[0]} `));
    check(results, 'tela mostra quem salvou', /Salvo nesta tela por /.test(await box.locator('[data-ef-origem]').innerText()));
    const ajuda = await box.locator('[data-ef-ajuda]').innerText();
    check(results, 'instruções de troca de responsável visíveis', /encaminhamento/.test(ajuda) && /Alertas por e-mail/.test(ajuda) && /Permitir/.test(ajuda));

    await box.locator('[data-ef-padrao]').click();
    await box.locator('[data-ef-salvar]').click();
    await page.waitForFunction(() => /Salvo\./.test(document.querySelector('#cfgEmailFaturas [data-ef-status]')?.textContent || ''), null, { timeout: 15000 });
    const voltou = await api(ROTA);
    check(results, 'voltar ao padrão tira os extras', JSON.stringify(voltou.remetentes) === JSON.stringify(padrao));

    const leitor = await api('/api/acesso/usuarios', { method: 'POST', body: JSON.stringify({ nome: 'Leitor e2e faturas', grupoId: 'grp-leitura' }) });
    const semChave = await fetch(`${API_TEST_URL}${ROTA}`).then((r) => r.status);
    const comLeitor = await fetch(`${API_TEST_URL}${ROTA}`, { headers: { 'X-API-Key': leitor.chave } }).then((r) => r.status);
    check(results, 'sem chave 401 e perfil Leitura 403', semChave === 401 && comLeitor === 403, `${semChave}/${comLeitor}`);
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'email-faturas-erro').catch(() => {});
  } finally {
    if (padrao.length) await api(ROTA, { method: 'PUT', body: JSON.stringify({ remetentes: padrao }) }).catch(() => {});
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
