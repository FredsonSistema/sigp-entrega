// Biblioteca do WF-06 (alertas diários com texto amigável). build_wf06.py copia este arquivo para os nós Code.
// Ideia: o SIGp calcula os fatos; a LLM local só escreve a ABERTURA do e-mail; o código confere a abertura
// (números, datas, links, afirmações de pagamento) e, se algo não bater, usa o texto padrão. A lista de contas
// abaixo da abertura vem sempre direto da API, sem passar pela LLM.

const NOMES_STATUS = {
  VENCIDO: 'Vencidas', VENCE_HOJE: 'Vencem hoje', VENCE_EM_BREVE: 'Vencem em breve',
  DIVERGENCIA: 'Divergências', AGUARDANDO_FATURA: 'Aguardando fatura', FATURA_AUSENTE: 'Fatura não disponível',
  PAGO_COM_ATRASO: 'Pagas com atraso', PAGO: 'Pagas no prazo',
  LEITURA_GMAIL_PARADA: 'Leitura do Gmail parada', FATURA_NAO_RECEBIDA: 'Faturas que não chegaram',
  FATURA_NA_CAIXA: 'Faturas na caixa sem associar',
};
const ORDEM_STATUS = ['LEITURA_GMAIL_PARADA', 'VENCIDO', 'VENCE_HOJE', 'FATURA_NAO_RECEBIDA', 'VENCE_EM_BREVE', 'DIVERGENCIA',
  'FATURA_NA_CAIXA', 'PAGO_COM_ATRASO', 'AGUARDANDO_FATURA', 'FATURA_AUSENTE', 'PAGO'];
const STATUS_VENCIMENTO = ['VENCIDO', 'VENCE_HOJE', 'VENCE_EM_BREVE'];
const MAX_DESTAQUES = 5;
const MAX_POR_GRUPO = 20;

function formatarBRL(valor) {
  const n = Number(valor);
  if (!Number.isFinite(n) || n <= 0) return null;
  const [inteiro, centavos] = n.toFixed(2).split('.');
  return `${inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${centavos}`;
}

function dataBR(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
  return m ? `${m[3]}/${m[2]}/${m[1]}` : null;
}

function situacaoDoItem(a) {
  const venc = dataBR(a.vencimento) || 'data não informada';
  const d = Math.abs(Number(a.dias) || 0);
  if (a.status === 'VENCIDO') return `vencida em ${venc}, há ${d} ${d === 1 ? 'dia' : 'dias'}`;
  if (a.status === 'VENCE_HOJE') return `vence hoje (${venc})`;
  return `vence em ${venc}, daqui a ${d} ${d === 1 ? 'dia' : 'dias'}`;
}

// Fatos do dia a partir de GET /api/alertas. Sem alertas: null (nada é enviado).
function montarFatos(resposta) {
  const r = resposta || {};
  const itens = Array.isArray(r.items) ? r.items : [];
  if (!itens.length) return null;
  const contagem = {};
  for (const a of itens) contagem[a.status] = (contagem[a.status] || 0) + 1;
  const grupos = ORDEM_STATUS.filter((s) => contagem[s]).map((s) => ({ status: s, nome: NOMES_STATUS[s], qtd: contagem[s] }));
  for (const s of Object.keys(contagem)) {
    if (!ORDEM_STATUS.includes(s)) grupos.push({ status: s, nome: s, qtd: contagem[s] });
  }
  // A API já ordena por severidade e prazo; os destaques são as primeiras contas com vencimento.
  const destaques = itens.filter((a) => STATUS_VENCIMENTO.includes(a.status)).slice(0, MAX_DESTAQUES).map((a) => ({
    local: String(a.local || 'Local não informado').slice(0, 80),
    provedor: String(a.provedor || 'provedor não informado').slice(0, 60),
    status: a.status,
    valor: formatarBRL(a.valor),
    vencimento: dataBR(a.vencimento),
    dias: Math.abs(Number(a.dias) || 0),
    situacao: situacaoDoItem(a),
  }));
  return { hoje: r.hoje, hojeBR: dataBR(r.hoje) || String(r.hoje || ''), total: itens.length, grupos, destaques, itens };
}

