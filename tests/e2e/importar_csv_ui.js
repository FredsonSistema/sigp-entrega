// H-01 — Importar CSV de agências pela tela: prévia, importar, gravado na API de TESTE; reimportar não muda nada.
const { API_TEST_URL, launch, shot, check, loginFresh } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  try {
    await loginFresh(page);
    const sufixo = Date.now().toString(36);
    const csv = Buffer.from([
      '\uFEFFNome;Cidade;CEP;Endereço;Número;Vencimento Fatura;Última Visita;Responsáveis;Provedores;Redes;Marcadores;Observações',
      `AG CSV ${sufixo} A;Itabuna;45600000;Rua A;10;;;Ana - (73) 90000-1111;CONECT TELECOM - 7500000010 - venc. dia 10;172.16.99.1;Regional Itabuna | RT;`,
      `AG CSV ${sufixo} B;Ilhéus;;;;;;;CONSULTAR;;CS;`,
    ].join('\r\n'), 'utf8');
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.waitForSelector('#btnImportCSV', { state: 'visible', timeout: 15000 });
    const importar = async () => {
      const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.click('#btnImportCSV')]);
      await chooser.setFiles({ name: 'agencias.csv', mimeType: 'text/csv', buffer: csv });
      await page.waitForSelector('#sigpCsvOverlay table', { timeout: 15000 });
      return page.locator('#sigpCsvOverlay').innerText();
    };
    const previa = await importar();
    check(results, 'prévia mostra 2 para criar e o aviso do CONSULTAR', /2 criar/.test(previa) && /não é nome de provedor/.test(previa), previa.split('\n')[1]);
    await shot(page, 'csv-01-previa');
    await page.click('#sigpCsvOverlay [data-role="csv-importar"]');
    await page.waitForFunction(() => !document.getElementById('sigpCsvOverlay'), null, { timeout: 10000 });
    await page.waitForTimeout(2500);
    const naApi = await page.evaluate(async ({ api, sufixo }) => {
      const r = await (await fetch(`${api}/api/locais`)).json();
      return (r.items || []).filter((l) => l.nome.includes(sufixo)).map((l) => ({ nome: l.nome, prov: (l.provedores || []).map((p) => `${p.nome}|${p.diaVencimento}`), marc: l.marcadores, obs: l.obs }));
    }, { api: API_TEST_URL, sufixo });
    const a = naApi.find((x) => x.nome.endsWith(' A'));
    check(results, 'as 2 agências foram gravadas na API', naApi.length === 2, JSON.stringify(naApi.map((x) => x.nome)));
    check(results, 'provedor com dia de vencimento e marcadores gravados', a && a.prov[0] === 'CONECT TELECOM|10' && (a.marc || []).includes('RT'), JSON.stringify(a));
    const segunda = await importar();
    check(results, 'importar de novo: tudo igual, nada para criar', /0 criar, 0 atualizar, 2 iguais/.test(segunda), segunda.split('\n')[1]);
    await page.click('#sigpCsvOverlay [data-role="csv-cancelar"]');
    await shot(page, 'csv-02-lista');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'csv-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
