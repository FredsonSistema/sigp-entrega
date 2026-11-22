// Escolha do modelo da triagem do Gmail (WF-08): mede, ANTES de escolher, o que cada modelo do Qwen 2.5 acerta e quanto
// demora, com 10 documentos fictícios cujo esperado segue as definições do prompt (n8n/wf08/prompt_classificacao.md).
// O pedido é montado pelo próprio código do nó "Extrair campos e montar pedido à IA" do WF-08 gerado (mesmo prompt, mesmo
// JSON Schema, temperatura 0); só o nome do modelo muda. Os modelos rodam intercalados, documento a documento, para a
// carga da máquina pesar igual; cada modelo é aquecido antes (a partida a frio fica fora da comparação).
// Uso, na raiz:  node tests/n8n/comparar_modelos_triagem.js   (chama o Ollama pelo container sigp_academic_ai)
// Saída: docs/entrega-academica/sqlserver/evidence/parte3/triagem-modelos.json
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, '..', '..');
const SAIDA = process.env.SAIDA || path.join(RAIZ, 'docs', 'entrega-academica', 'sqlserver', 'evidence', 'parte3', 'triagem-modelos.json');
// Variante "corrigido": o schema atual de n8n/wf08 (com maxLength em cada texto) e num_predict = 400.
const SCHEMA_ATUAL = JSON.parse(fs.readFileSync(path.join(RAIZ, 'n8n', 'wf08', 'schema_classificacao.json'), 'utf8'));
const MODELOS = (process.env.MODELOS || 'qwen2.5:0.5b,qwen2.5:1.5b,qwen2.5:3b').split(',');
// Duas variantes: o pedido exatamente como o WF-08 manda hoje (sem limite de resposta) e com num_predict, a proteção
// contra geração sem fim (achada nesta medição: o 1,5B não terminou em 15 min no aquecimento).
const VARIANTES = (process.env.VARIANTES || 'como_hoje,num_predict_512').split(',');
const LIMITE_S = 300; // o mesmo tempo do nó "Classificar com Qwen" do WF-08: depois disso o documento vai para Revisão
const wf = JSON.parse(fs.readFileSync(path.join(RAIZ, 'n8n_workflow_wf08_gmail_inbox.json'), 'utf8'));
const code = wf.nodes.find((n) => n.name === 'Extrair campos e montar pedido à IA').parameters.jsCode;

