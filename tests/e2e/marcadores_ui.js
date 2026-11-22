// Marcadores e grupos: Configurações (criar grupo com prévia, renomear e excluir marcador), formulário do local
// (adicionar marcador), pílulas e filtro na lista. API de TESTE; dados fictícios criados e removidos aqui.
const { launch, shot, check, loginFresh, apiAdmin } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  const T = `${Date.now() % 1000000}`;
  const REG = `MK${T} Regional`;
  const NET = `MKNET${T}`;
  const ag = (await apiAdmin('/api/locais?tipo=agencia')).json.items;
  const extras = [
    { id: `mk-${T}-1`, nome: `MK E2E Alfa ${T}`, cidade: 'Cidade MK', provedores: [{ id: 'mkp1', nome: NET }], marcadores: [] },
    { id: `mk-${T}-2`, nome: `MK E2E Beta ${T}`, cidade: 'Cidade MK', provedores: [{ id: 'mkp2', nome: 'Vox' }], marcadores: [REG] },
  ];
  const catalogo = async () => (await apiAdmin('/api/marcadores')).json.items;
  const local = async (id) => (await apiAdmin(`/api/locais/item/${id}`)).json.item;
  try {
    await apiAdmin('/api/locais/agencia', { method: 'PUT', body: JSON.stringify({ items: [...ag, ...extras] }) });
    await loginFresh(page);
    await page.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgMarcadores'); });
    const box = page.locator('#cfgMarcadores');
    const cartaoReg = box.locator('.mk-card', { hasText: REG });
    await cartaoReg.waitFor({ timeout: 20000 });
    check(results, 'marcador do local aparece no catálogo com 1 local', (await cartaoReg.innerText()).includes('1 local'));
    check(results, 'siglas das empresas com descrição', (await box.locator('.mk-card', { hasText: 'Rota Transportes' }).count()) === 1);

    // Grupo pela regra do cadastro, com prévia antes de salvar
    await box.locator('[data-mk-acao="novo-grupo"]').click();
    await box.locator('[data-mk-campo-form="nome"]').fill(`Grupo ${T}`);
    await box.locator('[data-mk-valores="0"]').fill(NET);
    await page.waitForFunction(() => /Prévia: 1 local/.test(document.querySelector('#cfgMarcadores [data-mk-previa]')?.textContent || ''), null, { timeout: 15000 });
    check(results, 'prévia do grupo mostra 1 local', true);
    await box.locator('[data-mk-acao="salvar"]').click();
    await box.locator('.mk-card', { hasText: `Grupo ${T}` }).waitFor({ timeout: 15000 });
    const grupo = (await catalogo()).find((m) => m.nome === `Grupo ${T}`);
    check(results, 'grupo salvo com o local do provedor', grupo && grupo.membros.map((m) => m.id).join() === `mk-${T}-1`, JSON.stringify(grupo && grupo.membros));
    await shot(page, 'marcadores-01-config');

    // Lista de agências: filtro por grupo e pílulas
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.waitForFunction((v) => [...document.querySelectorAll('#filtroMarcador option')].some((o) => o.value === v), `g:${grupo.id}`, { timeout: 15000 });
    await page.selectOption('#filtroMarcador', `g:${grupo.id}`);
    const linhas = await page.locator('#tbody tr').allInnerTexts();
    check(results, 'filtro por grupo mostra só o local do grupo', linhas.length === 1 && linhas[0].includes(`MK E2E Alfa ${T}`), linhas.join(' | ').slice(0, 200));
    check(results, 'pílula do grupo na lista', linhas[0] && linhas[0].includes(`Grupo ${T}`));
    await page.selectOption('#filtroMarcador', '');
    await page.fill('#search', `MK E2E Beta ${T}`);
    check(results, 'pílula do marcador na lista', (await page.locator('#tbody tr').first().innerText()).includes(REG));
    await shot(page, 'marcadores-02-lista');

    // Formulário do local: adicionar marcador (apelido vira a sigla do catálogo)
    await page.evaluate((id) => openModal(id), `mk-${T}-2`);
    const editor = page.locator('#marcList');
    await editor.locator('[data-mk-novo]').fill('Rota');
    await editor.locator('[data-mk-novo]').press('Enter');
    await editor.locator('[data-mk-novo]').fill(`MK${T} Novo`);
    await editor.locator('[data-mk-adicionar]').click();
    check(results, 'apelido "Rota" vira RT no formulário', (await editor.innerText()).includes('RT'));
    await shot(page, 'marcadores-03-form');
    await page.evaluate(() => document.querySelector('#form button[type="submit"]').click());
    let marc = [];
    for (let i = 0; i < 30 && marc.length !== 3; i += 1) {
      await page.waitForTimeout(500);
      marc = (await local(`mk-${T}-2`)).marcadores || [];
    }
    check(results, 'marcadores salvos na API', JSON.stringify(marc) === JSON.stringify([REG, 'RT', `MK${T} Novo`]), JSON.stringify(marc));
    check(results, 'marcador novo entrou no catálogo', (await catalogo()).some((m) => m.nome === `MK${T} Novo`));

    // Renomear e excluir no catálogo valem para o local (API e cópia do navegador)
    await page.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgMarcadores'); });
    await box.locator('.mk-card', { hasText: REG }).locator('[data-mk-acao="editar"]').click();
    await box.locator('[data-mk-campo-form="nome"]').fill(`${REG} Sul`);
    await box.locator('[data-mk-acao="salvar"]').click();
    await box.locator('.mk-card', { hasText: `${REG} Sul` }).waitFor({ timeout: 15000 });
    await box.locator('.mk-card', { hasText: `MK${T} Novo` }).locator('[data-mk-acao="excluir"]').click();
    await page.waitForFunction((n) => ![...document.querySelectorAll('#cfgMarcadores .mk-card')].some((c) => c.textContent.includes(n)), `MK${T} Novo`, { timeout: 15000 });
    const depois = (await local(`mk-${T}-2`)).marcadores;
    check(results, 'renomear e excluir valem no local (API)', JSON.stringify(depois) === JSON.stringify([`${REG} Sul`, 'RT']), JSON.stringify(depois));
    const noNavegador = await page.evaluate((id) => JSON.parse(localStorage.getItem('ti_agencias_v1') || '[]').find((l) => l.id === id)?.marcadores, `mk-${T}-2`);
    check(results, 'a cópia do navegador recebeu a troca (próxima edição não desfaz)', JSON.stringify(noNavegador) === JSON.stringify([`${REG} Sul`, 'RT']), JSON.stringify(noNavegador));
    await shot(page, 'marcadores-04-renomeado');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'marcadores-erro').catch(() => {});
  } finally {
    await apiAdmin('/api/locais/agencia', { method: 'PUT', body: JSON.stringify({ items: ag }) }).catch(() => {});
    for (const m of await catalogo().catch(() => [])) {
      if (m.nome.includes(T)) await apiAdmin(`/api/marcadores/${m.id}`, { method: 'DELETE' }).catch(() => {});
    }
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
