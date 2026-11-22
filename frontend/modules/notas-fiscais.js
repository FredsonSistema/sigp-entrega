const NFSE_STORAGE_KEY = 'sigp_nfse_v1';
const NFSE_EVENTOS = ['nfse_lancada', 'nota_lancada', 'nfse_atualizada', 'nota_paga', 'nfse_cancelada', 'nota_cancelada'];

function normalizarStatusNFSE(evento, item = {}) {
  const status = String(item.status || '').toUpperCase();
  if (['nfse_lancada', 'nota_lancada'].includes(evento)) return status || 'PENDENTE';
  if (['nota_paga', 'nfse_paga'].includes(evento)) return status || 'PAGA';
  if (['nfse_atualizada', 'nota_atualizada'].includes(evento)) return status || 'PENDENTE';
  return status || 'PENDENTE';
}

function loadNFSE() {
  try {
    const raw = localStorage.getItem(NFSE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (error) {
    return [];
  }
}

function saveNFSE(lista) {
  localStorage.setItem(NFSE_STORAGE_KEY, JSON.stringify(lista));
}

function parseValorNFSE(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  const cleaned = String(value ?? '').replace(/[R$\s]/g, '');
  const canonical = cleaned.includes(',')
    ? cleaned.replace(/\./g, '').replace(',', '.')
    : cleaned;
  const parsed = Number(canonical);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizarServicosNFSE(items = []) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => ({
    id: item.id || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())),
    codigo: String(item.codigo || item.codigoServico || '').trim(),
    descricao: String(item.descricao || item.description || '').trim(),
    quantidade: parseValorNFSE(item.quantidade || 0),
    valorUnitario: parseValorNFSE(item.valorUnitario || 0),
    valorTotal: parseValorNFSE(item.valorTotal ?? item.valor ?? 0),
    classificacao: String(item.classificacao || 'PENDENTE').toUpperCase(),
  })).filter((item) => item.descricao);
}

function extrairDataVencimentoXInfComp(texto = '') {
  const match = String(texto).match(/\bvencimento\b\s*(?:da\s+nota\s*)?[:\-]?\s*(\d{2}\/\d{2}\/\d{4}|\d{4}-\d{2}-\d{2})/i);
  if (!match) return '';
  const data = match[1];
  if (/^\d{4}-/.test(data)) return data;
  const [, dia, mes, ano] = data.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  return `${ano}-${mes}-${dia}`;
}

function normalizarNFSE(input = {}) {
  const valor = parseValorNFSE(input.valor ?? 0);
  const valorPago = parseValorNFSE(input.valorPago ?? 0);
  const localTipoNormalizado = String(input.localTipo || input.local_tipo || 'agencia').trim() || 'agencia';
  return {
    id: input.id || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())),
    chave: String(input.chave || '').trim(),
    numero: String(input.numero || '').trim(),
    serie: String(input.serie || '').trim(),
    provedorNome: String(input.provedorNome || '').trim(),
    localTipo: localTipoNormalizado,
    entidadeId: String(input.entidadeId || input.entidade_id || '').trim(),
    localNome: String(input.localNome || '').trim(),
    localCidade: String(input.localCidade || '').trim(),
    municipioCodigo: String(input.municipioCodigo || '').trim(),
    valor: Number.isFinite(valor) ? valor : 0,
    valorPago: Number.isFinite(valorPago) ? valorPago : 0,
    dataEmissao: input.dataEmissao || '',
    dataVencimento: input.dataVencimento || '',
    dataPagamento: input.dataPagamento || '',
    observacao: String(input.observacao || '').trim(),
    servicos: normalizarServicosNFSE(input.servicos || input.serviceItems || []),
    status: input.status || 'PENDENTE',
    criadoEm: input.criadoEm || new Date().toISOString(),
    atualizadoEm: input.atualizadoEm || new Date().toISOString(),
  };
}