const CLIENTE = 'ROTA TRANSPORTES RODOVIARIOS LTDA CNPJ 12.345.678/0001-90';
const DOCS = [
  { id: 'T01', descricao: 'Fatura de internet com boleto', remetente: 'faturamento@netfibra-ficticia.com.br', assunto: 'Sua fatura de dezembro chegou',
    arquivo: 'fatura_dezembro.pdf', corpo: 'Segue a fatura do mês.',
    texto: `NETFIBRA TELECOM FICTICIA LTDA CNPJ 98.765.432/0001-10\nFATURA Nº 2026120045\nCliente: ${CLIENTE}\nServiço: Link dedicado 200 Mbps - Agência Centro\nReferência: 01/12/2026 a 31/12/2026\nVencimento: 10/12/2026\nTotal a pagar: R$ 189,90\nBeneficiário: NETFIBRA TELECOM FICTICIA LTDA\nApós o vencimento cobrar multa de 2%`,
    esperado: { tipo: ['boleto_fatura', 'fatura_e_nota'], evento: 'fatura_nova', provedor: 'netfibra', empresa: 'rota', valor: 189.9, vencimento: '2026-12-10' } },
  { id: 'T02', descricao: 'Fatura e nota fiscal (NFCom) no mesmo PDF', remetente: 'cobranca@conecta-alfa-ficticia.com.br', assunto: 'Fatura e NFCom - competência 11/2026',
    arquivo: 'nfcom_fatura.pdf', corpo: '',
    texto: `DOCUMENTO AUXILIAR DA NOTA FISCAL FATURA DE SERVIÇOS DE COMUNICAÇÃO ELETRÔNICA - NFCom\nEmitente: CONECTA ALFA FICTICIA LTDA\nDestinatário: ${CLIENTE}\nNº 000.123.456 Série 1\nPeríodo: 01/11/2026 a 30/11/2026\nLink principal fibra 300 Mbps R$ 450,00\nTOTAL R$ 450,00\nBoleto - Vencimento 15/12/2026 - Valor R$ 450,00`,
    esperado: { tipo: ['fatura_e_nota'], evento: 'fatura_nova', provedor: 'conecta', empresa: 'rota', valor: 450, vencimento: '2026-12-15' } },
  { id: 'T03', descricao: 'Segunda via com novo vencimento', remetente: 'naoresponda@linkgama-ficticia.com.br', assunto: '2ª via da sua fatura',
    arquivo: 'segunda_via.pdf', corpo: 'Conforme solicitado, segue a 2ª via da fatura com novo vencimento.',
    texto: `LINK GAMA FICTICIA S.A.\n2ª VIA DE FATURA\nPagador: ${CLIENTE}\nFatura 7781 - Internet 100 Mbps Garagem Sul\nVencimento original: 05/11/2026  Novo vencimento: 25/11/2026\nValor: R$ 132,40 (com juros de atraso)`,
    esperado: { tipo: ['boleto_fatura'], evento: 'segunda_via', provedor: 'gama', empresa: 'rota', valor: 132.4, vencimento: '2026-11-25' } },
  { id: 'T04', descricao: 'Lembrete de vencimento', remetente: 'avisos@netfibra-ficticia.com.br', assunto: 'Lembrete: sua fatura vence amanhã',
    arquivo: 'lembrete.pdf', corpo: 'Olá! Sua fatura vence amanhã. Evite juros pagando em dia.',
    texto: 'NETFIBRA TELECOM FICTICIA LTDA\nLembrete de vencimento\nSua fatura de internet nº 2026120045 no valor de R$ 189,90 vence em 10/12/2026.\nSe já pagou, desconsidere.',
    esperado: { tipo: ['lembrete'], evento: 'lembrete_vencimento', provedor: 'netfibra', valor: 189.9, vencimento: '2026-12-10' } },
  { id: 'T05', descricao: 'Aviso de atraso com bloqueio', remetente: 'cobranca@veloznet-ficticia.com.br', assunto: 'Débito em aberto - risco de bloqueio',
    arquivo: 'aviso_atraso.pdf', corpo: 'Identificamos fatura em aberto.',
    texto: 'VELOZNET FICTICIA EIRELI\nAVISO DE DÉBITO EM ABERTO\nA fatura 5520 vencida em 20/10/2026, valor R$ 99,90, não consta como paga.\nRegularize em até 5 dias para evitar o bloqueio do serviço de internet.',
    esperado: { tipo: ['lembrete'], evento: 'aviso_atraso', provedor: 'veloz', valor: 99.9 } },
  { id: 'T06', descricao: 'Pagamento confirmado', remetente: 'financeiro@conecta-alfa-ficticia.com.br', assunto: 'Recebemos seu pagamento',
    arquivo: 'comprovante.pdf', corpo: 'Obrigado! Recebemos o pagamento da sua fatura.',
    texto: 'CONECTA ALFA FICTICIA LTDA\nCONFIRMAÇÃO DE PAGAMENTO\nRecebemos o pagamento da fatura 000.123.456 no valor de R$ 450,00 em 14/12/2026.\nObrigado por manter seus pagamentos em dia.',
    esperado: { evento: 'pagamento_confirmado', provedor: 'conecta' } },
  { id: 'T07', descricao: 'Nota de hotel (não é cobrança de internet)', remetente: 'reservas@pousada-ficticia.com.br', assunto: 'Nota fiscal da hospedagem',
    arquivo: 'nota_hotel.pdf', corpo: 'Segue a nota da hospedagem do técnico.',
    texto: `NOTA FISCAL DE SERVIÇO ELETRÔNICA\nPrestador: POUSADA BEIRA MAR FICTICIA LTDA\nTomador: ${CLIENTE}\nDiscriminação: hospedagem de técnico - 3 diárias - Wi-Fi incluso\nValor total: R$ 450,00`,
    esperado: { tipo: ['outro'] } },
  { id: 'T08', descricao: 'NFS-e de internet sem boleto', remetente: 'nfse@linkgama-ficticia.com.br', assunto: 'NFS-e emitida',
    arquivo: 'nfse_internet.pdf', corpo: 'A nota fiscal do serviço foi emitida.',
    texto: `PREFEITURA MUNICIPAL - NOTA FISCAL DE SERVIÇOS ELETRÔNICA - NFS-e Nº 3391\nPrestador: LINK GAMA FICTICIA S.A.\nTomador: ${CLIENTE}\nServiço: provimento de acesso à internet - competência 11/2026\nValor do serviço: R$ 132,40\nDocumento sem valor de cobrança: o boleto é enviado separadamente.`,
    esperado: { tipo: ['nota_fiscal'], evento: 'fatura_nova', provedor: 'gama', empresa: 'rota', valor: 132.4 } },
  { id: 'T09', descricao: 'Conta de energia (outra concessionária, não internet)', remetente: 'fatura@energia-ficticia.com.br', assunto: 'Sua conta de energia',
    arquivo: 'conta_energia.pdf', corpo: '',
    texto: `COMPANHIA DE ENERGIA FICTICIA\nConta de energia elétrica - consumo 1.240 kWh\nCliente: ${CLIENTE}\nVencimento: 18/12/2026  Total: R$ 1.874,33`,
    esperado: { tipo: ['outro'] } },
  { id: 'T10', descricao: 'Boleto de internet com OCR ruidoso', remetente: 'faturas@veloznet-ficticia.com.br', assunto: 'Boleto disponível',
    arquivo: 'boleto_scan.pdf', corpo: 'Seu boleto está disponível.',
    texto: `VEL0ZNET F1CTICIA EIREL1\nBenef1ciário: VELOZNET FICTICIA EIRELI\nPagad0r: ${CLIENTE}\nInternet f1bra 50 Mb - Rodov1ária Norte\nVenc1mento 22/12/2026   Valor d0 d0cumento R$ 89,9O\nN° documento 5577`,
    esperado: { tipo: ['boleto_fatura'], evento: 'fatura_nova', provedor: 'veloz', empresa: 'rota', valor: 89.9, vencimento: '2026-12-22' } },
];

