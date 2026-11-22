// Situação 1 pela tela: pagamento confirmado por e-mail (sem anexo) marca a cobrança como paga e aparece em
// "Avisos vinculados a cobranças"; aviso sem cobrança lançada fica em Inconclusivo (API de TESTE).
const { API_TEST_URL, launch, shot, check, loginFresh, abrirNota } = require('./lib');
(async () => {
  const results = [];
  const { browser, context } = await launch();
  const page = await context.newPage();
  try {
    await loginFresh(page);
    const tag = Date.now();
    const r = await page.evaluate(async ({ api, tag }) => {
      const json = (url, body) => fetch(`${api}${url}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((x) => x.json());
      const dominio = `fibra${tag}.example`;
      const local = (await json('/api/locais/agencia/item', { nome: `Agência Aviso ${tag}`, cidade: 'Itabuna' })).item;
      // Provedor com o e-mail cadastrado, pelo mesmo caminho da tela (cadastro do local).
      const lista = JSON.parse(localStorage.getItem('ti_agencias_v1') || '[]');
      lista.push({ ...local, provedores: [{ id: 'p1', nome: `Fibra Aviso ${tag}`, email: dominio, diaVencimento: '15' }] });
      localStorage.setItem('ti_agencias_v1', JSON.stringify(lista));
      await window.SIGP_API.persistLocation('ti_agencias_v1');
      await json('/api/notas/lancadas', { id: `nl-aviso-${tag}`, entidadeTipo: 'agencia', entidadeId: local.id, dados: {
        id: `nl-aviso-${tag}`, numero: `${tag}`.slice(-6), provedorNome: `Fibra Aviso ${tag} LTDA`, localNome: local.nome, localCidade: 'Itabuna',
        valorTotal: 99.9, dataEmissao: '2026-11-01', dataVencimento: '2026-11-15', servicos: [{ descricao: 'Internet', valorTotal: 99.9 }] } });
      const pago = await json('/api/notas-recebidas/aviso', { gmailMessageId: `aviso-pago-${tag}`, assunto: 'Pagamento confirmado',
        corpo: 'Recebemos seu pagamento. Pagamento realizado em 14/11/2026.', remetente: `Fibra <financeiro@${dominio}>`, recebidaEm: '2026-11-14T12:00:00Z' });
      const sem = await json('/api/notas-recebidas/aviso', { gmailMessageId: `aviso-sem-${tag}`, assunto: 'Fatura em atraso',
        corpo: 'Evite o bloqueio do serviço.', remetente: `Outro <cobranca@outro${tag}.example>`, recebidaEm: '2026-11-14T12:00:00Z' });
      return { pago, sem };
    }, { api: API_TEST_URL, tag });
    check(results, 'API: pagamento confirmado registrou o pagamento', r.pago.acao === 'pagamento_registrado', r.pago.acao);
    check(results, 'API: aviso sem cobrança lançada não vincula', r.sem.acao === 'sem_vinculo', r.sem.acao);
    await page.evaluate(() => document.querySelector('[data-view="notas-recebidas"]').click());
    const pago = await abrirNota(page, r.pago.item.id);
    check(results, 'pagamento fica na lista "Avisos vinculados a cobranças"', await pago.getAttribute('data-group') === 'avisos');
    const bloco = await pago.locator('[data-role="aviso"]').innerText();
    check(results, 'tela explica o pagamento automático', /Pagamento registrado automaticamente/.test(bloco) && /14\/11\/2026/.test(bloco), bloco.split('\n')[0]);
    check(results, 'aviso vinculado não oferece associar nem baixar PDF', await pago.locator('[data-action="compare"]').count() === 0
      && await pago.locator('a', { hasText: 'Abrir / imprimir PDF' }).isHidden());
    await pago.scrollIntoViewIfNeeded();
    await shot(page, 'av-01-pago');
    const sem = await abrirNota(page, r.sem.item.id);
    check(results, 'aviso sem cobrança vai para Inconclusivo com o motivo', await sem.getAttribute('data-group') === 'inconclusivo'
      && /Não achei a cobrança/.test(await sem.locator('[data-role="aviso"]').innerText()));
  } catch (error) {
    check(results, 'execução do teste', false, error.message.split('\n')[0]);
    await shot(page, 'av-erro').catch(() => {});
  } finally {
    await browser.close();
  }
  const falhas = results.filter((x) => !x.ok).length;
  console.log(`\n${results.length - falhas}/${results.length} verificações passaram.`);
  process.exit(falhas ? 1 : 0);
})();
