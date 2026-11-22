// Configurações > Alertas por e-mail: adicionar um ou mais e-mails, recusar inválido, remover, salvar no banco
// (lido pelo WF-06) e perfil sem permissão não vê a lista (API de TESTE, e-mails fictícios).
const { API_TEST_URL, API_TEST_KEY, launch, shot, check, loginFresh } = require('./lib');

const api = (caminho, opcoes = {}) => fetch(`${API_TEST_URL}${caminho}`, {
  ...opcoes, headers: { 'Content-Type': 'application/json', 'X-API-Key': API_TEST_KEY, ...(opcoes.headers || {}) },
}).then((r) => r.json());

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await api('/api/configuracoes/alertas', { method: 'PUT', body: JSON.stringify({ emails: [] }) });
    await loginFresh(page);
    await page.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgAlertas'); });
    const box = page.locator('#cfgAlertas');
    await box.locator('[data-alerta-salvar]').waitFor({ timeout: 20000 });
    check(results, 'lista vazia avisa que o resumo não é enviado', /não é enviado|Nenhum e-mail/.test(await box.innerText()));
    await box.locator('#cfgAlertaNovo').fill('sem-arroba.exemplo');
    await box.locator('[data-alerta-adicionar]').click();
    check(results, 'e-mail inválido é recusado na tela', /inválido/.test(await box.locator('[data-alerta-status]').innerText()));
    await box.locator('#cfgAlertaNovo').fill('Contas@Exemplo.com.br, gerente@exemplo.com.br');
    await box.locator('#cfgAlertaNovo').press('Enter');
    await box.locator('#cfgAlertaNovo').fill('terceiro@exemplo.com.br');
    await box.locator('[data-alerta-adicionar]').click();
    const itens = await box.locator('.cfg-alertas-lista li span').allInnerTexts();
    check(results, 'adiciona um ou mais (vírgula, Enter, botão), em minúsculas', itens.join(',') === 'contas@exemplo.com.br,gerente@exemplo.com.br,terceiro@exemplo.com.br', itens.join(','));
    await box.locator('[data-alerta-remover="1"]').click();
    await box.locator('[data-alerta-salvar]').click();
    await page.waitForFunction(() => /Salvo\./.test(document.querySelector('#cfgAlertas [data-alerta-status]')?.textContent || ''), null, { timeout: 15000 });
    await shot(page, 'alertas-01-salvo');
    const lido = await api('/api/configuracoes/alertas');
    check(results, 'salvo no banco (o que o WF-06 lê), sem o removido', lido.emails.join(',') === 'contas@exemplo.com.br,terceiro@exemplo.com.br' && lido.origem === 'tela', JSON.stringify(lido.emails));
    check(results, 'tela mostra quem salvou', /Salvo nesta tela por teste/.test(await box.locator('[data-alerta-origem]').innerText()));
    // Perfil Leitura: não vê nem altera
    const leitor = await api('/api/acesso/usuarios', { method: 'POST', body: JSON.stringify({ nome: 'Leitor e2e alertas', grupoId: 'grp-leitura' }) });
    const semChave = await fetch(`${API_TEST_URL}/api/configuracoes/alertas`).then((r) => r.status);
    const comLeitor = await fetch(`${API_TEST_URL}/api/configuracoes/alertas`, { headers: { 'X-API-Key': leitor.chave } }).then((r) => r.status);
    check(results, 'sem chave 401 e perfil Leitura 403 (e-mail é dado pessoal)', semChave === 401 && comLeitor === 403, `${semChave}/${comLeitor}`);
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'alertas-erro').catch(() => {});
  } finally {
    await api('/api/configuracoes/alertas', { method: 'PUT', body: JSON.stringify({ emails: [] }) }).catch(() => {});
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