const norm = (s) => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

function pedido(doc, modelo, variante = 'como_hoje') {
  const itens = {
    'Recuperar itens e etiquetas': { json: { remetente: doc.remetente, assunto: doc.assunto, nomeArquivo: doc.arquivo, corpo: doc.corpo }, binary: {} },
    'OCR local': { json: { text: doc.texto } },
    'Classificar com regras do SIGp': { json: { classificacao: {} } },
  };
  // eslint-disable-next-line no-new-func
  const body = new Function('$json', '$', '$env', code)({ exemplos: [] }, (n) => ({ item: itens[n] }), {}).json.ollamaBody;
  if (variante === 'corrigido') return { ...body, format: SCHEMA_ATUAL, options: { ...body.options, num_predict: 400 }, model: modelo, keep_alive: '30m' };
  const options = variante === 'num_predict_512' ? { ...body.options, num_predict: 512 } : body.options;
  return { ...body, options, model: modelo, keep_alive: '30m' };
}

function chamar(body) {
  const py = `import sys,urllib.request as u;r=u.Request('http://ollama:11434/api/chat',data=sys.stdin.buffer.read(),headers={'Content-Type':'application/json'});print(u.urlopen(r,timeout=${LIMITE_S}).read().decode())`;
  const inicio = Date.now();
  let saida;
  try {
    saida = execFileSync('docker', ['exec', '-i', 'sigp_academic_ai', 'python', '-c', py], { input: JSON.stringify(body), encoding: 'utf8', maxBuffer: 1e7 });
  } catch (e) {
    return { ms: Date.now() - inicio, resposta: null, tempo_esgotado: /timed out|TimeoutError/.test(String(e.stderr || e.message)), erro: String(e.stderr || e.message).split('\n').filter(Boolean).pop() };
  }
  const ms = Date.now() - inicio;
  const resp = JSON.parse(saida);
  let r = null;
  try { r = JSON.parse(resp.message.content); } catch { r = null; }
  return { ms, resposta: r, tokens_entrada: resp.prompt_eval_count, tokens_saida: resp.eval_count };
}

