// Funções compartilhadas pelos nós Code do WF-08 v2.
// Este arquivo é a fonte: build_wf08.ps1 o copia para dentro dos nós do workflow.
// Teste local: docker exec -i sigp_n8n node < n8n/wf08/testes_wf08.js (ver README da pasta).

// Empresas do grupo: sempre clientes (pagadoras), nunca provedores. Edite conforme o cadastro.
const EMPRESAS_DO_GRUPO = ['ROTA TRANSPORTE', 'VIACAO JEQUIE', 'EXPRESSO BRASILEIRO'];

const TIPOS_COBRANCA = ['boleto_fatura', 'fatura_e_nota', 'nota_fiscal', 'lembrete'];
const CONFIANCA_MINIMA = 0.8;
const INTERNET_CATEGORIAS = ['FATURA_INTERNET', 'NOTA_SERVICO_INTERNET'];
const TEXTO_MINIMO = 200; // abaixo disso o PDF não foi lido de verdade
const CONFIRMACOES_PARA_DESCARTE = 3;
const EVENTOS = ['fatura_nova', 'segunda_via', 'lembrete_vencimento', 'aviso_atraso', 'pagamento_confirmado']; // mesmo remetente confirmado 3x como "não é cobrança" = descarte automático

const semAcento = (v) => String(v || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
const soDigitos = (v) => String(v || '').replace(/\D/g, '');
const limparNome = (v) => String(v ?? '').replace(/\s+/g, ' ').trim().slice(0, 300);
const ehEmpresaDoGrupo = (nome) => EMPRESAS_DO_GRUPO.some((e) => semAcento(nome).includes(e));
const pareceEndereco = (v) => /\d{5}-?\d{3}|\b(RUA|R\.|AV|AVENIDA|RODOVIA|RODAVIA|BR-\d+|ESTRADA|TRAVESSA|PRACA)\b/i.test(semAcento(v));

function paraNumero(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number') return Number.isFinite(v) ? Math.round(v * 100) / 100 : null;
  const s = String(v).replace(/[^\d.,-]/g, '');
  const n = Number(s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s);
  return Number.isFinite(n) ? Math.round(n * 100) / 100 : null;
}

function normalizarData(v) {
  const s = String(v || '').trim();
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) {
    const br = s.match(/^(\d{2})[/.-](\d{2})[/.-](\d{4})$/);
    if (br) m = [br[0], br[3], br[2], br[1]];
  }
  if (!m) return '';
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCMonth() === +m[2] - 1 ? `${m[1]}-${m[2]}-${m[3]}` : '';
}

function normalizarCompetencia(v) {
  const s = String(v || '').trim();
  let m = s.match(/^(\d{4})-(\d{2})/);
  if (m && +m[2] >= 1 && +m[2] <= 12) return `${m[1]}-${m[2]}`;
  m = s.match(/^(\d{2})\/(\d{4})$/);
  if (m && +m[1] >= 1 && +m[1] <= 12) return `${m[2]}-${m[1]}`;
  return '';
}

// Remove colunas de espaços do OCR e limita o tamanho enviado ao modelo.
function compactarTexto(texto, limite = 3000) {
  return String(texto || '')
    .replace(/[ \t]{3,}/g, ' | ')
    .replace(/\n\s*\n+/g, '\n')
    .trim()
    .slice(0, limite);
}

// Boleto bancário (47 dígitos): os 14 finais trazem fator de vencimento e valor.
// Fator 1000 = 22/02/2025 (reinício do fator definido pela Febraban).
function lerLinhaDigitavel(texto) {
  const m = String(texto || '').match(/(\d{5}[.\s]?\d{5}\s+\d{5}[.\s]?\d{6}\s+\d{5}[.\s]?\d{6}\s+\d\s+\d{14})/);
  if (!m) return { linhaDigitavel: '', valorBoleto: null, vencimentoBoleto: '' };
  const d = soDigitos(m[1]);
  if (d.length !== 47) return { linhaDigitavel: '', valorBoleto: null, vencimentoBoleto: '' };
  const fator = Number(d.slice(33, 37));
  const valor = Number(d.slice(37)) / 100;
  const vencimento = fator >= 1000
    ? new Date(Date.UTC(2025, 1, 22) + (fator - 1000) * 86400000).toISOString().slice(0, 10)
    : '';
  return { linhaDigitavel: d, valorBoleto: valor > 0 ? Math.round(valor * 100) / 100 : null, vencimentoBoleto: vencimento };
}

