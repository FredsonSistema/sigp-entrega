// Situação 2: fatura do mês que não chegou. Exemplo do usuário (vence dia 20, chega 3 dias antes), com "hoje" simulado
// na API de alertas; o cadastro do provedor tem o campo Periodicidade ("Sem fatura por e-mail" desliga o alerta).
const { API_TEST_URL, launch, shot, check, loginFresh } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  try {
    await loginFresh(page);
    const tag = Date.now();
    const local = await page.evaluate(async ({ api, tag }) => {
      const json = (url, body) => fetch(`${api}${url}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((x) => x.json());
      const item = (await json('/api/locais/agencia/item', { nome: `Agência Esperada ${tag}`, cidade: 'Itabuna' })).item;
      const lista = JSON.parse(localStorage.getItem('ti_agencias_v1') || '[]');
      lista.push({ ...item, provedores: [{ id: 'p1', nome: `Netesperada${tag}`, diaVencimento: '20', dataVencimento: '2026-11-20', valor: '150.00' }] });
      localStorage.setItem('ti_agencias_v1', JSON.stringify(lista));
      await window.SIGP_API.persistLocation('ti_agencias_v1');
      return item;
    }, { api: API_TEST_URL, tag });
    const todos = (hoje) => page.evaluate(async ({ api, hoje }) => (await (await fetch(`${api}/api/alertas?hoje=${hoje}&tipo=fatura_nao_recebida`)).json()).items,
      { api: API_TEST_URL, hoje });
    const alertas = async (hoje) => (await todos(hoje)).filter((a) => a.entidadeId === local.id);
    // "Hoje" simulado um mês à frente: a última leitura do Gmail na base de teste fica para trás e a regra de
    // leitura parada age (alerta próprio e os de fatura em severidade baixa). Com leitura recente seria média/alta.
    const antes = await alertas('2026-12-14');
    check(results, 'antes da chegada esperada: sem alerta', antes.length === 0, JSON.stringify(antes));
    const depois = await alertas('2026-12-16');
    check(results, 'depois da chegada esperada: "fatura não chegou" para o vencimento 20/12', depois.length === 1 && depois[0].status === 'FATURA_NAO_RECEBIDA'
      && depois[0].vencimento === '2026-12-20' && depois[0].esperadaEm === '2026-12-15', JSON.stringify(depois.map((a) => [a.status, a.severidade, a.vencimento, a.esperadaEm])));
    const geral = await todos('2026-12-16');
    check(results, 'leitura do Gmail parada: alerta próprio e fatura em severidade baixa',
      geral.some((a) => a.status === 'LEITURA_GMAIL_PARADA') && depois[0].severidade === 'baixa' && /leitura do Gmail está parada/.test(depois[0].mensagem));
    // Cadastro: campo Periodicidade; "Sem fatura por e-mail" desliga o alerta.
    await page.evaluate(() => document.querySelector('.tab[data-view="agencias"]').click());
    await page.evaluate((id) => openModal(id), local.id);
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="rede"]'); // formulário em abas
    const sel = page.locator('#provList .dyn-row select[data-f="periodicidade"]').first();
    check(results, 'cadastro do provedor tem "Periodicidade" (padrão mensal)', await sel.count() === 1 && await sel.inputValue() === '');
    await sel.selectOption('sem_fatura');
    await shot(page, 'fnr-01-periodicidade');
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    await page.waitForTimeout(1500);
    const desligado = await alertas('2026-12-20');
    check(results, '"Sem fatura por e-mail" desliga o alerta', desligado.length === 0, JSON.stringify(desligado.map((a) => a.status)));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'fnr-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
