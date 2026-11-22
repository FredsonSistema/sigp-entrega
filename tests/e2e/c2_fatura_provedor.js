// C2 — "Adicionar fatura PDF" no provedor da localidade, sem exigir nome salvo nem local salvo.
// Fluxo: abre o modal → seleciona PDF → extrai (n8n/OCR) → valida → "Associar ao provedor"
//        → o modal fecha e a linha do provedor recebe nome, valor, dia e data de vencimento.
// Usa a API de TESTE (5011) e o n8n/OCR locais (somente leitura/extração).
const path = require('path');
const { APP_URL, API_TEST_URL, API_TEST_KEY, OUT_DIR, launch, shot, visible, check, loginFresh, makePdf } = require('./lib');

const WEBHOOK = 'http://127.0.0.1:5678/webhook/sigp-faturas-pdf';

(async () => {
  const results = [];
  const pdf = makePdf([
    'FIBRANET TELECOMUNICACOES LTDA',
    'CNPJ: 11.222.333/0001-81',
    'Fatura de servicos de internet',
    'Numero da fatura: 4455667',
    'Data de emissao: 01/12/2026',
    'Vencimento: 12/12/2026',
    'Valor total da fatura: R$ 289,90',
    'Descricao do servico: Link dedicado de internet 300 Mbps',
  ], path.join(OUT_DIR, 'fatura-sintetica-c2.pdf'));

  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  try {
    await loginFresh(page);
    await page.evaluate((url) => localStorage.setItem('sigp_fatura_pdf_webhook_url', url), WEBHOOK);

    // ---- Cenário 1: LOCAL NOVO + PROVEDOR SEM NOME ----
    await page.evaluate(() => document.getElementById('btnNew').click());
    await page.waitForSelector('#overlay.open'); await page.click('#overlay [data-loc-tab="rede"]'); // formulário em abas
    // O local novo já abre com uma linha de provedor vazia (sem precisar clicar em "+ provedor").
    check(results, 'cenário 1: local novo já abre com 1 linha de provedor vazia', (await page.locator('#provList .dyn-row').count()) === 1);
    const anexar = page.locator('#provList .dyn-row-actions button[title^="Anexar"]');
    await anexar.click();
    await page.waitForSelector('#faturaPdfOverlay.open', { timeout: 5000 }).catch(() => {});
    const abriu = await visible(page, '#faturaPdfOverlay.open .modal');
    check(results, 'LOCAL NOVO e provedor sem nome: o modal da fatura abre', abriu);
    await shot(page, 'c2-01-modal-aberto');

    await page.setInputFiles('#faturaPdfFile', pdf);
    await page.click('#faturaPdfExtrair');
    await page.waitForFunction(() => !document.getElementById('faturaPdfReview').hidden, null, { timeout: 180000 });
    const extraido = await page.evaluate(() => ({
      emissor: document.getElementById('faturaPdfEmissor').value,
      numero: document.getElementById('faturaPdfNumero').value,
      venc: document.getElementById('faturaPdfVencimento').value,
      valor: document.getElementById('faturaPdfValor').value,
    }));
    console.log('INFO extração automática:', JSON.stringify(extraido));
    await shot(page, 'c2-02-extraido');
    // O objetivo é testar o fluxo; campos que o OCR não achou são preenchidos como o usuário faria.
    await page.evaluate((fx) => {
      const set = (id, v) => { const el = document.getElementById(id); if (!el.value) { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); } };
      set('faturaPdfEmissor', fx.emissor); set('faturaPdfVencimento', fx.venc); set('faturaPdfValor', fx.valor);
    }, { emissor: 'FIBRANET TELECOMUNICACOES LTDA', venc: '2026-12-12', valor: '289.90' });
    await page.check('#faturaPdfConfirmarEmissor');
    const labelBotao = await page.textContent('#faturaPdfSalvar');
    check(results, 'o botão do modal se chama "Associar ao provedor"', /Associar ao provedor/.test(labelBotao), labelBotao);
    await page.click('#faturaPdfSalvar');
    await page.waitForFunction(() => !document.getElementById('faturaPdfOverlay').classList.contains('open'), null, { timeout: 8000 });
    check(results, 'ao associar, o modal fecha sozinho', true);

    const linha = await page.evaluate(() => {
      const r = document.querySelector('#provList .dyn-row');
      const g = (k) => r.querySelector(`[data-f="${k}"]`).value;
      return { nome: g('nome'), valor: g('valor'), dia: g('diaVencimento'), venc: g('dataVencimento'), fat: r.dataset.faturaAtualId || '' };
    });
    check(results, 'a linha recebeu o NOME do provedor (do emissor)', /FIBRANET/i.test(linha.nome), linha.nome);
    check(results, 'a linha recebeu o VALOR', Number(linha.valor) === 289.9, linha.valor);
    check(results, 'a linha recebeu a DATA de vencimento', linha.venc === '2026-12-12', linha.venc);
    check(results, 'a linha recebeu o DIA do vencimento', linha.dia === '12', linha.dia);
    check(results, 'a fatura ficou pendente (local ainda não salvo)', /^pendente-/.test(linha.fat), linha.fat);
    await shot(page, 'c2-03-linha-preenchida');

    // salva o local → a fatura pendente deve ser enviada à API
    const nomeLocal = 'Agência Teste C2 ' + Date.now();
    await page.fill('#f_nome', nomeLocal);
    await page.fill('#f_cidade', 'Itabuna');
    await page.click('#form button[type=submit]');
    await page.waitForFunction(() => !document.getElementById('overlay').classList.contains('open'), null, { timeout: 15000 });
    await page.waitForTimeout(3000);
    const faturas = await page.evaluate(async ({ api }) => (await (await fetch(`${api}/api/faturas`)).json()).items || [], { api: API_TEST_URL });
    const locais = await page.evaluate(() => JSON.parse(localStorage.getItem('ti_agencias_v1') || '[]'));
    const ag = locais.find((l) => l.nome === nomeLocal);
    const nova = faturas.find((f) => ag && String(f.entidade_id) === String(ag.id));
    check(results, 'ao salvar o local, a fatura PDF foi enviada à API', Boolean(nova), nova ? nova.id : 'não encontrada');
    const prov = ag?.provedores?.[0];
    check(results, 'o local guardou o provedor com nome, valor e vencimento', prov && /FIBRANET/i.test(prov.nome) && prov.dataVencimento === '2026-12-12', JSON.stringify(prov || {}).slice(0, 140));
    check(results, 'a fatura pendente virou o id real da fatura', prov && nova && prov.faturaAtualId === nova.id, prov?.faturaAtualId);
    check(results, 'a fatura está ligada ao local salvo', nova && ag && String(nova.entidade_id) === String(ag.id));

    // ---- Cenário 2: LOCAL SALVO + NOME DIGITADO (sem salvar) ----
    await page.evaluate((id) => {
      const el = document.querySelector(`[data-id="${id}"]`);
      if (el) el.click();
    }, ag?.id);
    const aberto = await page.evaluate((id) => { try { openModal(id); return true; } catch (e) { return String(e); } }, ag?.id);
    await page.waitForSelector('#overlay.open', { timeout: 5000 });
    await page.evaluate(() => document.getElementById('btnAddProv').click());
    const linhas = page.locator('#provList .dyn-row');
    const ultimo = linhas.nth((await linhas.count()) - 1);
    await ultimo.locator('[data-f="nome"]').fill('Provedor Digitado Agora');
    await ultimo.locator('button[title^="Anexar"]').click();
    await page.waitForSelector('#faturaPdfOverlay.open', { timeout: 5000 }).catch(() => {});
    const titulo = await page.textContent('#faturaPdfTitle');
    check(results, 'NOME digitado e não salvo: o modal abre (sem exigir salvar e reabrir)', /Provedor Digitado Agora/.test(titulo), titulo);
    check(results, 'o provedor esperado vem do nome digitado', (await page.inputValue('#faturaPdfProvedorEsperado')) === 'Provedor Digitado Agora');
    await shot(page, 'c2-04-nome-digitado');
    await page.click('#faturaPdfCancelar');

    // 💰 sem dia de vencimento: avisa em vez de sumir
    await ultimo.locator('button[title^="Marcar como pago"]').click();
    const toastTxt = await page.evaluate(() => (document.getElementById('toast') || {}).textContent || '');
    check(results, 'botão 💰 sempre presente; sem dia de vencimento avisa o motivo', /dia de vencimento/i.test(toastTxt), toastTxt);
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'c2-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();