function normalizarCamposNotaImportada(chave, payload = {}) {
  const origem = payload && typeof payload === 'object' ? payload : {};
  const doc = origem.documento || origem;
  const valorTotal = parseValorNFSE(doc.valorTotal ?? doc.valor ?? doc.valorTotalNfse ?? origem.valor ?? 0);
  const valorPago = parseValorNFSE(doc.valorPago ?? origem.valorPago ?? 0);

  return {
    id: doc.id || origem.id || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())),
    chave: String(doc.chave || origem.chave || chave || '').trim(),
    numero: String(doc.numero || origem.numero || '').trim(),
    serie: String(doc.serie || origem.serie || '').trim(),
    provedorNome: String(doc.provedorNome || origem.provedorNome || origem.provedor || doc.provedor || '').trim(),
    localTipo: String(doc.localTipo || origem.localTipo || 'agencia').trim() || 'agencia',
    entidadeId: String(doc.entidadeId || origem.entidadeId || '').trim(),
    localNome: String(doc.localNome || origem.localNome || '').trim(),
    localCidade: String(doc.localCidade || origem.localCidade || '').trim(),
    municipioCodigo: String(doc.municipioCodigo || origem.municipioCodigo || '').trim(),
    valor: Number.isFinite(valorTotal) ? valorTotal : 0,
    valorPago: Number.isFinite(valorPago) ? valorPago : 0,
    dataEmissao: doc.dataEmissao || origem.dataEmissao || '',
    dataVencimento: doc.dataVencimento || origem.dataVencimento || '',
    dataPagamento: doc.dataPagamento || origem.dataPagamento || '',
    observacao: String(doc.observacao || origem.observacao || '').trim(),
    servicos: normalizarServicosNFSE(doc.servicos || origem.servicos || doc.serviceItems || []),
    status: String(doc.status || origem.status || 'PENDENTE').toUpperCase(),
    criadoEm: doc.criadoEm || origem.criadoEm || new Date().toISOString(),
    atualizadoEm: doc.atualizadoEm || origem.atualizadoEm || new Date().toISOString(),
  };
}

function parseJsonImportado(conteudo) {
  try {
    const data = typeof conteudo === 'string' ? JSON.parse(conteudo) : conteudo;
    if (data && typeof data === 'object') {
      return data;
    }
  } catch (error) {
    return null;
  }
  return null;
}

// NFS-e (ABRASF e nacional), NF-e e NFCom: o mesmo leitor do n8n (frontend/modules/xml-fiscal.js é cópia de
// n8n/lib/xml_fiscal.js; o teste tests/test_paridade_extrator_n8n.py confere). Lê nNFSe e usa a razão social.
function lerXmlFiscalCompartilhado(text) {
  const leitor = typeof XmlFiscalSIGp !== 'undefined' ? XmlFiscalSIGp
    : (typeof window !== 'undefined' ? window.XmlFiscalSIGp : null);
  const r = leitor ? leitor.lerXmlFiscal(text) : null;
  if (!r || !r.ok) return null;
  return {
    chave: r.chave || '',
    numero: r.numero || '',
    serie: r.serie || '',
    provedorNome: r.emissorNome || r.emissorFantasia || '',
    localNome: r.destinatarioNome || '',
    localCidade: r.cidade || '',
    municipioCodigo: r.municipioCodigo || '',
    valor: r.valorTotal ?? 0,
    dataEmissao: r.dataEmissao || '',
    dataVencimento: r.dataVencimento || '',
    status: 'PENDENTE',
    observacao: 'Importado via XML',
    servicos: (r.servicos || []).map((s) => ({
      codigo: '', descricao: s.descricao, quantidade: s.quantidade ?? 1,
      valorUnitario: s.valorUnitario ?? s.valorTotal ?? 0, valorTotal: s.valorTotal ?? 0, classificacao: 'PENDENTE',
    })),
  };
}