// Frase das quantidades por situação, montada pelo SIGp (a LLM só copia): "22 contas vencidas e 1 conta paga com atraso".
const FRASE_STATUS = {
  VENCIDO: ['conta vencida', 'contas vencidas'],
  VENCE_HOJE: ['conta que vence hoje', 'contas que vencem hoje'],
  VENCE_EM_BREVE: ['conta que vence nos próximos dias', 'contas que vencem nos próximos dias'],
  PAGO_COM_ATRASO: ['conta paga com atraso', 'contas pagas com atraso'],
  PAGO: ['conta paga no prazo', 'contas pagas no prazo'],
  FATURA_NAO_RECEBIDA: ['fatura que não chegou', 'faturas que não chegaram'],
  FATURA_NA_CAIXA: ['fatura na caixa sem associar', 'faturas na caixa sem associar'],
  DIVERGENCIA: ['divergência', 'divergências'],
};
function fraseQuantidades(f) {
  const partes = f.grupos.map((g) => {
    const fr = FRASE_STATUS[g.status];
    return fr ? `${g.qtd} ${g.qtd === 1 ? fr[0] : fr[1]}` : `${g.nome.toLowerCase()}: ${g.qtd}`;
  });
  return partes.length > 1 ? `${partes.slice(0, -1).join(', ')} e ${partes[partes.length - 1]}` : partes[0];
}

function montarPedidoLLM(fatos, prompt, schema, modelo) {
  return {
    model: modelo || 'qwen2.5:3b',
    stream: false,
    options: { temperature: 0.3, num_ctx: 4096, num_predict: 220 },
    format: schema,
    messages: [
      { role: 'system', content: prompt },
      { role: 'user', content: `TEXTO BASE (correto):\n${textoModelo(fatos)}` },
    ],
  };
}

// Abertura padrão, usada quando a da LLM falta ou não passa na conferência.
function textoModelo(f) {
  let texto = `Bom dia! Passando para atualizar as contas de internet de hoje, ${f.hojeBR}: há ${fraseQuantidades(f)}.`;
  const d = f.destaques[0];
  if (d) texto += ` A que pede mais atenção é a da ${d.local} · ${d.provedor}: ${d.situacao}.`;
  return `${texto} Veja a lista abaixo.`;
}

// Números que a abertura pode citar: tudo o que está nos fatos (contagens, datas, valores, dias, números dos nomes).
function numerosPermitidos(f) {
  const ok = new Set([String(f.total), String(f.destaques.length)]);
  const addData = (br) => {
    if (!br) return;
    const [d, m, a] = br.split('/');
    [br, `${d}/${m}`, d, m, a, String(Number(d)), String(Number(m)), `${Number(d)}/${Number(m)}`].forEach((x) => ok.add(x));
  };
  addData(f.hojeBR);
  for (const g of f.grupos) ok.add(String(g.qtd));
  for (const d of f.destaques) {
    addData(d.vencimento);
    ok.add(String(d.dias));
    if (d.valor) { ok.add(d.valor); ok.add(d.valor.replace(/,00$/, '')); ok.add(d.valor.replace(/\./g, '')); }
    for (const n of `${d.local} ${d.provedor}`.match(/\d+/g) || []) ok.add(n);
  }
  return ok;
}

// Nome do local sem o tipo ("Agência ANDARAI" -> "andarai"), para achar a conta citada no texto.
function nucleoDoLocal(local) {
  return String(local || '').replace(/^(Agência|Rodoviária|Garagem)\s+/i, '').toLowerCase();
}