function avaliar(doc, r) {
  const e = doc.esperado;
  const campos = {};
  if (!r) return { json_valido: false, campos: { json: false }, acertos: 0, total: 1 };
  if (e.tipo) campos.tipo = e.tipo.includes(r.tipoDocumento);
  if (e.evento) campos.evento = r.evento === e.evento;
  if (e.provedor) campos.provedor = norm(r.provedorNome).includes(e.provedor) && !norm(r.provedorNome).includes('rota');
  if (e.empresa) campos.empresa = norm(r.empresaDestinataria).includes(e.empresa);
  if (e.valor !== undefined) campos.valor = typeof r.valor === 'number' && Math.abs(r.valor - e.valor) < 0.01;
  if (e.vencimento) campos.vencimento = r.vencimento === e.vencimento;
  const v = Object.values(campos);
  return { json_valido: true, campos, acertos: v.filter(Boolean).length, total: v.length };
}

// Erros que importam para o fluxo: fatura de internet lida como "outro" (candidata a ser ignorada se as regras também
// não acharem nada) e documento que não é de internet lido como cobrança (iria para associação, com revisão humana).
function erroGrave(doc, r) {
  if (!r) return 'sem resposta válida (vai para Revisão)';
  const ehCobranca = doc.esperado.tipo && !doc.esperado.tipo.includes('outro');
  if (ehCobranca && r.tipoDocumento === 'outro') return 'cobrança lida como "outro"';
  if (doc.esperado.tipo && doc.esperado.tipo.includes('outro') && r.tipoDocumento !== 'outro') return 'não-cobrança lida como cobrança';
  return null;
}

const tamanhos = {};
try {
  const lista = execFileSync('docker', ['exec', 'sigp_ollama', 'ollama', 'list'], { encoding: 'utf8' });
  for (const l of lista.split('\n').slice(1)) { const c = l.trim().split(/\s{2,}/); if (c[0]) tamanhos[c[0]] = c[2]; }
} catch { /* sem a lista, segue sem o tamanho */ }

