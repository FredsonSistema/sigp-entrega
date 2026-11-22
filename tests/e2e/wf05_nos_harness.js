// Executa os nós Code novos do WF-05 com entradas simuladas e o Ollama real, sem gravar nada no SIGp.
// Uso: Get-Content tests/e2e/wf05_nos_harness.js -Raw | docker exec -i -e WF05="$(...)" sigp_n8n node
// (o workflow é passado pela variável WF05_JSON lida de /tmp/wf05.json dentro do container).
const fs = require('fs');
const wf = JSON.parse(fs.readFileSync('/tmp/wf05.json', 'utf8'));
const codigo = (nome) => wf.nodes.find((n) => n.name === nome).parameters.jsCode;
const saidas = {};
async function rodar(nome, entrada) {
  const $input = { first: () => ({ json: entrada }), all: () => [{ json: entrada }] };
  const $ = (outro) => ({ first: () => ({ json: saidas[outro] }) });
  const fn = new Function('$input', '$', '$env', `return (async () => {\n${codigo(nome)}\n})();`);
  const r = await fn($input, $, process.env);
  saidas[nome] = r[0] ? r[0].json : undefined;
  return saidas[nome];
}
async function ollama(body) {
  const inicio = Date.now();
  const r = await fetch((process.env.SIGP_OLLAMA_URL || 'http://ollama:11434') + '/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const json = await r.json();
  console.log(`   (Ollama ${((Date.now() - inicio) / 1000).toFixed(1)} s)`);
  return json;
}

(async () => {
  // Saída típica do nó "Escolher texto" para um ciclo fechado (dados FICTÍCIOS).
  const ciclo = (status, valorPago, dataPagamento) => ({
    escopo: 'SIG', status, titulo: `Ciclo fechado · Garagem Exemplo · NF 302500`, referencia: 'nota-ficticia-1',
    textoBase: `Provedor: OPIX INTERNET · Valor lançado: R$ 119,90 · Pago: R$ ${valorPago}\nEmissão 2026-11-01 · Vencimento 2026-11-10 · Pagamento ${dataPagamento}\nFatura: R$ 119,90 · vencimento 2026-11-10`,
    conteudo: 'Texto da regra do sistema.',
    dados: { status, requerValidacao: true, etapa: 'gerente', numero: '302500', localNome: 'Garagem Exemplo', provedor: 'OPIX INTERNET',
      vencimento: '2026-11-10', valorLancado: 119.9, valorPagoAcumulado: Number(String(valorPago).replace(',', '.')), dataPagamento,
      fatura: { valor: 119.9, vencimento: '2026-11-10', emissor: 'OPIX INTERNET' }, parecerIA: { status: 'sem_dados' } },
  });

  for (const [rotulo, entrada] of [
    ['MATCH (3 evidências conferem)', ciclo('MATCH', '119,90', '2026-11-09')],
    ['DIVERGENCIA (pago a menos)', ciclo('DIVERGENCIA', '99,90', '2026-11-12')],
    ['PENDENTE (não vai à LLM)', ciclo('PENDENTE', '0', '')],
  ]) {
    console.log(`\n=== ${rotulo}`);
    const preparado = await rodar('Preparar pedido à LLM (SIG)', entrada);
    console.log(`   vai à LLM: ${preparado.precisaLLM}`);
    if (!preparado.precisaLLM) continue;
    const resposta = await ollama(preparado.ollamaBody);
    const final = await rodar('Juntar análise da LLM', resposta);
    console.log(`   modelo: ${final.modelo} | conclusão: ${final.dados.analiseLLM.conclusao} | discorda: ${final.dados.analiseLLM.discordaDaRegra}`);
    console.log(final.conteudo.split('\n').map((l) => '   | ' + l).join('\n'));
  }

  console.log('\n=== Falha da LLM (resposta inválida): segue com o texto da regra');
  await rodar('Preparar pedido à LLM (SIG)', ciclo('MATCH', '119,90', '2026-11-09'));
  const semLLM = await rodar('Juntar análise da LLM', { error: { message: 'timeout simulado' } });
  console.log(`   analiseLLM: ${JSON.stringify(semLLM.dados.analiseLLM)} | conteúdo mantido: ${semLLM.conteudo === 'Texto da regra do sistema.'}`);

  console.log('\n=== Etapa executiva (gerente validou)');
  const evento = { body: { evento: 'decisao_gerente', dados: {
    decisao: { status: 'VALIDADA', acao: 'validar', usuario: 'gerente.teste', justificativa: '', created_at: new Date().toISOString() },
    analise: { id: 'analise-1', titulo: 'Ciclo fechado · Garagem Exemplo · NF 302500', referencia: 'nota-ficticia-1', conteudo: saidas['Juntar análise da LLM']?.conteudo || 'Ciclo confere.' },
    resumo: ciclo('MATCH', '119,90', '2026-11-09').dados,
  } } };
  const exec = await rodar('Montar etapa executiva', evento);
  const respExec = await ollama(exec.ollamaBody);
  const sie = await rodar('Juntar resumo executivo', respExec);
  console.log(`   escopo: ${sie.escopo} | modelo: ${sie.modelo} | impacto: ${sie.dados.resumoExecutivoLLM.impacto}`);
  console.log(sie.conteudo.split('\n').map((l) => '   | ' + l).join('\n'));

  console.log('\n=== Gerente devolveu: não vai para a SIE');
  const devolvido = await rodar('Montar etapa executiva', { body: { evento: 'decisao_gerente', dados: { decisao: { status: 'DEVOLVIDA' }, analise: {} } } });
  console.log(`   segue para a SIE: ${Boolean(devolvido)}`);
  const outro = await rodar('Montar etapa executiva', { body: { evento: 'conciliacao_atualizada', dados: {} } });
  console.log(`   evento de conciliação no ramo executivo: ${Boolean(outro)} (esperado: false)`);
})().catch((e) => { console.log('ERRO', e.stack); process.exit(1); });