// Extração por regras (B-03): a mesma do WF-03 e do SIGp, em n8n/lib/extrator.js (ExtratorSIGp).
// build_wf08.ps1 cola a lib antes deste arquivo. Aqui ficam só as partes próprias do WF-08:
// destinatário pela empresa do grupo e valor/vencimento do texto separados dos da linha digitável.
function extrairCampos(texto) {
  const text = String(texto || '');
  const f = ExtratorSIGp.extrairCamposFatura(text);
  const textoSemAcento = semAcento(text);
  const cnpjRe = /\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}/g;
  const todosCnpjs = [...text.matchAll(cnpjRe)].map((m) => ({ cnpj: soDigitos(m[0]), pos: m.index }));

  // Destinatário: primeira empresa do grupo citada e o CNPJ logo depois dela; senão, o do extrator (tomador).
  let empresaDestinataria = '';
  let cnpjDestinatario = '';
  for (const empresa of EMPRESAS_DO_GRUPO) {
    const pos = textoSemAcento.indexOf(empresa);
    if (pos < 0) continue;
    const fimLinha = text.indexOf('\n', pos);
    empresaDestinataria = limparNome(text.slice(pos, fimLinha < 0 ? undefined : fimLinha).split(/\s{3,}|\|/)[0]);
    cnpjDestinatario = todosCnpjs.find((c) => c.pos >= pos && c.pos - pos <= 250)?.cnpj || '';
    break;
  }
  cnpjDestinatario = cnpjDestinatario || f.cnpjDestinatario;

  // Emissor: o do extrator, desde que não seja o destinatário; senão, CNPJ perto do rótulo de emissor.
  let cnpjEmissor = f.cnpjEmissor && f.cnpjEmissor !== cnpjDestinatario ? f.cnpjEmissor : '';
  if (!cnpjEmissor) {
    for (const m of text.matchAll(/benefici[aá]rio|cedente|prestador|emitente|raz[aã]o social/gi)) {
      const c = todosCnpjs.find((x) => x.pos >= m.index && x.pos - m.index <= 700 && x.cnpj !== cnpjDestinatario);
      if (c) { cnpjEmissor = c.cnpj; break; }
    }
  }
  if (!cnpjEmissor) {
    const outros = [...new Set(todosCnpjs.map((c) => c.cnpj).filter((c) => c !== cnpjDestinatario))];
    if (outros.length === 1) [cnpjEmissor] = outros;
  }

  const emissorNome = limparNome(f.emissorNome);
  return {
    ...lerLinhaDigitavel(text),
    empresaDestinataria,
    cnpjDestinatario,
    cnpjEmissor,
    emissorNome: ehEmpresaDoGrupo(emissorNome) ? '' : emissorNome,
    // Sem o padrão 999999999 aqui: a IA ainda pode sugerir o número; o SIGp aplica o padrão ao receber.
    numero: f.numeroPadrao ? '' : limparNome(f.numero).slice(0, 80),
    chave: f.chavePadrao ? '' : f.chave,
    valorTotal: f.valorTexto,
    dataVencimento: f.vencimentoTexto,
    dataEmissao: f.dataEmissao,
    descricaoServico: f.descricaoServico,
  };
}

