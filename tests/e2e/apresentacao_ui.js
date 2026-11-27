// Página da apresentação final (docs/entrega-academica/apresentacao.html): abre sem servidor nem internet, sem erro de
// JavaScript; cada seção desenha o conteúdo; os botões de antes/depois, conjunto e painel trocam o que é mostrado.
const path = require('path');
const { launch, shot, check } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  await page.setViewportSize({ width: 1366, height: 900 });
  const erros = [];
  page.on('pageerror', (e) => erros.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') erros.push(m.text()); });
  const pedidosExternos = [];
  page.on('request', (r) => { if (!r.url().startsWith('file:')) pedidosExternos.push(r.url()); });
  try {
    const arquivo = path.resolve(__dirname, '..', '..', 'docs', 'entrega-academica', 'apresentacao.html');
    await page.goto('file:///' + arquivo.replace(/\\/g, '/'));
    await page.waitForSelector('#kpis .kpi');
    check(results, 'abre sem erro de JavaScript', erros.length === 0, erros.join(' | '));
    check(results, 'não pede nada da internet (funciona offline)', pedidosExternos.length === 0, pedidosExternos.join(' '));
    const secoes = await page.locator('#menu button').evaluateAll((bs) => bs.map((b) => b.dataset.ir));
    const esperadas = ['visao', 'respostas', 'mudancas', 'llm', 'casos', 'rag', 'injecao', 'ft', 'seg', 'otim', 'lat', 'hist'];
  check(results, 'seções no menu (inclui comentários da professora, mudanças e RAG)', secoes.join(',') === esperadas.join(','), secoes.join(','));
    for (const id of secoes) {
      await page.click(`#menu [data-ir="${id}"]`);
      const texto = (await page.locator(`#${id}`).innerText()).trim();
      check(results, `seção ${id} desenhada`, texto.length > 200 && !/undefined|NaN/.test(texto), `${texto.length} caracteres`);
      await page.waitForTimeout(400); // espera a animação de entrada da seção
      await shot(page, `apresentacao-${id}`);
    }
    // Casos: antes x depois muda o acerto
    await page.click('#menu [data-ir="casos"]');
    const depois = await page.locator('#kpiCasos .kpi').first().innerText();
    await page.click('#segCasos [data-v="antes"]');
    const antes = await page.locator('#kpiCasos .kpi').first().innerText();
    check(results, 'casos: troca antes/depois muda o acerto', /16\/16/.test(depois) && /12\/16/.test(antes), `${depois.replace(/\s+/g, ' ')} | ${antes.replace(/\s+/g, ' ')}`);
    await page.click('#tabCasos tr[data-caso="IA-015"]');
    check(results, 'casos: clicar mostra o detalhe do caso', /IA-015/.test(await page.locator('#detalheCaso').innerText()));
    // Fine-tuning: conjunto A x B
    await page.click('#menu [data-ir="ft"]');
    const ftA = await page.locator('#ftAcerto').innerText();
    await page.click('#segFt [data-v="B"]');
    const ftB = await page.locator('#ftAcerto').innerText();
    check(results, 'fine-tuning: troca de conjunto muda as barras', ftA !== ftB && /\/20/.test(ftB), '');
    // Segurança: cada painel abre com conteúdo
    await page.click('#menu [data-ir="seg"]');
    for (const p of ['esc', 'trilha', 'perfis', 'matriz', 'segredos']) {
      await page.click(`#segSeg [data-v="${p}"]`);
      const t = await page.locator('#painelSeg').innerText();
      check(results, `segurança: painel ${p}`, t.length > 80 && !/undefined|NaN/.test(t), `${t.length} caracteres`);
    }
    await shot(page, 'apresentacao-seg-matriz');
    // Histórico: filtro por tipo
    await page.click('#menu [data-ir="hist"]');
    const total = await page.locator('#listaHist details').count();
    await page.click('#filtroHist [data-f="REPROVADO"]');
    const reprovados = await page.locator('#listaHist details').count();
    check(results, 'histórico: filtro por tipo', total >= 20 && reprovados > 0 && reprovados < total, `${reprovados} de ${total}`);
    check(results, 'nenhum erro de JavaScript na navegação', erros.length === 0, erros.join(' | '));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
