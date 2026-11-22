const SIGP_DOCUMENT_STATUS = {
  PENDENTE: 'PENDENTE',
  RECEBIDA: 'RECEBIDA',
  DIVERGENCIA: 'DIVERGENCIA',
  DIVERGENCIA_CADASTRAL: 'DIVERGENCIA_CADASTRAL',
  NAO_ENCONTRADA: 'NAO_ENCONTRADA',
  PAGA: 'PAGA',
  PARCIAL: 'PARCIAL',
  VENCIDA: 'VENCIDA',
};

const SIGP_ITEM_STATUS = {
  PENDENTE: 'PENDENTE',
  PAGO: 'PAGO',
  PAGAMENTO_PARCIAL: 'PAGAMENTO_PARCIAL',
  DIVERGENTE: 'DIVERGENTE',
  ATUALIZAR: 'ATUALIZAR',
  EXPIRADO: 'EXPIRADO',
};

const SIGP_LOCAL_TIPOS = ['agencia', 'rodoviaria', 'garagem', 'local', 'outro'];

function normalizarLocalTipo(localTipo) {
  const valor = String(localTipo || '').trim().toLowerCase();
  return SIGP_LOCAL_TIPOS.includes(valor) ? valor : 'agencia';
}

function criarDocumentoBase(payload = {}) {
  const id = payload.id || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));
  const valorTotal = Number(payload.valorTotal ?? payload.valor ?? 0);
  const valorPago = Number(payload.valorPago ?? 0);

  return {
    id,
    tipoDocumento: String(payload.tipoDocumento || payload.tipo || 'NFSE').trim() || 'NFSE',
    origem: String(payload.origem || 'SIGP').trim() || 'SIGP',
    provedorNome: String(payload.provedorNome || '').trim(),
    chave: String(payload.chave || '').trim(),
    numero: String(payload.numero || '').trim(),
    serie: String(payload.serie || '').trim(),
    valorTotal: Number.isFinite(valorTotal) ? valorTotal : 0,
    valorPago: Number.isFinite(valorPago) ? valorPago : 0,
    dataEmissao: payload.dataEmissao || '',
    dataVencimento: payload.dataVencimento || '',
    status: payload.status || SIGP_DOCUMENT_STATUS.PENDENTE,
    observacao: String(payload.observacao || '').trim(),
    arquivoOrigem: payload.arquivoOrigem || '',
    localTipo: normalizarLocalTipo(payload.localTipo || payload.local_tipo || payload.localTipoDocumento),
    localNome: String(payload.localNome || '').trim(),
    localCidade: String(payload.localCidade || '').trim(),
    criadoEm: payload.criadoEm || new Date().toISOString(),
    atualizadoEm: payload.atualizadoEm || new Date().toISOString(),
  };
}

function criarItemDocumento(documentoId, payload = {}) {
  const valor = Number(payload.valor ?? 0);
  const idBase = payload.id || `${documentoId}-item-${Date.now()}`;

  return {
    id: idBase,
    documentoId,
    localTipo: normalizarLocalTipo(payload.localTipo || payload.local_tipo),
    localId: String(payload.localId || '').trim(),
    localNome: String(payload.localNome || '').trim(),
    localCidade: String(payload.localCidade || '').trim(),
    valor: Number.isFinite(valor) ? valor : 0,
    status: payload.status || SIGP_ITEM_STATUS.PENDENTE,
    observacao: String(payload.observacao || '').trim(),
    dataVencimento: payload.dataVencimento || '',
    dataPagamento: payload.dataPagamento || '',
  };
}

function normalizarItensDocumento(documentoId, itens = []) {
  if (!Array.isArray(itens) || !itens.length) {
    return [criarItemDocumento(documentoId, { localTipo: 'agencia', localNome: '', localCidade: '', valor: 0, status: SIGP_ITEM_STATUS.PENDENTE })];
  }

  return itens.map((item, index) => {
    const itemPayload = typeof item === 'object' && item ? item : {};
    return criarItemDocumento(documentoId, {
      ...itemPayload,
      id: itemPayload.id || `${documentoId}-item-${index + 1}`,
      valor: itemPayload.valor ?? itemPayload.total ?? 0,
      localTipo: itemPayload.localTipo || itemPayload.local_tipo || 'agencia',
    });
  });
}

function buildDocumentoContract(payload = {}, itens = []) {
  const documento = criarDocumentoBase(payload);
  const listaItens = normalizarItensDocumento(documento.id, itens.length ? itens : [{
    localTipo: documento.localTipo,
    localNome: documento.localNome,
    localCidade: documento.localCidade,
    valor: documento.valorTotal,
    status: documento.status,
    observacao: documento.observacao,
    dataVencimento: documento.dataVencimento,
  }]);

  const totalItens = listaItens.reduce((acc, item) => acc + Number(item.valor || 0), 0);

  return {
    versao: 2,
    evento: payload.evento || 'documento_recebido',
    timestamp: new Date().toISOString(),
    documento,
    itens: listaItens,
    resumo: {
      totalItens: listaItens.length,
      totalValor: Number.isFinite(totalItens) ? totalItens : 0,
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
      valor: documento.valorTotal,
      valorTotal: documento.valorTotal,
      dataEmissao: documento.dataEmissao,
      dataVencimento: documento.dataVencimento,
      observacao: documento.observacao,
      status: documento.status,
    },
  };
}

function validarDocumentoContract(payload = {}) {
  const errors = [];
  const documento = criarDocumentoBase(payload);

  if (!documento.chave && !documento.numero) {
    errors.push('Informe chave ou número do documento.');
  }

  if (!documento.provedorNome) {
    errors.push('Informe o nome do provedor.');
  }

  if (!documento.localNome && !documento.localCidade) {
    errors.push('Informe local ou cidade da operação.');
  }

  if (documento.valorTotal <= 0) {
    errors.push('O valor do documento precisa ser maior que zero.');
  }

  return {
    ok: errors.length === 0,
    documento,
    errors,
  };
}

if (typeof window !== 'undefined') {
  window.SIGP_DOCUMENTOS = {
    SIGP_DOCUMENT_STATUS,
    SIGP_ITEM_STATUS,
    SIGP_LOCAL_TIPOS,
    normalizarLocalTipo,
    criarDocumentoBase,
    criarItemDocumento,
    normalizarItensDocumento,
    buildDocumentoContract,
    validarDocumentoContract,
  };
}