function parseXmlImportado(conteudo) {
  if (typeof conteudo !== 'string') return null;
  const text = conteudo.trim();
  if (!text || !text.includes('<')) return null;
  const fiscal = lerXmlFiscalCompartilhado(text);
  if (fiscal) return fiscal;

  if (typeof DOMParser === 'undefined') return null;
  const xml = new DOMParser().parseFromString(text, 'application/xml');
  if (xml.querySelector('parsererror')) return null;
  const elements = (parent) => Array.from(parent?.getElementsByTagName('*') || []);
  const findByName = (parent, names) => {
    const nodes = elements(parent);
    for (const name of names) {
      const found = nodes.find((node) => (node.localName || node.nodeName.split(':').pop()).toLowerCase() === name.toLowerCase());
      if (found) return found;
    }
    return null;
  };
  const valueByName = (parent, ...names) => (findByName(parent, names)?.textContent || '').trim();

  if ((xml.documentElement.localName || xml.documentElement.nodeName).toLowerCase() === 'registropagamento') {
    const documentoOrigem = findByName(xml.documentElement, ['documentoOrigem']) || xml.documentElement;
    const pagamento = findByName(xml.documentElement, ['pagamento']) || xml.documentElement;
    const destinatario = findByName(documentoOrigem, ['destinatario']);
    const aviso = valueByName(xml.documentElement, 'aviso');
    const observacao = valueByName(xml.documentElement, 'observacao');
    const numeroPagamento = valueByName(documentoOrigem, 'numeroNotaPagamento', 'idPagamento');
    return {
      chave: valueByName(documentoOrigem, 'chave', 'chaveNota', 'chaveAcesso'),
      numero: valueByName(documentoOrigem, 'numeroNota', 'numeroFatura', 'numeroDocumento', 'numeroNotaPagamento'),
      serie: valueByName(documentoOrigem, 'serie'),
      provedorNome: valueByName(documentoOrigem, 'provedorNome', 'provedor', 'emitente'),
      localNome: valueByName(destinatario, 'razaoSocial', 'nome'),
      localCidade: valueByName(destinatario, 'cidade', 'xMun', 'municipio'),
      valor: parseValorNFSE(valueByName(documentoOrigem, 'valorOriginal', 'valorTotal', 'valor')),
      valorPago: parseValorNFSE(valueByName(pagamento, 'valorTotalPagoSimulado', 'valorTotalPago', 'valorPrincipalPago', 'valorPago')),
      dataVencimento: valueByName(documentoOrigem, 'vencimento', 'dataVencimento'),
      dataPagamento: valueByName(pagamento, 'dataPagamento', 'dataLiquidacao'),
      status: 'PAGA',
      observacao: [
        'Importado via XML de pagamento.',
        numeroPagamento ? `Referência do pagamento: ${numeroPagamento}.` : '',
        aviso,
        observacao,
      ].filter(Boolean).join(' '),
      servicos: [],
    };
  }

  if ((xml.documentElement.localName || xml.documentElement.nodeName).toLowerCase() === 'faturaalgar') {
    const fatura = findByName(xml.documentElement, ['fatura']);
    const emitente = findByName(xml.documentElement, ['emitente']);
    const destinatario = findByName(xml.documentElement, ['destinatario']);
    const enderecoInstalacao = findByName(destinatario, ['enderecoInstalacao']);
    const enderecoCobranca = findByName(destinatario, ['enderecoCobranca']);
    const informacoes = findByName(xml.documentElement, ['informacoesAdicionais']);
    const notaFiscalTexto = valueByName(informacoes, 'notaFiscalEletronica');
    const identidadeFiscal = notaFiscalTexto.match(/\bNF\s*N(?:[º°.]?\s*)?([A-Z0-9./-]+)\s*[-–]\s*S[ÉE]RIE\s*([A-Z0-9-]+)/i);
    const numeroFatura = valueByName(fatura, 'numero');
    const numeroNota = identidadeFiscal?.[1] || numeroFatura;
    const serie = identidadeFiscal?.[2] || '';
    const chave = valueByName(fatura, 'chaveAcesso', 'chNFe');
    const observacao = [
      'Importado via XML de fatura Algar.',
      numeroFatura ? `Fatura ${numeroFatura}.` : '',
      chave ? '' : 'O arquivo não contém chave de acesso de nota fiscal.',
      notaFiscalTexto && !identidadeFiscal ? `Referência fiscal: ${notaFiscalTexto}.` : '',
    ].filter(Boolean).join(' ');

    return {
      chave,
      numero: numeroNota,
      serie,
      provedorNome: valueByName(emitente, 'razaoSocial'),
      localNome: valueByName(destinatario, 'razaoSocial'),
      localCidade: valueByName(enderecoInstalacao, 'cidade') || valueByName(enderecoCobranca, 'cidade'),
      municipioCodigo: '',
      valor: parseValorNFSE(valueByName(fatura, 'valorTotal')),
      dataEmissao: valueByName(fatura, 'emissao'),
      dataVencimento: valueByName(fatura, 'vencimento'),
      status: 'PENDENTE',
      observacao,
      servicos: [],
    };
  }

  const infNfse = findByName(xml, ['InfNfse']) || xml.documentElement;
  const prestador = findByName(infNfse, ['PrestadorServico']) || infNfse;
  const tomador = findByName(infNfse, ['TomadorServico']) || infNfse;
  const tomadorEndereco = findByName(tomador, ['Endereco']) || tomador;
  const declaracao = findByName(infNfse, ['InfDeclaracaoPrestacaoServico']) || infNfse;
  const servico = findByName(declaracao, ['Servico']) || declaracao;
  const idAttribute = infNfse.getAttribute?.('Id') || '';
  const chave = valueByName(infNfse, 'CodigoVerificacao', 'chNFe', 'chave', 'cNFe') || idAttribute.replace(/^NFS/i, '');
  const numero = valueByName(infNfse, 'Numero', 'nNF', 'nDoc');
  const serie = valueByName(declaracao, 'Serie');
  const provedorNome = valueByName(prestador, 'NomeFantasia', 'RazaoSocial', 'xNome');
  const localNome = valueByName(tomador, 'RazaoSocial', 'xNome')
    || [valueByName(tomadorEndereco, 'Endereco'), valueByName(tomadorEndereco, 'Numero')].filter(Boolean).join(', ');
  const localCidade = valueByName(infNfse, 'xLocalidadeInc')
    || valueByName(tomadorEndereco, 'xMun', 'Municipio', 'Cidade');
  const municipioCodigo = valueByName(tomadorEndereco, 'CodigoMunicipio');
  const dataEmissao = valueByName(infNfse, 'DataEmissao', 'dEmi', 'dhEmi');
  const dataVencimento = extrairDataVencimentoXInfComp(valueByName(infNfse, 'xInfComp'));
  const valor = parseValorNFSE(valueByName(infNfse, 'ValorLiquidoNfse', 'ValorServicos', 'vNF', 'vTotNF'));
  const codigoServico = valueByName(servico, 'ItemListaServico', 'CodigoTributacaoMunicipio');
  let servicos = elements(servico)
    .filter((node) => (node.localName || node.nodeName.split(':').pop()).toLowerCase() === 'itensservico')
    .map((node) => ({
      codigo: codigoServico,
      descricao: valueByName(node, 'Discriminacao', 'Descricao', 'Description'),
      quantidade: parseValorNFSE(valueByName(node, 'Quantidade', 'qCom')),
      valorUnitario: parseValorNFSE(valueByName(node, 'ValorUnitario', 'vUnCom')),
      valorTotal: parseValorNFSE(valueByName(node, 'ValorTotal', 'vProd')),
      classificacao: 'PENDENTE',
    }))
    .filter((item) => item.descricao);
  if (!servicos.length) {
    const descricao = valueByName(servico, 'Discriminacao');
    if (descricao) servicos = [{ codigo: codigoServico, descricao, quantidade: 1, valorUnitario: valor, valorTotal: valor, classificacao: 'PENDENTE' }];
  }

  if (!chave && !numero && !serie && !provedorNome) {
    return null;
  }

  return {
    chave,
    numero,
    serie,
    provedorNome,
    localNome,
    localCidade,
    municipioCodigo,
    valor,
    dataEmissao,
    dataVencimento,
    status: 'PENDENTE',
    observacao: 'Importado via XML',
    servicos,
  };
}

