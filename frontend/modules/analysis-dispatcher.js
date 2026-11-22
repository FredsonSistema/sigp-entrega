(() => {
  const apiUrl = () => window.SIGP_NFSE.getNFSEBackendUrl().replace(/\/$/, '');

  async function readApi(path) {
    const response = await fetch(`${apiUrl()}${path}`);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `API respondeu HTTP ${response.status}`);
    return body;
  }

  function sameEntity(note, local) {
    return note.localTipo === local.tipo && note.entidadeId === String(local.id || '');
  }

  function sameIdentity(left, right) {
    const leftKey = String(left.chave || '').trim().toLowerCase();
    const rightKey = String(right.chave || '').trim().toLowerCase();
    if (leftKey && rightKey) return leftKey === rightKey;
    return String(left.numero || '').trim() === String(right.numero || '').trim()
      && String(left.serie || '').trim() === String(right.serie || '').trim()
      && String(left.provedorNome || '').trim().toLowerCase() === String(right.provedorNome || '').trim().toLowerCase()
      && String(left.dataEmissao || '').slice(0, 10) === String(right.dataEmissao || '').slice(0, 10);
  }

  function workflowNote(note, local) {
    const servicos = Array.isArray(note.servicos) ? note.servicos : [];
    return {
      id: note.id,
      chave: note.chave || '',
      numero: note.numero || '',
      serie: note.serie || '',
      provedor_nome: note.provedorNome || '',
      descricao: servicos.map((service) => String(service.descricao || '').trim()).filter(Boolean).join('; ')
        || String(note.descricao || '').trim(),
      servicos: servicos.map((service) => ({
        descricao: String(service.descricao || '').trim(),
        valor: Number(service.valorTotal || 0),
      })).filter((service) => service.descricao),
      entidade_tipo: note.localTipo || local.tipo,
      entidade_id: note.entidadeId || String(local.id || ''),
      local_nome: note.localNome || local.nome || '',
      local_cidade: note.localCidade || local.cidade || '',
      valor_total: Number(note.valor || 0),
      valor_pago: Number(note.valorPago || 0),
      data_emissao: note.dataEmissao || '',
      data_vencimento: note.dataVencimento || '',
      data_pagamento: note.dataPagamento || '',
      status: note.status || 'PENDENTE',
    };
  }

  function invoiceComparisons(invoice) {
    const comparisons = invoice?.dados?.comparacao || {};
    return Object.entries(comparisons)
      .filter(([, result]) => result === false)
      .map(([field]) => field);
  }

  async function enviar({ notaLancada, notaPaga = null, fatura = null, local = {}, aceitarDivergencia = false }) {
    if (!window.SIGP_API?.enviarAnaliseManual) throw new Error('Integração manual com n8n indisponível.');
    if (!local.id || !local.tipo) throw new Error('Salve o cadastro do local antes de enviar a análise.');
    if (!notaLancada && fatura?.nota_lancada_id) {
      const notes = await window.SIGP_NFSE.listarNotasBackendNFSE();
      notaLancada = notes.find((note) => note.id === fatura.nota_lancada_id) || null;
    }

    let savedLaunch = null;
    if (notaLancada) {
      const launchedPayload = {
        ...notaLancada,
        entidadeTipo: local.tipo,
        entidadeId: String(local.id),
        localTipo: local.tipo,
        localNome: local.nome || notaLancada.localNome,
        localCidade: local.cidade || notaLancada.localCidade,
      };
      const launched = await window.SIGP_NFSE.salvarNotaLancadaBackend(launchedPayload);
      savedLaunch = launched.item;
    } else if (!fatura) {
      throw new Error('Informe uma nota lançada ou uma fatura PDF para analisar.');
    }

    let savedPayment = null;
    if (notaPaga && savedLaunch) {
      const paid = await window.SIGP_NFSE.salvarNotaPagaBackend({
        ...notaPaga,
        entidadeTipo: local.tipo,
        entidadeId: String(local.id),
        localTipo: local.tipo,
        localNome: local.nome || notaPaga.localNome,
        localCidade: local.cidade || notaPaga.localCidade,
      }, {
        id: notaPaga.id,
        valorPago: notaPaga.valorPago || notaPaga.valor,
        dataPagamento: notaPaga.dataPagamento,
        notaLancadaId: savedLaunch.id,
      });
      savedPayment = paid.item;
    } else {
      const payments = await window.SIGP_NFSE.listarNotasBackendNFSE('pagas');
      savedPayment = payments.find((note) => (
        savedLaunch && sameEntity(note, local) && sameIdentity(note, savedLaunch)
      )) || null;
    }

    if (!fatura) {
      const response = await readApi('/api/faturas');
      fatura = (response.items || []).find((item) => item.nota_lancada_id === savedLaunch.id) || null;
    }

    let reconciliation = null;
    if (savedPayment) {
      const response = await fetch(`${apiUrl()}/api/notas/conciliar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notaLancadaId: savedLaunch.id, notaPagaId: savedPayment.id }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `Conciliação respondeu HTTP ${response.status}`);
      reconciliation = body;
    }

    const differences = invoiceComparisons(fatura);
    const status = differences.length
      ? 'DIVERGENCIA'
      : reconciliation?.status || (savedPayment && savedLaunch ? 'AGUARDANDO_FATURA' : 'PENDENTE');
    const diverged = status === 'DIVERGENCIA' || differences.length > 0;
    let aceitaDivergencia = Boolean(aceitarDivergencia);
    if (diverged) {
      const details = [
        reconciliation?.resultado?.observacao || '',
        differences.length ? `Fatura: ${differences.join(', ')}.` : '',
      ].filter(Boolean).join('\n');
      if (!aceitarDivergencia) {
        aceitaDivergencia = window.confirm(
          `Foram encontradas divergências nesta análise.\n\n${details || 'A conciliação não confere.'}\n\nDeseja enviar mesmo assim para análise manual?`,
        );
      }
      if (!aceitaDivergencia) return { cancelled: true, status };
    }

    const invoiceData = fatura ? {
      id: fatura.id,
      nome_arquivo: fatura.nome_arquivo,
      dados: fatura.dados || {},
    } : null;
    const accumulatedPaid = savedLaunch
      ? (await window.SIGP_NFSE.listarNotasBackendNFSE('pagas'))
        .filter((note) => sameEntity(note, local) && sameIdentity(note, savedLaunch))
        .reduce((total, note) => total + Number(note.valorPago || 0), 0)
      : 0;
    const invoiceDocument = savedLaunch || {
      id: `fatura-${fatura.id}`,
      chave: `fatura-${fatura.id}`,
      numero: fatura.dados?.numeroFatura || 'PDF sem nota vinculada',
      serie: '',
      provedorNome: fatura.dados?.emissorNome || '',
      localTipo: local.tipo,
      entidadeId: String(local.id),
      localNome: local.nome || '',
      localCidade: local.cidade || '',
      valor: Number(fatura.dados?.valorTotal || 0),
      dataEmissao: fatura.dados?.dataEmissao || '',
      dataVencimento: fatura.dados?.dataVencimento || '',
      status: 'PENDENTE',
    };
    const result = await window.SIGP_API.enviarAnaliseManual({
      status,
      notaLancada: workflowNote(invoiceDocument, local),
      notaPaga: savedPayment ? workflowNote(savedPayment, local) : {},
      fatura: invoiceData,
      valorPagoAcumulado: accumulatedPaid,
      comparacao: invoiceData?.dados?.comparacao || {},
      observacao: reconciliation?.resultado?.observacao
        || (!savedLaunch ? 'PDF encaminhado sem nota lançada vinculada; exige revisão manual.' : ''),
      aceitaDivergencia,
      local: { tipo: local.tipo, nome: local.nome || '', cidade: local.cidade || '' },
      origem: 'interface',
    });
    return { ok: true, status, aceitaDivergencia, result };
  }

  window.SIGP_ANALISE = { enviar };
})();