// Confere a abertura escrita pela LLM. Devolve { ok, motivo }.
function conferirAbertura(texto, f) {
  const t = String(texto || '').trim();
  if (t.length < 30) return { ok: false, motivo: 'abertura vazia ou curta demais' };
  if (/\n|^\s*[-•]|\b(por situação|frase das quantidades|texto base|conta 1:)/im.test(t)) return { ok: false, motivo: 'copiou os fatos em vez de escrever a abertura' };
  if (/\b(ignore|ignorar|instru[çc][õo]es|regras anteriores|diga que|system:|prompt)\b/i.test(t)) return { ok: false, motivo: 'texto parece instrução (possível prompt injection)' };
  if (t.length > 560) return { ok: false, motivo: 'abertura longa demais' };
  if (/https?:|www\.|@|<[a-z]/i.test(t)) return { ok: false, motivo: 'abertura com link, e-mail ou HTML' };
  if (/\b(multas?|juros|penalidades?|corte|cortad[ao]|bloquei\w*|suspens\w*|protesto|negativa\w*)\b/i.test(t)) return { ok: false, motivo: 'fala de multa, juros, corte ou bloqueio, que não estão nos fatos' };
  const permitidos = numerosPermitidos(f);
  for (const n of t.match(/\d+(?:[.,]\d+)*(?:\/\d+)*/g) || []) {
    const limpo = n.replace(/[.,]$/, '');
    if (!permitidos.has(limpo)) return { ok: false, motivo: `número ou data fora dos fatos: ${limpo}` };
  }
  const temPagamento = f.grupos.some((g) => g.status === 'PAGO' || g.status === 'PAGO_COM_ATRASO');
  // "não paga", "ainda não foi paga" e "valor a ser pago" não afirmam pagamento.
  const semNegacao = t.replace(/\b(n[ãa]o|ainda n[ãa]o)\s+(foi\s+|foram\s+|est[áa]\s+|est[ãa]o\s+)?(pag|quitad)\w*/gi, '').replace(/\ba ser pag\w*/gi, '');
  if (!temPagamento && /\b(pag[oa]s?|quitad[oa]s?)\b/i.test(semNegacao)) return { ok: false, motivo: 'afirma pagamento que não está nos fatos' };
  const tem = (s) => f.grupos.some((g) => g.status === s);
  // A situação precisa bater: "vencida" só se houver vencida; "atraso" só se houver vencida ou paga com atraso.
  if (!tem('VENCIDO') && /\bvencid[ao]s?\b|\bj[aá] venceu|\bvenceram\b/i.test(t)) return { ok: false, motivo: 'chama de vencida uma conta que não venceu' };
  if (!tem('VENCIDO') && !tem('PAGO_COM_ATRASO') && /atras/i.test(t)) return { ok: false, motivo: 'fala de atraso que não está nos fatos' };
  if (!tem('VENCE_HOJE') && /vence(m)? hoje|vencendo hoje/i.test(t)) return { ok: false, motivo: 'diz que vence hoje sem conta vencendo hoje' };
  if (tem('VENCIDO') && !/vencid|venceu|venceram|atras/i.test(t)) return { ok: false, motivo: 'não menciona as contas vencidas' };
  // Generalização errada ("todas as contas estão vencidas") quando há mais de uma situação.
  if (/\b(tod[ao]s\s+(as\s+|os\s+)?(outr[ao]s\s+|demais\s+)?(contas?|faturas?)|tod[ao]s\s+(est[ãa]o|venc)|nenhuma\s+(outra\s+)?conta|as\s+demais\s+(contas\s+)?est[ãa]o)\b/i.test(t)) return { ok: false, motivo: 'generaliza para todas as contas' };
  if (tem('VENCIDO') && /\bem dia\b/i.test(t)) return { ok: false, motivo: 'diz que está em dia, mas há contas vencidas' };
  // Precisa dizer pelo menos uma quantidade certa (total ou de uma situação), em algarismo ou por extenso.
  const EXTENSO = { um: 1, uma: 1, dois: 2, duas: 2, 'três': 3, tres: 3, quatro: 4, cinco: 5, seis: 6, sete: 7, oito: 8, nove: 9, dez: 10 };
  const qtds = new Set([f.total, ...f.grupos.map((g) => g.qtd)]);
  const citaQtd = (t.match(/\b\d+\b/g) || []).some((n) => qtds.has(Number(n)))
    || (t.toLowerCase().match(/\b(um|uma|dois|duas|tr[êe]s|quatro|cinco|seis|sete|oito|nove|dez)\b/g) || []).some((w) => qtds.has(EXTENSO[w]));
  if (!citaQtd) return { ok: false, motivo: 'não diz quantas contas há' };
  const numerosDoTexto = new Set([...(t.match(/\b\d+\b/g) || []).map(Number),
    ...(t.toLowerCase().match(/\b(um|uma|dois|duas|tr[êe]s|quatro|cinco|seis|sete|oito|nove|dez)\b/g) || []).map((w) => EXTENSO[w])]);
  const faltando = f.grupos.filter((g) => !numerosDoTexto.has(g.qtd));
  if (faltando.length) return { ok: false, motivo: `faltou a quantidade de ${faltando[0].nome.toLowerCase()}` };
  const urgente = f.destaques[0];
  if (urgente) {
    if (!t.toLowerCase().includes(nucleoDoLocal(urgente.local))) return { ok: false, motivo: 'não cita a conta mais urgente' };
  }
  // No máximo 2 contas citadas (o resto está na lista): conta os locais distintos dos destaques que aparecem.
  const citadas = new Set(f.destaques.map((d) => nucleoDoLocal(d.local)).filter((n) => t.toLowerCase().includes(n))).size;
  if (citadas > 2) return { ok: false, motivo: 'cita contas demais (a lista completa vai abaixo)' };
  return { ok: true, motivo: '' };
}