function importarNotaArquivo({ tipo = 'json', conteudo = '', arquivoNome = '', registrarEvento = true } = {}) {
  if (!conteudo || typeof conteudo !== 'string') {
    return { ok: false, motivo: 'conteudo_vazio' };
  }

  let dados = null;
  if (tipo === 'json') {
    dados = parseJsonImportado(conteudo);
  } else if (tipo === 'xml') {
    dados = parseXmlImportado(conteudo);
  } else if (tipo === 'pdf') {
    return { ok: false, motivo: 'pdf_requer_extracao_manual' };
  } else {
    return { ok: false, motivo: 'tipo_nao_suportado' };
  }

  if (!dados) {
    return { ok: false, motivo: 'json_ou_xml_invalido' };
  }

  const normalizado = normalizarCamposNotaImportada(dados.chave || '', dados);
  const nota = normalizarNFSE({
    ...normalizado,
    id: normalizado.id,
    chave: normalizado.chave,
    numero: normalizado.numero,
    serie: normalizado.serie,
    provedorNome: normalizado.provedorNome,
    localTipo: normalizado.localTipo || 'agencia',
    localNome: normalizado.localNome,
    localCidade: normalizado.localCidade,
    valor: normalizado.valor,
    valorPago: normalizado.valorPago || 0,
    dataEmissao: normalizado.dataEmissao,
    dataVencimento: normalizado.dataVencimento,
    dataPagamento: normalizado.dataPagamento,
    observacao: normalizado.observacao || `Importado via ${tipo}${arquivoNome ? ' — ' + arquivoNome : ''}`,
    status: normalizado.status || 'PENDENTE',
  });

  if (!nota.chave && !nota.numero) {
    return { ok: false, motivo: 'chave_ou_numero_obrigatorio' };
  }

  const eventoPayload = registrarEvento ? emitirNFSE('nota_lancada', nota) : null;
  return {
    ok: true,
    nota,
    evento: registrarEvento ? 'nota_lancada' : null,
    payload: eventoPayload,
    tipo,
    arquivoNome,
  };
}