// Memória de exemplos (etapa 4): decisões do operador em documentos parecidos (GET /api/llm/exemplos).
// Vêm do banco local, já curtos e numa linha; entram como referência, nunca como instrução.
function textoExemplos(exemplos) {
  const linha = (e) => {
    const base = `remetente ${e.remetente || '(desconhecido)'} · assunto "${String(e.assunto || '').slice(0, 90)}"`;
    if (e.rotulo === 'cobranca_provedor') {
      return `- ${base} → COBRANÇA DE PROVEDOR (provedor: ${e.provedor || '?'}; tipo: ${e.tipoDocumento || '?'}${e.local ? `; local: ${e.local}` : ''})`
        + (e.correcao ? ` [correção do operador: ${e.correcao}]` : '');
    }
    return `- ${base} → NÃO É COBRANÇA DE PROVEDOR (${[e.motivo, e.detalhe].filter(Boolean).join(': ') || 'descartado pelo operador'})`;
  };
  const lista = (Array.isArray(exemplos) ? exemplos : []).slice(0, 8);
  return lista.length ? ['--- Exemplos confirmados pelo operador (documentos parecidos) ---', ...lista.map(linha)].join('\n') : '';
}

function montarMensagensIA(meta, textoOcr, exemplos = []) {
  const usuario = [
    textoExemplos(exemplos),
    `Remetente: ${meta.remetente || '(desconhecido)'}`,
    `Assunto: ${meta.assunto || ''}`,
    `Arquivo: ${meta.nomeArquivo || ''}`,
    `Corpo do e-mail: ${String(meta.corpo || '').slice(0, 800)}`,
    '--- Texto do PDF (OCR) ---',
    compactarTexto(textoOcr) || '(sem texto reconhecido)',
  ].filter(Boolean).join('\n');
  return [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: usuario },
  ];
}

function lerRespostaIA(resposta) {
  if (!resposta || resposta.error) {
    const erro = resposta?.error;
    return { ia: null, erro: String(erro?.message || erro || 'sem resposta do Ollama').slice(0, 300) };
  }
  try {
    const ia = JSON.parse(resposta.message?.content || '');
    if (!ia || typeof ia !== 'object' || !ia.tipoDocumento) throw new Error('JSON sem tipoDocumento');
    return { ia, erro: '' };
  } catch (e) {
    return { ia: null, erro: `resposta da IA inválida: ${e.message}`.slice(0, 300) };
  }
}