const resultado = { executado_em_utc: new Date().toISOString(), metodo: 'pedido do nó do WF-08 (prompt, JSON Schema, temperatura 0); um modelo de cada vez, variantes intercaladas; aquecimento antes; limite de 300 s por pedido como no WF-08', modelos: {}, documentos: DOCS.map((d) => ({ id: d.id, descricao: d.descricao, esperado: d.esperado })) };
// Um modelo de cada vez (o Ollama local mantém só um carregado: intercalar modelos recarregava o modelo a cada pedido e
// misturava o tempo de carga na latência). Dentro do modelo, as duas variantes são intercaladas documento a documento.
for (const m of MODELOS) {
  const configs = VARIANTES.map((v) => ({ chave: `${m} · ${v}`, m, v }));
  for (const c of configs) {
    process.stdout.write(`aquecendo ${c.chave}... `);
    const t = chamar(pedido(DOCS[0], c.m, c.v));
    console.log(`${t.ms} ms${t.tempo_esgotado ? ' (tempo esgotado)' : ''}`);
    resultado.modelos[c.chave] = { modelo: c.m, variante: c.v, tamanho: tamanhos[c.m] || null, aquecimento_ms: t.ms, aquecimento_esgotado: !!t.tempo_esgotado, casos: [] };
  }
  for (const doc of DOCS) {
    for (const { chave, m: modelo, v } of configs) {
      const reg = resultado.modelos[chave];
      if (reg.casos.filter((x) => x.tempo_esgotado).length >= 3) {
        reg.casos.push({ id: doc.id, nao_medido: true, motivo: '3 pedidos anteriores desta configuração estouraram o tempo', acertos: 0, total: 0, campos: {} });
        console.log(`${doc.id} ${chave.padEnd(30)} não medido (3 tempos esgotados antes)`);
        continue;
      }
      const r = chamar(pedido(doc, modelo, v));
      const a = avaliar(doc, r.resposta);
      const grave = erroGrave(doc, r.resposta);
      reg.casos.push({ id: doc.id, ms: r.ms, tempo_esgotado: !!r.tempo_esgotado, tokens_entrada: r.tokens_entrada, tokens_saida: r.tokens_saida, ...a, erro_grave: grave,
        resposta: r.resposta && { tipoDocumento: r.resposta.tipoDocumento, evento: r.resposta.evento, provedorNome: r.resposta.provedorNome,
          empresaDestinataria: r.resposta.empresaDestinataria, valor: r.resposta.valor, vencimento: r.resposta.vencimento, confianca: r.resposta.confianca } });
      console.log(`${doc.id} ${chave.padEnd(30)} ${String(a.acertos).padStart(2)}/${a.total} campos  ${String(r.ms).padStart(6)} ms  ${r.tempo_esgotado ? 'TEMPO ESGOTADO ' : ''}${grave ? 'ERRO GRAVE: ' + grave : ''}`);
    }
  }
}
const pct = (v, p) => { const s = [...v].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.ceil(p * s.length) - 1)]; };
for (const [m, d] of Object.entries(resultado.modelos)) {
  const medidos = d.casos.filter((c) => !c.nao_medido);
  const ms = medidos.map((c) => c.ms);
  const porCampo = {};
  for (const c of d.casos) for (const [k, v] of Object.entries(c.campos)) { porCampo[k] = porCampo[k] || [0, 0]; porCampo[k][1] += 1; if (v) porCampo[k][0] += 1; }
  d.resumo = {
    campos_certos: d.casos.reduce((s, c) => s + c.acertos, 0), campos_total: d.casos.reduce((s, c) => s + c.total, 0),
    por_campo: Object.fromEntries(Object.entries(porCampo).map(([k, [a, t]]) => [k, `${a}/${t}`])),
    medidos: medidos.length, json_valido: d.casos.filter((c) => c.json_valido).length, tempo_esgotado: d.casos.filter((c) => c.tempo_esgotado).length, erros_graves: d.casos.filter((c) => c.erro_grave).map((c) => `${c.id}: ${c.erro_grave}`),
    latencia_ms: { media: Math.round(ms.reduce((s, x) => s + x, 0) / ms.length), mediana: pct(ms, 0.5), p95: pct(ms, 0.95) },
  };
  console.log(`\n${m} (${d.tamanho || '?'}): ${d.resumo.campos_certos}/${d.resumo.campos_total} campos · ${JSON.stringify(d.resumo.por_campo)} · erros graves ${d.resumo.erros_graves.length} · média ${d.resumo.latencia_ms.media} ms, p95 ${d.resumo.latencia_ms.p95} ms`);
}
fs.writeFileSync(SAIDA, JSON.stringify(resultado, null, 2) + '\n');
console.log(`\nResultado: ${SAIDA}`);