function criarNFSE(payload) {
  const lista = loadNFSE();
  const item = normalizarNFSE(payload);
  lista.push(item);
  saveNFSE(lista);
  return item;
}

function atualizarNFSE(id, payload) {
  const lista = loadNFSE();
  const index = lista.findIndex((item) => item.id === id);
  if (index === -1) return null;

  const atualizado = {
    ...lista[index],
    ...normalizarNFSE({ ...lista[index], ...payload }),
    atualizadoEm: new Date().toISOString(),
  };

  lista[index] = atualizado;
  saveNFSE(lista);
  return atualizado;
}

function excluirNFSE(id) {
  const lista = loadNFSE().filter((item) => item.id !== id);
  saveNFSE(lista);
  return lista;
}

function buildNFSEEvent(evento, item) {
  if (!NFSE_EVENTOS.includes(evento)) {
    throw new Error(`Evento inválido para NFSe: ${evento}`);
  }

  const eventoStatus = normalizarStatusNFSE(evento, item);
  const valorTotal = Number(item.valor || item.valorTotal || 0);
  const valorPago = Number(item.valorPago || 0);

  const documento = {
    id: item.id,
    tipoDocumento: 'NFSE',
    origem: 'SIGP',
    chave: item.chave,
    numero: item.numero,
    serie: item.serie,
    provedorNome: item.provedorNome,
    localTipo: String(item.localTipo || 'agencia').trim() || 'agencia',
    localNome: item.localNome,
    localCidade: item.localCidade,
    valorTotal,
    valorPago: eventoStatus === 'PAGA' ? valorTotal : valorPago,
    dataEmissao: item.dataEmissao,
    dataVencimento: item.dataVencimento,
    dataPagamento: item.dataPagamento || (eventoStatus === 'PAGA' ? new Date().toISOString() : ''),
    observacao: item.observacao,
    servicos: normalizarServicosNFSE(item.servicos || []),
    status: eventoStatus,
    criadoEm: item.criadoEm || new Date().toISOString(),
    atualizadoEm: item.atualizadoEm || new Date().toISOString(),
  };

  const itens = [{
    id: `${item.id}-item-1`,
    documentoId: item.id,
    localTipo: documento.localTipo,
    localId: '',
    localNome: item.localNome,
    localCidade: item.localCidade,
    valor: valorTotal,
    status: eventoStatus === 'PAGA' ? 'PAGO' : eventoStatus,
    observacao: item.observacao,
    dataVencimento: item.dataVencimento,
    dataPagamento: documento.dataPagamento,
  }];

  const payload = {
    versao: 2,
    evento,
    timestamp: new Date().toISOString(),
    documento,
    itens,
    resumo: {
      totalItens: itens.length,
      totalValor: valorTotal,
      status: documento.status,
    },
    dados: {
      id: documento.id,
      tipoDocumento: documento.tipoDocumento,
      chave: documento.chave,
      numero: documento.numero,
      serie: documento.serie,
      provedorNome: documento.provedorNome,
      localTipo: documento.localTipo,
      localNome: documento.localNome,
      localCidade: documento.localCidade,
      valor: valorTotal,
      valorTotal,
      valorPago: documento.valorPago,
      dataEmissao: documento.dataEmissao,
      dataVencimento: documento.dataVencimento,
      dataPagamento: documento.dataPagamento,
      observacao: documento.observacao,
      servicos: documento.servicos,
      status: documento.status,
    },
  };

  return payload;
}

