// Entrada manual em Notas recebidas: envia uma fatura fictícia pela tela, a IA (WF-10) lê como se fosse um e-mail, a
// nota fica sem etiqueta; depois a mesma fatura "chega por e-mail" e vem com o local da entrada manual já selecionado.
// Usa a API de TESTE (5011) apontando para um n8n descartável com o WF-10 (SIGP_N8N_ENTRADA_MANUAL_URL). Dados fictícios.
const path = require('path');
const { API_TEST_URL, OUT_DIR, launch, shot, check, loginFresh, abrirNota, makePdf, apiAdmin } = require('./lib');

(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept());
  const sufixo = Date.now();
  try {
    await loginFresh(page);
    const local = (await apiAdmin('/api/locais/garagem/item', { method: 'POST', body: JSON.stringify({ nome: `Garagem Manual ${sufixo}`, cidade: 'Itabuna' }) })).json.item;
    await page.evaluate((l) => {
      const list = JSON.parse(localStorage.getItem('ti_garagens_v1') || '[]');
      list.push({ ...l, notasFiscais: [] });
      localStorage.setItem('ti_garagens_v1', JSON.stringify(list));
    }, local);
    const pdf = makePdf(['VELOZNET FICTICIA EIRELI', 'FATURA DE SERVICOS DE INTERNET', `Numero da fatura: ${sufixo}`,
      'Servico: Internet fibra 50 Mb', 'Vencimento: 22/12/2026', 'Total a pagar: R$ 89,90'], path.join(OUT_DIR, `manual-${sufixo}.pdf`));
    await page.evaluate(() => document.querySelector('[data-view="notas-recebidas"]').click());
    await page.locator('#notasRecebidasManual').waitFor({ state: 'visible', timeout: 15000 });
    check(results, 'quadro "Adicionar documento" visível para quem associa notas', true);
    await page.locator('#nrManualEnviar').click();
    check(results, 'sem arquivo: pede o PDF ou o XML', /Escolha a fatura/.test(await page.locator('#nrManualStatus').innerText()));
    await page.setInputFiles('#nrManualPdf', pdf);
    await page.fill('#nrManualObs', 'Teste de tela: entregue no balcão');
    await page.locator('#nrManualEnviar').click();
    await page.waitForFunction(() => /Recebido|IA não foi chamada/.test(document.getElementById('nrManualStatus').textContent), null, { timeout: 20000 });
    check(results, 'envio aceito e a IA chamada', /Recebido/.test(await page.locator('#nrManualStatus').innerText()), await page.locator('#nrManualStatus').innerText());
    const criado = (await apiAdmin('/api/notas-recebidas')).json.items.find((i) => i.origemManual && i.nome_arquivo === `manual-${sufixo}.pdf`);
    check(results, 'entrada manual na caixa, sem etiqueta', criado && criado.etiqueta_status === 'SEM_EMAIL', criado && criado.etiqueta_status);
    const badge = await page.locator(`[data-note-id="${criado.id}"] [data-role="manual-badge"]`).innerText().catch(() => '');
    check(results, 'selo "Manual · aguardando a IA" na lista', /aguardando a IA/.test(badge), badge);
    await shot(page, 'manual-01-enviado');
    // Espera o WF-10 (OCR + regras + Qwen) gravar o resultado.
    let lido = null;
    for (let i = 0; i < 40 && !lido; i += 1) {
      await page.waitForTimeout(6000);
      const it = (await apiAdmin('/api/notas-recebidas')).json.items.find((x) => x.id === criado.id);
      if (it && !it.dados.aguardandoIA && it.dados.iaProcessadaEm) lido = it;
    }
    check(results, 'IA leu como e-mail (emissor, valor e vencimento)', lido && /VELOZNET/.test(lido.dados.emissorNome) && Number(lido.dados.valorTotal) === 89.9 && lido.dados.dataVencimento === '2026-12-22',
      lido && `${lido.dados.emissorNome} · ${lido.dados.valorTotal} · ${lido.dados.dataVencimento} · IA ${lido.dados.decisaoIA}`);
    await page.locator('#notasRecebidasAtualizar').click();
    const card = await abrirNota(page, criado.id);
    const aviso = await card.locator('[data-role="manual"]').innerText();
    check(results, 'cartão diz que veio pela tela, com a observação e sem etiqueta', /Enviado pela tela/.test(aviso) && /balcão/.test(aviso) && /sem etiqueta/i.test(aviso));
    check(results, 'campos preenchidos pela leitura', /VELOZNET/.test(await card.locator('[data-role="issuer"]').inputValue()));
    check(results, 'arquivo: "enviado pela tela"', /enviado pela tela/.test(await card.locator('.nr-anexo-meta').innerText()));
    await shot(page, 'manual-02-cartao');
    // Associa a entrada manual à garagem.
    await card.locator('[data-role="type"]').selectOption('garagem');
    await card.locator('[data-role="location"]').selectOption(local.id);
    await card.locator('[data-action="compare"]').click();
    await card.locator('[data-action="commit"]').waitFor({ timeout: 15000 });
    await card.locator('[data-action="commit"]').click();
    await page.waitForFunction(() => /associada/i.test(document.getElementById('notasRecebidasStatus')?.textContent || ''), null, { timeout: 20000 });
    const pend = (await apiAdmin('/api/notas-recebidas?etiquetaPendente=1')).json.items.map((i) => i.id);
    check(results, 'associada e fora da fila de etiquetas do Gmail', !pend.includes(criado.id));
    // A mesma fatura chega por e-mail (como o WF-08 grava).
    const dados = { emissorNome: lido.dados.emissorNome, valorTotal: 89.9, dataVencimento: '2026-12-22', numero: '999999999', decisaoIA: 'importar' };
    const email = await page.evaluate(async ({ api, dados, sufixo }) => {
      const form = new FormData();
      form.append('gmailMessageId', `msg-manual-ui-${sufixo}`); form.append('gmailAttachmentId', 'a1');
      form.append('remetente', 'faturas@veloznet-ficticia.com.br'); form.append('assunto', 'Sua fatura chegou');
      form.append('dadosExtracao', JSON.stringify(dados));
      form.append('arquivo', new Blob(['%PDF-1.4 copia do e-mail'], { type: 'application/pdf' }), 'fatura-email.pdf');
      return (await (await fetch(`${api}/api/notas-recebidas`, { method: 'POST', body: form })).json()).item;
    }, { api: API_TEST_URL, dados, sufixo });
    check(results, 'e-mail ligado à entrada manual', email.correspondenteManual && email.correspondenteManual.id === criado.id, email.correspondenteManual && email.correspondenteManual.motivo);
    await page.locator('#notasRecebidasAtualizar').click();
    const cardEmail = await abrirNota(page, email.id);
    const avisoEmail = await cardEmail.locator('[data-role="manual"]').innerText();
    check(results, 'cartão do e-mail avisa a entrada manual', /adicionada à mão/.test(avisoEmail), avisoEmail.slice(0, 120));
    check(results, 'local da entrada manual já selecionado', await cardEmail.locator('[data-role="location"]').inputValue() === local.id);
    await shot(page, 'manual-03-email');
    check(results, 'navegador não chamou a API real nem o n8n', context.bloqueados.length === 0, context.bloqueados.join(', '));
  } catch (error) {
    check(results, 'execução sem erro', false, error.message);
    await shot(page, 'manual-erro').catch(() => {});
  } finally {
    await browser.close();
    const falhas = results.filter((r) => !r.ok).length;
    console.log(`${results.length - falhas}/${results.length} verificações passaram.`);
    process.exit(falhas ? 1 : 0);
  }
})();