// Escolhe a abertura: a da LLM, se veio no formato e passou na conferência; senão, a padrão.
function escolherAbertura(respostaOllama, f) {
  const r = respostaOllama || {};
  let abertura = '';
  try {
    abertura = String(JSON.parse(r.message?.content || '').abertura || '').trim();
  } catch (e) {
    return { abertura: textoModelo(f), origem: 'modelo', motivo: r.error ? `LLM indisponível (${String(r.error.message || r.error).slice(0, 80)})` : 'resposta da LLM fora do formato' };
  }
  const conferencia = conferirAbertura(abertura, f);
  if (!conferencia.ok) return { abertura: textoModelo(f), origem: 'modelo', motivo: conferencia.motivo, recusada: abertura.slice(0, 600) };
  return { abertura, origem: 'llm', motivo: '' };
}

// Contas por regional (marcador "Regional ..." do local, vindo da API em "regional"), para quem lê o resumo geral.
// Só aparece se algum local tiver regional; contas de local sem regional ficam em "Sem regional", no fim.
function resumoPorRegional(itens) {
  const contas = itens.filter((a) => Object.prototype.hasOwnProperty.call(a, 'regional'));
  if (!contas.some((a) => a.regional)) return [];
  const mapa = {};
  for (const a of contas) {
    const r = a.regional || 'Sem regional';
    mapa[r] = mapa[r] || { total: 0, status: {} };
    mapa[r].total += 1;
    mapa[r].status[a.status] = (mapa[r].status[a.status] || 0) + 1;
  }
  return Object.entries(mapa)
    .sort((x, y) => (x[0] === 'Sem regional') - (y[0] === 'Sem regional') || y[1].total - x[1].total || x[0].localeCompare(y[0], 'pt-BR'))
    .map(([nome, r]) => ({
      nome, total: r.total,
      detalhe: [...ORDEM_STATUS, ...Object.keys(r.status).filter((s) => !ORDEM_STATUS.includes(s))]
        .filter((s) => r.status[s]).map((s) => `${NOMES_STATUS[s] || s} ${r.status[s]}`).join(' · '),
    }));
}

// Mensagem final: abertura + resumo por regional + lista completa (direto da API) + rodapé dizendo de onde veio o texto.
function montarMensagem(f, escolha, modelo, duracaoMs) {
  const grupos = {};
  for (const a of f.itens) (grupos[a.status] = grupos[a.status] || []).push(a);
  const linhas = [escolha.abertura];
  const porRegional = resumoPorRegional(f.itens);
  if (porRegional.length) {
    linhas.push('', 'Por regional:');
    porRegional.forEach((r) => linhas.push(`- ${r.nome}: ${r.total} (${r.detalhe})`));
  }
  const ordem = [...ORDEM_STATUS, ...Object.keys(grupos).filter((s) => !ORDEM_STATUS.includes(s))];
  for (const s of ordem) {
    if (!grupos[s]) continue;
    linhas.push('', `${NOMES_STATUS[s] || s} (${grupos[s].length}):`);
    grupos[s].slice(0, MAX_POR_GRUPO).forEach((a) => {
      const valor = formatarBRL(a.valor);
      linhas.push(`- ${a.mensagem}${valor ? ` · R$ ${valor}` : ''}${a.regional ? ` · ${a.regional}` : ''}`);
    });
    if (grupos[s].length > MAX_POR_GRUPO) linhas.push(`  … e mais ${grupos[s].length - MAX_POR_GRUPO}`);
  }
  linhas.push('', '—', escolha.origem === 'llm'
    ? `A abertura foi escrita pela IA local (${modelo}) e conferida pelo SIGp. A lista vem direto do sistema.`
    : `Abertura com o texto padrão do SIGp (${escolha.motivo}). A lista vem direto do sistema.`);
  const texto = linhas.join('\n');
  return {
    escopo: 'SIG',
    titulo: `Alertas do dia ${f.hojeBR}`,
    referencia: `alertas-${f.hoje}`,
    conteudo: texto,
    texto,
    assunto: `SIGp · ${f.total} ${f.total === 1 ? 'alerta' : 'alertas'} em ${f.hojeBR}`,
    modelo: escolha.origem === 'llm' ? modelo : 'regra fixa',
    dados: {
      total: f.total,
      grupos: Object.fromEntries(f.grupos.map((g) => [g.status, g.qtd])),
      porRegional: Object.fromEntries(porRegional.map((r) => [r.nome, r.total])),
      textoAbertura: { origem: escolha.origem, motivo: escolha.motivo, ...(escolha.recusada ? { recusada: escolha.recusada } : {}), duracaoMs: duracaoMs || null },
    },
  };
}
