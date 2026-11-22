// Configurações > Qualidade do cadastro: prévia, unificar nomes de provedor, dia de vencimento e unidade inválida,
// com backup antes; a cópia do navegador recebe a correção (API de TESTE, dados fictícios criados e removidos aqui).
const { launch, shot, check, loginFresh, apiAdmin } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  const ag = (await apiAdmin('/api/locais?tipo=agencia')).json.items;
  const QC = `QCX${Date.now() % 1000000}`; // nome novo a cada execução (o mapa de nomes unificados é permanente)
  const extras = [
    { id: `qc-${QC}-1`, nome: 'QC E2E Alfa', cidade: 'Cidade QC', provedores: [{ id: 'qcp1', nome: `${QC} LTDA` }] },
    { id: `qc-${QC}-2`, nome: 'QC E2E Beta', cidade: 'Cidade QC', provedores: [{ id: 'qcp2', nome: QC }, { id: 'qcp3', nome: 'Provedor QC Dia' }] },
    { id: `qc-${QC}-3`, nome: 'AGENCIAS', cidade: 'Cidade QC', provedores: [] },
  ];
  try {
    await apiAdmin('/api/locais/agencia', { method: 'PUT', body: JSON.stringify({ items: [...ag, ...extras] }) });
    await loginFresh(page);
    await page.evaluate(() => { document.querySelector('.tab[data-view="config"]').click(); window.SIGP_CONFIG_LAYOUT.irPara('#cfgQualidade'); });
    const box = page.locator('#cfgQualidade');
    await box.locator('.qc-chips').waitFor({ timeout: 20000 });
    check(results, 'resumo da qualidade com contagens', (await box.locator('.qc-chip').count()) >= 3);
    const grupo = box.locator('.qc-grupo', { hasText: QC });
    check(results, 'prévia mostra de → para', (await grupo.innerText()).replace(/\s+/g, ' ').includes(`${QC} LTDA → ${QC}`));
    // Só o grupo QCNET (os outros desmarcados) para não mexer no resto da base de teste
    for (const c of await box.locator('[data-qc-grupo]').all()) {
      const nome = await c.evaluate((el) => el.closest('legend').textContent);
      if (!nome.includes(QC)) await c.uncheck();
    }
    await box.locator('[data-qc-acao="unificar"]').click();
    await page.waitForFunction(() => /Pronto: 1 alteração/.test(document.querySelector('#cfgQualidade [data-qc-status="unificar"]')?.textContent || ''), null, { timeout: 20000 });
    const p1 = (await apiAdmin(`/api/locais/item/qc-${QC}-1`)).json.item.provedores[0].nome;
    check(results, 'unificou na API', p1 === QC, p1);
    const noNavegador = await page.evaluate((id1) => JSON.parse(localStorage.getItem('ti_agencias_v1') || '[]').find((l) => l.id === id1)?.provedores?.[0]?.nome, `qc-${QC}-1`);
    check(results, 'a cópia do navegador recebeu o nome novo (próxima edição não desfaz)', noNavegador === QC, noNavegador);
    // Dia de vencimento
    const dias = box.locator('details[data-qc-sec="dias"]');
    if (!(await dias.evaluate((d) => d.open))) await dias.locator(':scope > summary').click();
    await box.locator(`[data-local="qc-${QC}-2"][data-provedor="qcp3"]`).fill('12');
    await box.locator('[data-qc-acao="dias"]').click();
    await page.waitForFunction(() => /Pronto: 1 alteração/.test(document.querySelector('#cfgQualidade [data-qc-status="dias"]')?.textContent || ''), null, { timeout: 20000 });
    const dia = (await apiAdmin(`/api/locais/item/qc-${QC}-2`)).json.item.provedores.find((p) => p.id === 'qcp3').diaVencimento;
    check(results, 'dia de vencimento salvo', dia === '12', dia);
    // Unidade inválida
    await box.locator(`[data-qc-acao="desativar"][data-local="qc-${QC}-3"]`).click();
    await page.waitForFunction((id) => !document.querySelector(`[data-qc-acao="desativar"][data-local="${id}"]`), `qc-${QC}-3`, { timeout: 20000 });
    const ativa = (await apiAdmin('/api/locais?tipo=agencia')).json.items.some((l) => l.id === `qc-${QC}-3`);
    check(results, 'unidade inválida desativada', !ativa);
    await shot(page, 'qualidade-01');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'qualidade-erro').catch(() => {});
  } finally {
    await apiAdmin('/api/locais/agencia', { method: 'PUT', body: JSON.stringify({ items: ag }) }).catch(() => {});
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