function importarNotaManual(payload = {}) {
  const nota = criarNFSE({
    ...payload,
    status: payload.status || 'PENDENTE',
    criadoEm: payload.criadoEm || new Date().toISOString(),
    atualizadoEm: payload.atualizadoEm || new Date().toISOString(),
  });

  const evento = 'nota_lancada';
  const eventoPayload = emitirNFSE(evento, nota);
  return { nota, evento, payload: eventoPayload };
}

function registrarPagamentoNFSE(id, pagamento = {}) {
  const lista = loadNFSE();
  const nota = lista.find((item) => item.id === id);
  if (!nota) {
    return { ok: false, motivo: 'nota_nao_encontrada' };
  }

  const valorPago = Number(pagamento.valorPago ?? pagamento.valor ?? nota.valor ?? 0);
  const dataPagamento = pagamento.dataPagamento || new Date().toISOString();
  const status = valorPago >= Number(nota.valor || 0) ? 'PAGA' : 'PAGO_PARCIAL';

  const atualizada = atualizarNFSE(id, {
    ...nota,
    valorPago,
    dataPagamento,
    status,
    observacao: pagamento.observacao || nota.observacao,
    atualizadoEm: new Date().toISOString(),
  });

  const payload = emitirNFSE('nota_paga', atualizada);
  return { ok: true, nota: atualizada, evento: 'nota_paga', payload };
}

function emitirNFSE(evento, item) {
  const payload = buildNFSEEvent(evento, item);
  if (typeof window !== 'undefined') {
    const fila = JSON.parse(localStorage.getItem('sigp_nfse_eventos_v1') || '[]');
    fila.push(payload);
    localStorage.setItem('sigp_nfse_eventos_v1', JSON.stringify(fila));
  }
  return payload;
}

