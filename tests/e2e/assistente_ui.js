// Aba Assistente (estilo chat): conversas à esquerda, conversa no centro, artefatos à direita; continuação da
// conversa; relatório PDF e Excel no painel; histórico reabre; treino com 👍 e termo novo (API de TESTE).
const fs = require('fs');
const { launch, shot, check, loginFresh } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  page.on('dialog', (d) => d.accept(''));
  const respostas = () => page.locator('#view_assistente .chat-ia .chat-texto');
  const esperar = async (n) => page.waitForFunction((qtd) => document.querySelectorAll('#view_assistente .chat-ia .chat-texto').length >= qtd
    && !document.querySelector('#view_assistente [aria-busy="true"]'), n, { timeout: 180000 });
  const perguntar = async (texto) => { await page.fill('#chatPergunta', texto); await page.press('#chatPergunta', 'Enter'); };
  try {
    await loginFresh(page);
    await page.evaluate(() => document.querySelector('.tab[data-view="assistente"]').click());
    await page.waitForSelector('#view_assistente .chat-boas-vindas', { timeout: 20000 });
    check(results, 'três colunas: conversas, conversa e artefatos', await page.locator('#view_assistente .chat-lateral').isVisible()
      && await page.locator('#view_assistente .chat-centro').isVisible() && await page.locator('#view_assistente .chat-painel').isVisible());
    check(results, 'tela inicial com "Como posso ajudar?" e sugestões', (await page.locator('.chat-sugestao').count()) >= 4);
    await page.locator('.chat-sugestao', { hasText: 'Quantas agências estão em atraso?' }).click();
    await esperar(1);
    check(results, 'resposta com os números do sistema', /Hoje, \d{2}\/\d{2}\/\d{4}, (nenhuma|\d+ agência)/.test(await respostas().last().innerText()));
    check(results, 'conversa nova aparece na lista com o título da pergunta',
      (await page.locator('.chat-conv.ativa .chat-conv-abrir').innerText()).startsWith('Quantas agências estão em atraso?'));
    const temTabela = await page.locator('.chat-art-tabela tbody tr').count();
    check(results, 'tabela vai para o painel de artefatos, fora da conversa', temTabela > 1, `${temTabela} linhas`);
    await page.locator('.chat-ia [data-util="1"]').last().click();
    await page.waitForSelector('text=👍 aprovado', { timeout: 15000 });
    check(results, '👍 marca como aprovado', true);
    await perguntar('e as rodoviárias?');
    await esperar(2);
    check(results, 'continuação da conversa ("e as rodoviárias?")', /continuação da conversa/.test(await page.locator('.chat-ia .chat-rodape').last().innerText())
      && /rodoviária|nenhuma/.test(await respostas().last().innerText()));
    await perguntar('crie um relatório com a lista de agências');
    await esperar(3);
    check(results, 'relatório abre no painel com PDF e Excel', await page.locator('.chat-art-acoes a', { hasText: 'PDF' }).isVisible()
      && await page.locator('.chat-art-acoes a', { hasText: 'Excel' }).isVisible());
    check(results, 'painel com abas dos artefatos da conversa', (await page.locator('.chat-art-abas [role="tab"]').count()) >= 2);
    const [download] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }), page.locator('.chat-art-acoes a', { hasText: 'Excel' }).click()]);
    check(results, 'Excel (CSV) baixa com a sessão', fs.readFileSync(await download.path(), 'utf8').startsWith('\ufeffTipo;Nome;Cidade;Endereço'));
    await shot(page, 'assistente-01-conversa');
    // Nova conversa e histórico
    const primeira = await page.locator('.chat-conv.ativa .chat-conv-abrir').getAttribute('data-abrir');
    await page.locator('[data-nova]').click();
    await page.waitForSelector('#view_assistente .chat-boas-vindas', { timeout: 10000 });
    await page.locator(`[data-abrir="${primeira}"]`).click();
    await page.waitForFunction(() => document.querySelectorAll('#view_assistente .chat-ia .chat-texto').length === 3, null, { timeout: 15000 });
    check(results, 'histórico: reabre a conversa com as 3 respostas', true);
    // Divisórias arrastáveis
    const largura = (sel) => page.locator(sel).evaluate((el) => Math.round(el.getBoundingClientRect().width));
    const antesEsq = await largura('.chat-lateral');
    const antesDir = await largura('.chat-painel');
    const divEsq = await page.locator('[data-divisor="esq"]').boundingBox();
    await page.mouse.move(divEsq.x + 3, divEsq.y + 200);
    await page.mouse.down();
    await page.mouse.move(divEsq.x + 83, divEsq.y + 200, { steps: 6 });
    await page.mouse.up();
    const depoisEsq = await largura('.chat-lateral');
    check(results, 'arrastar a divisória alarga a lista de conversas', depoisEsq - antesEsq >= 60, `${antesEsq} → ${depoisEsq} px`);
    const divDir = await page.locator('[data-divisor="dir"]').boundingBox();
    await page.mouse.move(divDir.x + 3, divDir.y + 200);
    await page.mouse.down();
    await page.mouse.move(divDir.x - 97, divDir.y + 200, { steps: 6 });
    await page.mouse.up();
    const depoisDir = await largura('.chat-painel');
    check(results, 'arrastar a outra divisória alarga os artefatos', depoisDir - antesDir >= 60, `${antesDir} → ${depoisDir} px`);
    check(results, 'a conversa nunca fica estreita demais', (await largura('.chat-centro')) >= 320);
    await page.locator('[data-divisor="esq"]').focus();
    await page.keyboard.press('ArrowLeft');
    check(results, 'teclado: seta move a divisória (16 px)', (await largura('.chat-lateral')) === depoisEsq - 16);
    await page.reload();
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#appRoot')).display !== 'none', null, { timeout: 20000 });
    await page.evaluate(() => document.querySelector('.tab[data-view="assistente"]').click());
    await page.waitForSelector('#view_assistente .chat-lateral', { timeout: 20000 });
    const recarregada = await largura('.chat-lateral');
    check(results, 'larguras ficam guardadas depois de recarregar', Math.abs(recarregada - (depoisEsq - 16)) <= 2, `esperado ${depoisEsq - 16}, obtido ${recarregada} · ${await page.evaluate(() => localStorage.getItem('sigp_assistente_larguras_v1'))}`);
    await page.locator('[data-recolher]').click();
    check(results, 'recolher a lista: a conversa ocupa o espaço', !(await page.locator('.chat-lateral').isVisible()) && (await largura('.chat-centro')) > 500);
    await page.locator('[data-lateral]').click();
    await page.locator('[data-divisor="esq"]').dblclick();
    check(results, 'mostrar de novo e dois cliques voltam ao padrão (260 px)', (await largura('.chat-lateral')) === 260);
    await page.locator(`[data-abrir="${primeira}"]`).click();
    await page.waitForFunction(() => document.querySelectorAll('#view_assistente .chat-ia .chat-texto').length === 3, null, { timeout: 15000 });
    await shot(page, 'assistente-03-divisorias');
    // Treinar
    await page.locator('[data-treinar]').click();
    await page.waitForSelector('.chat-treino .chat-numeros', { timeout: 15000 });
    check(results, 'treino mostra números do histórico e exportação do dataset', /aprovadas/.test(await page.locator('.chat-numeros').innerText())
      && await page.locator('.chat-treino a', { hasText: 'dataset' }).isVisible());
    await page.fill('#chatTermo', 'em débito');
    await page.fill('#chatSignifica', 'vencida');
    await page.locator('#chatTermoForm button[type=submit]').click();
    await page.waitForFunction(() => /Aprendido/.test(document.getElementById('chatTermoStatus')?.textContent || ''), null, { timeout: 15000 });
    check(results, 'ensinar termo pelo painel de treino', true);
    await shot(page, 'assistente-02-treino');
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'assistente-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