// Junta regras do SIGp, campos determinísticos do PDF e a sugestão da IA.
// A IA classifica e sugere; valor/vencimento do boleto lidos da linha digitável prevalecem.
function consolidar({ ia, iaErro, regras, ext, meta, modelo, ocrUsado, caracteresTexto, texto }) {
  regras = regras || {};
  let tipo = String(ia?.tipoDocumento || '');
  const confBruta = Number(ia?.confianca);
  const confianca = Number.isFinite(confBruta) ? Math.max(0, Math.min(1, confBruta)) : 0;
  if (tipo === 'nota_fiscal' && ext.linhaDigitavel) tipo = 'fatura_e_nota';

  const valorIA = paraNumero(ia?.valor);
  const vencIA = normalizarData(ia?.vencimento);
  const valorFinal = ext.valorBoleto ?? ext.valorTotal ?? valorIA;
  const vencFinal = ext.vencimentoBoleto || ext.dataVencimento || vencIA;
  const divergencias = [];
  if (valorIA !== null && valorFinal !== null && Math.abs(valorIA - valorFinal) > 0.01) {
    divergencias.push(`valor: IA ${valorIA} x documento ${valorFinal}`);
  }
  if (ext.valorBoleto !== null && ext.valorTotal !== null && Math.abs(ext.valorBoleto - ext.valorTotal) > 0.01) {
    divergencias.push(`valor: boleto ${ext.valorBoleto} x texto ${ext.valorTotal}`);
  }
  if (vencIA && vencFinal && vencIA !== vencFinal) divergencias.push(`vencimento: IA ${vencIA} x documento ${vencFinal}`);

  // Não inventar: o provedor sugerido pela IA só vale se o nome aparecer no documento ou no remetente
  // (evita copiar o provedor de um exemplo de outro e-mail).
  const provedorSugerido = limparNome(ia?.provedorNome);
  const provedorIA = provedorSugerido && texto !== undefined && !nomeApareceNoTexto(provedorSugerido, `${texto} ${meta.remetente || ''}`)
    ? '' : provedorSugerido;
  const empresaIA = limparNome(ia?.empresaDestinataria);
  const remetenteNome = limparNome(String(meta.remetente || '').replace(/<[^>]*>/g, '').replace(/"/g, ''));
  const emissorNome = (provedorIA && !ehEmpresaDoGrupo(provedorIA) ? provedorIA : '')
    || ext.emissorNome
    || (regras.provedoresPorRemetente || regras.provedoresEncontrados || [])[0]
    || (ehEmpresaDoGrupo(remetenteNome) ? '' : remetenteNome);
  const empresaDestinataria = ext.empresaDestinataria
    || (empresaIA && !pareceEndereco(empresaIA) && !(provedorIA && empresaIA === provedorIA) ? empresaIA : '');

  // Triagem em três níveis (alta / baixa / inconclusivo). A LLM decide o "não é cobrança"; a regra só impede
  // ignorar quando há sinal de internet ou quando o PDF não foi lido (aí ninguém sabe: inconclusivo).
  const sinaisInternet = INTERNET_CATEGORIAS.includes(regras.categoria)
    || ['provedoresEncontrados', 'provedoresPorRemetente', 'palavrasInternet'].some((k) => (regras[k] || []).length);
  const legivel = caracteresTexto === undefined || caracteresTexto >= TEXTO_MINIMO;
  const iaNao = !iaErro && tipo === 'outro' && confianca >= CONFIANCA_MINIMA;
  const hist = regras.remetente || {};
  const remetenteConfirmado = Number(hist.confirmadosNaoCobranca || 0) >= CONFIRMACOES_PARA_DESCARTE
    && !Number(hist.cobrancasConfirmadas || 0);
  const ignorar = legivel && !sinaisInternet && (iaNao || remetenteConfirmado);
  const autoDescarte = ignorar && remetenteConfirmado;
  let probabilidade = 'inconclusivo';
  let motivoProbabilidade;
  if (!legivel) motivoProbabilidade = 'PDF sem texto legível (senha, imagem ou arquivo vazio)';
  else if (autoDescarte) { probabilidade = 'baixa'; motivoProbabilidade = `Remetente confirmado ${hist.confirmadosNaoCobranca} vezes como não cobrança`; }
  else if (ignorar) { probabilidade = 'baixa'; motivoProbabilidade = 'Sem sinal de internet e a IA diz que não é cobrança'; }
  else if (iaErro) motivoProbabilidade = 'A IA não respondeu';
  else if (sinaisInternet && iaNao) motivoProbabilidade = 'A regra vê internet, mas a IA diz que não é cobrança';
  else if (sinaisInternet) { probabilidade = 'alta'; motivoProbabilidade = 'Sinal de internet e a IA concorda'; }
  else motivoProbabilidade = 'Só a IA indica cobrança; nenhum provedor ou termo de internet encontrado';

  const camposParaRevisar = [];
  if (iaErro) camposParaRevisar.push('classificacaoIA');
  if (!TIPOS_COBRANCA.includes(tipo)) camposParaRevisar.push('tipoDocumento');
  if (confianca < CONFIANCA_MINIMA) camposParaRevisar.push('confianca');
  if (valorFinal === null) camposParaRevisar.push('valorTotal');
  if (!vencFinal && tipo !== 'nota_fiscal') camposParaRevisar.push('dataVencimento');
  if (!emissorNome) camposParaRevisar.push('emissorNome');
  if (divergencias.length) camposParaRevisar.push('divergencias');

  return {
    decisao: ignorar ? 'ignorar' : 'importar',
    probabilidade,
    motivoProbabilidade,
    autoDescarte,
    dadosExtracao: {
      evento: escolherEvento(regras.evento, ia, confianca, iaErro),
      identificadoresCliente: texto === undefined ? [] : lerIdentificadoresCliente(texto),
      empresaDestinataria,
      cnpjDestinatario: ext.cnpjDestinatario,
      emissorNome,
      numero: ext.numero || limparNome(ia?.numeroDocumento).slice(0, 80),
      chave: ext.chave,
      cnpjEmissor: ext.cnpjEmissor,
      valorTotal: valorFinal,
      dataEmissao: ext.dataEmissao,
      dataVencimento: vencFinal,
      descricaoServico: ext.descricaoServico,
      tipoDocumento: tipo || 'indefinido',
      competencia: normalizarCompetencia(ia?.competencia),
      linhaDigitavel: ext.linhaDigitavel,
      ocrUsado: Boolean(ocrUsado),
      versaoRegras: typeof ExtratorSIGp !== 'undefined' ? ExtratorSIGp.VERSAO_REGRAS : 0,
      classificacao: {
        ...regras,
        origemBusca: meta.origemBusca,
        metodo: 'regras_v1+ia_local',
        ia: {
          modelo,
          tipoDocumento: ia?.tipoDocumento || '',
          confianca,
          motivo: limparNome(ia?.motivo),
          provedorNome: provedorIA,
          empresaDestinataria: empresaIA,
          valor: valorIA,
          vencimento: vencIA,
          erro: iaErro || '',
        },
        divergencias,
      },
      revisaoManual: camposParaRevisar.length > 0,
      camposParaRevisar,
    },
  };
}

// Ajuste final da probabilidade depois de OCR/XML: o que não pode ser ignorado não fica "baixa", e
// "alta" sem valor, vencimento ou emissor vira inconclusivo (falta informação para decidir).
function probabilidadeFinal(dados, probabilidade, motivo, { ocrErro = false, xml = false } = {}) {
  if (ocrErro) return { probabilidade: 'inconclusivo', motivo: 'O PDF não pôde ser lido (OCR)' };
  if (xml && probabilidade === 'baixa') return { probabilidade: 'inconclusivo', motivo: 'Tem XML de nota fiscal: confira se é cobrança' };
  if (probabilidade === 'alta') {
    const faltam = [
      !(Number(dados.valorTotal) > 0) && 'valor',
      !dados.dataVencimento && dados.tipoDocumento !== 'nota_fiscal' && 'vencimento',
      !dados.emissorNome && 'emissor',
    ].filter(Boolean);
    if (faltam.length) return { probabilidade: 'inconclusivo', motivo: `Parece internet, mas falta: ${faltam.join(', ')}` };
  }
  return { probabilidade, motivo };
}

// Situação 1: tipo de e-mail. Frase clara achada pela regra do SIGp vale; sem frase, vale a LLM com 80%+.
function escolherEvento(regra, ia, confianca, iaErro) {
  if (regra && regra.tipo && regra.tipo !== 'fatura_nova') return { tipo: regra.tipo, origem: 'regra', frase: regra.frase || '' };
  if (!iaErro && EVENTOS.includes(ia?.evento) && ia.evento !== 'fatura_nova' && confianca >= CONFIANCA_MINIMA) {
    return { tipo: ia.evento, origem: 'ia', frase: '' };
  }
  return { tipo: 'fatura_nova', origem: regra ? 'regra' : 'padrao', frase: '' };
}

const PALAVRAS_GENERICAS = new Set(['INTERNET', 'TELECOM', 'TELECOMUNICACOES', 'TELECOMUNICACAO', 'COMUNICACAO', 'COMUNICACOES',
  'SERVICOS', 'SERVICO', 'PROVEDOR', 'FIBRA', 'REDE', 'REDES', 'TECNOLOGIA', 'SOLUCOES', 'INFORMATICA', 'DIGITAL', 'CONECTIVIDADE',
  'CONEXAO', 'BANDA', 'LARGA', 'LINK', 'DADOS', 'GRUPO', 'EMPRESA', 'COMERCIO', 'BRASIL', 'NORDESTE', 'BAHIA', 'LTDA', 'EIRELI', 'S/A']);
// Alguma palavra própria do nome (4+ letras, não genérica) aparece no texto?
function nomeApareceNoTexto(nome, texto) {
  const alvo = semAcento(texto).replace(/[^A-Z0-9]+/g, ' ');
  const palavras = semAcento(nome).replace(/[^A-Z0-9]+/g, ' ').split(' ').filter((p) => p.length >= 4 && !PALAVRAS_GENERICAS.has(p));
  if (!palavras.length) return true;
  return palavras.some((p) => ` ${alvo} `.includes(` ${p} `));
}

// Situações 3 a 5: código do cliente, contrato e endereço de instalação (mesma regra de backend/identificadores.py;
// casos de teste compartilhados em tests/casos_identificadores.json).
function normalizarCodigo(v) {
  const t = String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  return t.replace(/^0+/, '') || t;
}
function lerIdentificadoresCliente(texto) {
  const ROT_CLIENTE = '(?:c[oó]d(?:igo|\\.)?\\s*(?:do\\s*)?cliente|n[ºo°.]*\\s*(?:do\\s*)?cliente|id\\s*(?:do\\s*)?cliente)';
  const ROT_CONTRATO = '(?:n[uú]mero\\s*do\\s*contrato(?:\\s*\\(id\\))?|n[ºo°.]+\\s*(?:do\\s*)?contrato|ref\\.?\\s*a\\s*contrato|contrato(?:\\(s\\))?)';
  const VALOR = '[:\\-]?\\s*([A-Z0-9][A-Z0-9.\\-/]{0,24})';
  const padroes = [['cliente', new RegExp(`${ROT_CLIENTE}\\s*${VALOR}`, 'gi')], ['contrato', new RegExp(`${ROT_CONTRATO}\\s*${VALOR}`, 'gi')]];
  const instalacao = /(?:endere[cç]o\s*de\s*)?instala[cç][aã]o\s*:\s*([^\n]{8,80})/i;
  const data = /^\d{1,2}[/.]\d{1,2}([/.]\d{2,4})?$/;
  const valido = (v) => { const d = v.replace(/\D/g, ''); const n = normalizarCodigo(v).length; return d.length > 0 && n >= 3 && n <= 15 && d.length <= 15 && !data.test(v); };
  const achados = [];
  const vistos = new Set();
  const guardar = (tipo, valor) => {
    const chave = `${tipo}:${normalizarCodigo(valor)}`;
    if (normalizarCodigo(valor) && !vistos.has(chave) && achados.length < 6) { vistos.add(chave); achados.push({ tipo, valor: valor.replace(/^[.\-/ ]+|[.\-/ ]+$/g, '') }); }
  };
  const linhas = String(texto || '').split(/\r?\n/);
  linhas.forEach((linha, i) => {
    for (const [tipo, re] of padroes) {
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(linha))) { if (valido(m[1])) guardar(tipo, m[1]); }
    }
    // Rótulo de coluna: o valor está na linha de baixo, na mesma coluna (o texto do PDF preserva as posições).
    const soRotulo = new RegExp(ROT_CLIENTE, 'gi');
    let r;
    while ((r = soRotulo.exec(linha))) {
      const depois = linha.slice(r.index + r[0].length, r.index + r[0].length + 30);
      if (/^\s*[:\-]?\s*[A-Z0-9]*\d/i.test(depois) || i + 1 >= linhas.length) continue;
      const perto = [];
      const tok = /\S+/g;
      let t;
      while ((t = tok.exec(linhas[i + 1]))) {
        if (/^[A-Z0-9][A-Z0-9.\-/]{3,24}$/i.test(t[0]) && valido(t[0]) && Math.abs(t.index - r.index) <= 15) perto.push([Math.abs(t.index - r.index), t[0]]);
      }
      perto.sort((a, b) => a[0] - b[0] || (a[1] < b[1] ? -1 : 1));
      if (perto.length) guardar('cliente', perto[0][1]);
    }
    const inst = instalacao.exec(linha);
    if (inst && /[A-Za-z]{3,}/.test(inst[1])) guardar('instalacao', inst[1].split(/\s+/).join(' ').trim().slice(0, 80));
  });
  return achados;
}