async function sincronizarBackendNFSE(item) {
  return salvarNotaLancadaBackend(item);
}

function getNFSEBackendUrl() {
  return window.SIGP_CONFIG.apiUrl();
}

function mapBackendNFSE(item = {}) {
  const nota = normalizarNFSE({
    id: item.id,
    chave: item.chave,
    numero: item.numero,
    serie: item.serie,
    provedorNome: item.provedor_nome ?? item.provedorNome,
    localTipo: item.entidade_tipo ?? item.localTipo ?? 'agencia',
    entidadeId: item.entidade_id ?? item.entidadeId ?? '',
    localNome: item.local_nome ?? item.localNome,
    localCidade: item.local_cidade ?? item.localCidade,
    municipioCodigo: item.municipio_codigo ?? item.municipioCodigo,
    valor: item.valor_total ?? item.valorTotal ?? item.valor,
    valorPago: item.valor_pago ?? item.valorPago,
    dataEmissao: item.data_emissao ?? item.dataEmissao,
    dataVencimento: item.data_vencimento ?? item.dataVencimento,
    dataPagamento: item.data_pagamento ?? item.dataPagamento,
    observacao: item.observacao,
    servicos: item.servicos || [],
    status: item.status,
    criadoEm: item.created_at ?? item.createdAt,
    atualizadoEm: item.updated_at ?? item.updatedAt,
  });
  nota.faturaAnexada = Boolean(item.fatura_anexada);
  return nota;
}

