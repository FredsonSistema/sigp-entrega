// Notas recebidas em listas: alta probabilidade x inconclusivo x baixa probabilidade (com os ignorados pela IA),
// e-mails em accordion clássico (um aberto por lista) e partes de cada e-mail em disclosure (API de TESTE).
const { API_TEST_URL, launch, shot, check, loginFresh, abrirNota } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  try {
    await loginFresh(page);
    const tag = Date.now();
    const ids = await page.evaluate(async ({ api, tag }) => {
      const criar = async (n, dados) => {
        const form = new FormData();
        form.append('gmailMessageId', `msg-listas-${tag}-${n}`);
        form.append('dadosExtracao', JSON.stringify({ valorTotal: 120, dataVencimento: '2026-12-10', ...dados }));
        form.append('arquivo', new Blob(['%PDF-1.4 teste'], { type: 'application/pdf' }), `${n}.pdf`);
        return (await (await fetch(`${api}/api/notas-recebidas`, { method: 'POST', body: form })).json()).item.id;
      };
      const internet = (nome) => ({
        emissorNome: nome, chave: '29261112345678000199550010000012341000012345', cnpjEmissor: '12.345.678/0001-99',
        classificacao: { categoria: 'FATURA_INTERNET', confianca: 0.9, palavrasInternet: ['fibra'], ia: { tipoDocumento: 'boleto_fatura', confianca: 0.95 } },
      });
      return {
        a: await criar('a', internet(`Fibra Listas A ${tag}`)),
        b: await criar('b', internet(`Fibra Listas B ${tag}`)),
        c: await criar('c', {
          emissorNome: `Software Listas C ${tag}`,
          classificacao: { categoria: 'DOCUMENTO_FISCAL_REVISAO', confianca: 0.52, palavrasFiscais: ['nfse'], ia: { tipoDocumento: 'outro', confianca: 0.9, motivo: 'Locação de software' } },
        }),
        // Parece internet, mas sem valor: inconclusivo.
        d: await criar('d', { ...internet(`Fibra Listas D ${tag}`), valorTotal: null }),
      };
    }, { api: API_TEST_URL, tag });
    await page.evaluate(() => document.querySelector('[data-view="notas-recebidas"]').click());
    await page.waitForFunction((i) => document.querySelector(`#notasRecebidasLista [data-note-id="${i}"]`), ids.c, { timeout: 20000 });
    const grupo = (id) => page.locator(`#notasRecebidasLista [data-note-id="${id}"]`).getAttribute('data-group');
    const grupos = [await grupo(ids.a), await grupo(ids.b), await grupo(ids.c), await grupo(ids.d)];
    check(results, 'três níveis: alta, baixa e inconclusivo (falta valor)', JSON.stringify(grupos) === JSON.stringify(['alta', 'alta', 'baixa', 'inconclusivo']), JSON.stringify(grupos));
    const abertas = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('details.nr-list')].map((d) => [d.dataset.list, d.open])));
    check(results, 'alta e inconclusivo abertas; baixa recolhida', abertas.alta === true && abertas.inconclusivo === true && abertas.baixa === false, JSON.stringify(abertas));
    const a = page.locator(`[data-note-id="${ids.a}"]`);
    const b = page.locator(`[data-note-id="${ids.b}"]`);
    const cabecalho = await a.locator('[data-action="toggle-note"]').innerText();
    check(results, 'cabeçalho do e-mail sem chave nem CNPJ', !/2926111234|12\.345\.678/.test(cabecalho) && /Fibra Listas A/.test(cabecalho), cabecalho.replace(/\s+/g, ' ').slice(0, 120));
    check(results, 'e-mails começam recolhidos', await a.locator('.nr-acc-panel').isHidden() && await a.locator('[data-action="toggle-note"]').getAttribute('aria-expanded') === 'false');
    await a.locator('[data-action="toggle-note"]').click();
    // Nota aberta = modal: dados, local e arquivos visíveis sem expandir nada; "Validar" é o único botão primário, no rodapé.
    const modal = a.locator('.nr-modal');
    const visiveis = await Promise.all(['[data-role="issuer"]', '[data-role="location"]', '.nr-anexo', '.nr-m-rodape [data-action="compare"]']
      .map((sel) => modal.locator(sel).isVisible()));
    check(results, 'ao abrir: modal com dados, local, arquivos e "Validar" no rodapé', visiveis.every(Boolean) && await modal.getAttribute('role') === 'dialog', JSON.stringify(visiveis));
    check(results, 'ações de risco afastadas do botão primário', await modal.locator('.nr-m-rodape-esq [data-action="discard"]').count() === 1
      && await modal.locator('.nr-m-rodape-dir [data-action="discard"]').count() === 0);
    await shot(page, 'nl-01-aberto');
    await page.keyboard.press('Escape');
    check(results, 'Esc fecha o modal', await a.locator('.nr-acc-panel').isHidden());
    await a.locator('[data-action="toggle-note"]').click();
    await a.locator('[data-action="close-note"]').click();
    check(results, '✕ fecha o modal', await a.locator('.nr-acc-panel').isHidden());
    await b.locator('[data-action="toggle-note"]').click();
    check(results, 'abrir B mostra só B', await a.locator('.nr-acc-panel').isHidden() && await b.locator('.nr-acc-panel').isVisible());
    await b.locator('[data-action="toggle-note"]').focus();
    await page.keyboard.press('ArrowUp');
    const focado = await page.evaluate(() => document.activeElement?.closest('[data-note-id]')?.dataset.noteId);
    check(results, 'teclado: seta para cima vai para o e-mail anterior da lista', focado && focado !== ids.b, focado);
    await page.evaluate(() => document.getElementById('notasRecebidasAtualizar').click());
    await page.waitForFunction((i) => { const p = document.querySelector(`[data-note-id="${i}"] .nr-acc-panel`); return p && !p.hidden; }, ids.b, { timeout: 15000 });
    check(results, 'atualizar a lista mantém o e-mail aberto', await b.locator('.nr-acc-panel').isVisible());
    const c = await abrirNota(page, ids.c);
    const motivo = await c.locator('details.nr-disc[data-disc="motivo"]').innerText();
    check(results, '"Por que está nesta lista" mostra o sinal contra (IA)', /não é cobrança de internet \(90%\)/.test(motivo) && /Locação de software/.test(motivo), motivo.replace(/\s+/g, ' ').slice(0, 140));
    check(results, 'selo do e-mail: baixa com a confiança da IA', /Baixa · IA 90%/.test(await c.locator('.nr-m-dir .nr-badge').innerText()));
    check(results, 'abrir outra nota fecha a anterior (um modal por vez)', await b.locator('.nr-acc-panel').isHidden());
    const d = await abrirNota(page, ids.d);
    check(results, 'inconclusivo explica o que falta', /falta: valor/.test(await d.locator('[data-role="nivel-motivo"]').innerText()));
    await c.scrollIntoViewIfNeeded();
    await shot(page, 'nl-02-baixa');
    // Limpeza: descarta as notas do teste (não somem; ficam no filtro Descartada).
    await page.evaluate(async ({ api, ids }) => {
      for (const id of Object.values(ids)) {
        await fetch(`${api}/api/notas-recebidas/${id}/descartar`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ motivo: 'outro', detalhe: 'teste de listas' }) });
      }
    }, { api: API_TEST_URL, ids });
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'nl-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