async function requisitarBackendNFSE(path, options = {}) {
  if (typeof fetch !== 'function') throw new Error('fetch_indisponivel');
  const response = await fetch(`${getNFSEBackendUrl().replace(/\/$/, '')}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(body.error || `http_${response.status}`), { status: response.status });
  return body;
}

async function listarNotasBackendNFSE(tipo = 'lancadas') {
  const body = await requisitarBackendNFSE(`/api/notas/${tipo}`);
  return (body.items || []).map(mapBackendNFSE);
}

// Notas entram pelo n8n (igual à produção) quando SIGP_API está carregado; sem ele, direto na API.
async function enviarDocumentoNFSE(path, payload) {
  if (typeof window !== 'undefined' && window.SIGP_API?.enviarDocumento) {
    return window.SIGP_API.enviarDocumento(path, payload);
  }
  return requisitarBackendNFSE(path, { method: 'POST', body: JSON.stringify(payload) });
}

async function salvarNotaLancadaBackend(item, arquivoOrigem = '') {
  const payload = {
      id: item.id,
      source: 'json',
      status: item.status || 'PENDENTE',
      entidadeTipo: item.entidadeTipo || item.localTipo || 'agencia',
      entidadeId: item.entidadeId || item.entidade_id || '',
      origem: item.origem || 'manual',
      arquivoOrigem,
      dados: {
        ...item,
        valorTotal: Number(item.valor || item.valorTotal || 0),
      },
  };
  try {
    const body = await enviarDocumentoNFSE('/api/notas/lancadas', payload);
    const mapped = mapBackendNFSE(body.item);
    // Recorrência: a API atualizou a nota do mesmo mês; a informação segue para a tela avisar o usuário.
    if (body.item?.recorrencia) mapped.recorrencia = body.item.recorrencia;
    return { ...body, item: mapped };
  } catch (error) {
    if (error.status !== 409) throw error;
    const existing = (await listarNotasBackendNFSE()).filter((candidate) => (
      candidate.entidadeId === payload.entidadeId
      && candidate.localTipo === payload.entidadeTipo
      && (
        payload.dados.chave
          ? candidate.chave.trim().toLowerCase() === String(payload.dados.chave).trim().toLowerCase()
          : candidate.numero === payload.dados.numero
            && candidate.serie === payload.dados.serie
            && candidate.provedorNome.trim().toLowerCase() === String(payload.dados.provedorNome || '').trim().toLowerCase()
            && String(candidate.dataEmissao || '').slice(0, 10) === String(payload.dados.dataEmissao || '').slice(0, 10)
      )
    ));
    if (existing.length !== 1) throw error;
    const candidate = existing[0];
    const sameRecord = (
      candidate.numero === String(payload.dados.numero || '').trim()
      && candidate.serie === String(payload.dados.serie || '').trim()
      && candidate.provedorNome.trim().toLowerCase() === String(payload.dados.provedorNome || '').trim().toLowerCase()
      && Math.abs(Number(candidate.valor || 0) - Number(payload.dados.valorTotal || 0)) < 0.01
    );
    if (!sameRecord) throw error;
    return { ok: true, item: candidate, via: 'api', duplicataReutilizada: true };
  }
}

async function salvarNotaPagaBackend(item, pagamento = {}) {
  const payload = {
      id: pagamento.id || item.id,
      notaLancadaId: pagamento.notaLancadaId || '',
      source: 'json',
      status: pagamento.status || 'PAGA',
      valorPago: Number(pagamento.valorPago ?? item.valorPago ?? item.valor ?? 0),
      dataPagamento: pagamento.dataPagamento || item.dataPagamento || '',
      entidadeTipo: item.entidadeTipo || item.localTipo || 'agencia',
      entidadeId: item.entidadeId || item.entidade_id || '',
      origem: pagamento.origem || item.origem || 'manual',
      arquivoOrigem: pagamento.arquivoOrigem || item.arquivoOrigem || '',
      dados: {
        ...item,
        valorTotal: Number(item.valor || item.valorTotal || 0),
        localCidade: pagamento.localCidade || item.localCidade || '',
      },
  };
  try {
    const body = await enviarDocumentoNFSE('/api/notas/pagas', payload);
    return { ...body, item: mapBackendNFSE(body.item) };
  } catch (error) {
    if (error.status !== 409) throw error;
    const existing = (await listarNotasBackendNFSE('pagas')).filter((candidate) => (
      candidate.entidadeId === payload.entidadeId
      && candidate.localTipo === payload.entidadeTipo
      && (
        payload.dados.chave
          ? candidate.chave.trim().toLowerCase() === String(payload.dados.chave).trim().toLowerCase()
          : candidate.numero === payload.dados.numero
            && candidate.serie === payload.dados.serie
            && candidate.provedorNome.trim().toLowerCase() === String(payload.dados.provedorNome || '').trim().toLowerCase()
      )
      && String(candidate.dataPagamento || '').slice(0, 10) === String(payload.dataPagamento || '').slice(0, 10)
      && Math.abs(Number(candidate.valorPago || 0) - payload.valorPago) < 0.01
    ));
    if (existing.length !== 1) throw error;
    return { ok: true, item: existing[0], via: 'api', duplicataReutilizada: true };
  }
}

async function conciliarNotasBackendNFSE(notaLancadaId, notaPagaId) {
  return requisitarBackendNFSE('/api/notas/conciliar', {
    method: 'POST',
    body: JSON.stringify({ notaLancadaId, notaPagaId }),
  });
}

const SIGP_NFSE_API = {
  NFSE_STORAGE_KEY,
  NFSE_EVENTOS,
  loadNFSE,
  saveNFSE,
  normalizarNFSE,
  criarNFSE,
  atualizarNFSE,
  excluirNFSE,
  importarNotaManual,
  importarNotaArquivo,
  registrarPagamentoNFSE,
  buildNFSEEvent,
  emitirNFSE,
  sincronizarBackendNFSE,
  getNFSEBackendUrl,
  mapBackendNFSE,
  listarNotasBackendNFSE,
  salvarNotaLancadaBackend,
  salvarNotaPagaBackend,
  conciliarNotasBackendNFSE,
};

if (typeof globalThis !== 'undefined') {
  globalThis.SIGP_NFSE = SIGP_NFSE_API;
}

if (typeof window !== 'undefined') {
  window.SIGP_NFSE = SIGP_NFSE_API;
}
