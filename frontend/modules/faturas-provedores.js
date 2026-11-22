(() => {
  const WEBHOOK_KEY = 'sigp_fatura_pdf_webhook_url';
  const MAX_FILE_SIZE = 15 * 1024 * 1024;
  const DEFAULT_ID = '999999999'; // mesmo valor padrão do backend (backend/campos.py)
  let selectedFile = null;
  let selectedNota = null;
  let selectedProvider = null;
  let selectedEntity = null;
  let extractionResult = null;
  let onSaved = null;
  let storedEntities = [];

  const byId = (id) => document.getElementById(id);

  function backendUrl() {
    return window.SIGP_NFSE.getNFSEBackendUrl().replace(/\/$/, '');
  }

  function setBusy(busy, message = '') {
    byId('faturaPdfExtrair').disabled = busy;
    byId('faturaPdfSalvar').disabled = busy || !extractionResult;
    byId('faturaPdfStatus').textContent = message;
  }

  function compareText(expected, actual) {
    const normalize = (value) => String(value || '')
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .toLocaleLowerCase('pt-BR').replace(/[^a-z0-9]/g, '');
    const left = normalize(expected);
    const right = normalize(actual);
    return Boolean(left && right && (left.includes(right) || right.includes(left)));
  }

  function renderComparisons() {
    const expectedProvider = byId('faturaPdfProvedorEsperado').value.trim();
    const expectedAmount = Number(selectedNota?.valor || selectedProvider?.valor || 0);
    const expectedDue = selectedNota?.dataVencimento || selectedProvider?.dataVencimento || '';
    const issuer = byId('faturaPdfEmissor').value.trim();
    const amountValue = byId('faturaPdfValor').value.trim();
    const amount = Number(amountValue);
    const due = byId('faturaPdfVencimento').value;
    const checks = [
      !expectedProvider
        ? 'Emissor sem provedor de referência'
        : !issuer
          ? 'Emissor aguardando extração ou preenchimento'
          : `Emissor ${compareText(expectedProvider, issuer) ? 'confere' : `diverge (${expectedProvider})`}`,
      expectedAmount <= 0
        ? 'Valor sem nota de referência'
        : !amountValue || !Number.isFinite(amount)
          ? 'Valor aguardando extração ou preenchimento'
          : `Valor ${Math.abs(expectedAmount - amount) < 0.01 ? 'confere' : `diverge (${expectedAmount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })})`}`,
      !expectedDue
        ? 'Vencimento sem nota de referência'
        : !due
          ? 'Vencimento aguardando extração ou preenchimento'
          : `Vencimento ${expectedDue === due ? 'confere' : `diverge do cadastro (${expectedDue})`}`,
    ];
    byId('faturaPdfComparacao').textContent = checks.join(' · ');
  }

  function fillExtractedFields(result) {
    const candidates = Array.isArray(result.cnpjCandidatos) ? result.cnpjCandidatos : [];
    byId('faturaPdfEmissor').value = result.emissorNome || '';
    byId('faturaPdfCnpj').value = result.cnpjEmissor || (candidates.length === 1 ? candidates[0] : '');
    byId('faturaPdfNumero').value = result.numeroFatura || '';
    byId('faturaPdfEmissao').value = result.dataEmissao || '';
    byId('faturaPdfVencimento').value = result.dataVencimento || '';
    byId('faturaPdfValor').value = result.valorTotal ?? '';
    byId('faturaPdfDescricao').value = result.descricaoServico
      || (selectedNota?.servicos || []).map((service) => String(service.descricao || '').trim()).filter(Boolean).join('; ')
      || '';
    byId('faturaPdfCnpjCandidatos').textContent = candidates.length
      ? `CNPJs encontrados no PDF: ${candidates.join(', ')}. Confira qual pertence ao emissor.`
      : 'Nenhum CNPJ foi reconhecido; confira o documento antes de salvar.';
    byId('faturaPdfReview').hidden = false;
    byId('faturaPdfSalvar').disabled = false;
    renderComparisons();
  }

  function resetModal() {
    selectedFile = null;
    extractionResult = null;
    byId('faturaPdfFile').value = '';
    byId('faturaPdfFileName').textContent = 'Selecione a fatura PDF do provedor.';
    byId('faturaPdfReview').hidden = true;
    byId('faturaPdfConfirmarEmissor').checked = false;
    byId('faturaPdfDescricao').value = '';
    byId('faturaPdfStatus').textContent = '';
    byId('faturaPdfSalvar').disabled = true;
  }

  function open(nota, savedCallback) {
    selectedNota = nota;
    selectedProvider = null;
    selectedEntity = {
      tipo: nota.entidade_tipo || nota.localTipo || 'agencia',
      id: nota.entidade_id || nota.entidadeId || '',
      nome: nota.localNome || '',
      cidade: nota.localCidade || '',
    };
    onSaved = savedCallback;
    resetModal();
    byId('faturaPdfSalvar').textContent = 'Salvar fatura';
    byId('faturaPdfTitle').textContent = `Anexar fatura · ${nota.provedorNome || nota.chave || nota.numero || 'nota'}`;
    byId('faturaPdfProvedorEsperado').value = nota.provedorNome || '';
    byId('faturaPdfOverlay').classList.add('open');
  }

  function openForEntity(entity, nota, savedCallback) {
    selectedEntity = entity;
    selectedNota = nota || null;
    selectedProvider = null;
    onSaved = savedCallback;
    resetModal();
    byId('faturaPdfSalvar').textContent = 'Salvar fatura';
    byId('faturaPdfTitle').textContent = `Anexar fatura · ${entity.nome}`;
    byId('faturaPdfProvedorEsperado').value = nota?.provedorNome || entity.provedorEsperado || '';
    byId('faturaPdfOverlay').classList.add('open');
  }

  function openForProvider(entity, provider, savedCallback) {
    selectedEntity = entity;
    selectedNota = null;
    selectedProvider = provider;
    onSaved = savedCallback;
    resetModal();
    byId('faturaPdfTitle').textContent = `Anexar fatura · ${provider.nome || 'novo provedor'} · ${entity.nome || 'local'}`;
    byId('faturaPdfProvedorEsperado').value = provider.nome || '';
    byId('faturaPdfSalvar').textContent = 'Associar ao provedor';
    byId('faturaPdfOverlay').classList.add('open');
  }

  function close() {
    byId('faturaPdfOverlay').classList.remove('open');
    selectedFile = null;
    selectedNota = null;
    selectedProvider = null;
    selectedEntity = null;
    extractionResult = null;
  }

  async function extract() {
    const file = selectedFile;
    const endpoint = window.SIGP_CONFIG.webhookUrl('webhookFaturaPdf');
    if (!file) {
      setBusy(false, 'Selecione uma fatura PDF.');
      return;
    }
    if (!endpoint) {
      setBusy(false, 'Configure primeiro a URL do webhook de extração do n8n.');
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      setBusy(false, 'O PDF excede o limite de 15 MiB.');
      return;
    }

    const signature = new Uint8Array(await file.slice(0, 5).arrayBuffer());
    if (String.fromCharCode(...signature) !== '%PDF-') {
      setBusy(false, 'O arquivo selecionado não parece ser um PDF válido.');
      return;
    }

    setBusy(true, 'Enviando a fatura ao n8n para extração local...');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 450000);
    try {
      const url = new URL(endpoint);
      url.searchParams.set('entidadeTipo', selectedEntity.tipo);
      url.searchParams.set('entidadeId', selectedEntity.id || '');
      url.searchParams.set('localNome', selectedEntity.nome || '');
      url.searchParams.set('localCidade', selectedEntity.cidade || '');
      url.searchParams.set('provedorEsperado', byId('faturaPdfProvedorEsperado').value.trim());
      if (selectedProvider) {
        url.searchParams.set('provedorId', selectedProvider.id || '');
        url.searchParams.set('valorEsperado', String(selectedProvider.valor || 0));
        url.searchParams.set('vencimentoEsperado', selectedProvider.dataVencimento || '');
      }
      if (selectedNota) {
        url.searchParams.set('notaId', selectedNota.id);
        url.searchParams.set('valorEsperado', String(selectedNota.valor || 0));
        url.searchParams.set('vencimentoEsperado', selectedNota.dataVencimento || '');
      }
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/pdf' },
        body: file,
        signal: controller.signal,
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(result?.error || result?.message || `n8n respondeu HTTP ${response.status}`);
      }
      if (!result || result.ok !== true) {
        throw new Error(result?.error || 'O n8n não conseguiu extrair os dados da fatura.');
      }
      extractionResult = result;
      fillExtractedFields(result);
      setBusy(false, result.textEncontrado === false
        ? 'Não foi possível reconhecer texto no PDF, mesmo após o OCR local. Confira e preencha os campos manualmente.'
        : result.ocrUsado
          ? 'OCR local aplicado. Confira e corrija os campos antes de salvar.'
          : 'Texto extraído do PDF. Confira e corrija os campos antes de salvar.');
    } catch (error) {
      setBusy(false, error.name === 'AbortError'
        ? 'A extração excedeu 450 segundos. Verifique o n8n e tente novamente.'
        : `Falha ao extrair a fatura: ${error.message || 'erro de conexão'}`);
    } finally {
      clearTimeout(timeout);
    }
  }

  // Faturas anexadas a um local ainda não salvo, indexadas pelo id da linha do provedor.
  const pendentes = new Map();

  async function postInvoice({ file, dados, entityTipo, entityId, noteId = '', providerId = '', expectedProvider = '' }) {
    const form = new FormData();
    form.append('arquivo', file, file.name);
    form.append('dadosExtracao', JSON.stringify(dados));
    form.append('entidadeTipo', entityTipo);
    form.append('entidadeId', entityId);
    form.append('notaLancadaId', noteId);
    form.append('provedorId', providerId);
    form.append('provedorEsperado', expectedProvider);
    const response = await fetch(`${backendUrl()}/api/faturas`, { method: 'POST', body: form });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || `API respondeu HTTP ${response.status}`);
    return result.item || result.fatura;
  }

  const hasPending = (providerRowId) => pendentes.has(String(providerRowId || ''));

  // Envia a fatura pendente depois que o local foi salvo. Mantém o pendente se o envio falhar.
  async function uploadPending(providerRowId, entity) {
    const key = String(providerRowId || '');
    const pending = pendentes.get(key);
    if (!pending) return null;
    const invoice = await postInvoice({
      file: pending.file,
      dados: pending.dados,
      entityTipo: entity.tipo,
      entityId: entity.id,
      providerId: key,
      expectedProvider: pending.expectedProvider,
    });
    pendentes.delete(key);
    return invoice;
  }

  async function save() {
    if (!selectedFile || !selectedEntity || !extractionResult) return;
    if (!byId('faturaPdfConfirmarEmissor').checked) {
      setBusy(false, 'Confirme que revisou o emissor e os dados extraídos do PDF.');
      return;
    }

    // C2: o provedor pode estar sem nome; nesse caso vale o emissor extraído e revisado.
    const expectedProvider = byId('faturaPdfProvedorEsperado').value.trim() || byId('faturaPdfEmissor').value.trim();
    const dados = {
      emissorNome: byId('faturaPdfEmissor').value.trim(),
      cnpjEmissor: byId('faturaPdfCnpj').value.trim(),
      numeroFatura: byId('faturaPdfNumero').value.trim(),
      dataEmissao: byId('faturaPdfEmissao').value,
      dataVencimento: byId('faturaPdfVencimento').value,
      valorTotal: Number(byId('faturaPdfValor').value || 0),
      descricao: byId('faturaPdfDescricao').value.trim()
        || (selectedNota?.servicos || []).map((service) => String(service.descricao || '').trim()).filter(Boolean).join('; '),
      cnpjCandidatos: extractionResult.cnpjCandidatos || [],
      dataEmissaoOrigem: byId('faturaPdfEmissao').value ? 'documento' : 'recebimento',
      numeroPadrao: false,
      origemExtracao: 'n8n_pdf',
      emissorConfirmado: true,
      extraidoEm: new Date().toISOString(),
    };
    if (!dados.emissorNome || !dados.dataVencimento || !Number.isFinite(dados.valorTotal) || dados.valorTotal <= 0) {
      setBusy(false, 'Preencha o emissor, o vencimento e um valor maior que zero (obrigatórios; o OCR não os identificou).');
      return;
    }
    // Mesmas regras do Gmail: número vazio ou inválido vale o padrão; emissão vazia vale a data de recebimento (hoje).
    if (!/\d/.test(dados.numeroFatura) || /^\d{2}[/.-]\d{2}[/.-]\d{4}$|^\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}$/.test(dados.numeroFatura)) {
      if (dados.numeroFatura) dados.numeroOriginal = dados.numeroFatura;
      dados.numeroFatura = DEFAULT_ID;
      dados.numeroPadrao = true;
    }
    if (!dados.dataEmissao) {
      const today = new Date();
      dados.dataEmissao = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    }

    const differences = [
      expectedProvider && dados.emissorNome && !compareText(expectedProvider, dados.emissorNome) ? 'emissor' : '',
      Number(selectedNota?.valor || selectedProvider?.valor || 0) > 0
        && Math.abs(Number(selectedNota?.valor || selectedProvider?.valor || 0) - dados.valorTotal) >= 0.01 ? 'valor' : '',
      (selectedNota?.dataVencimento || selectedProvider?.dataVencimento)
        && (selectedNota?.dataVencimento || selectedProvider?.dataVencimento) !== dados.dataVencimento ? 'vencimento' : '',
    ].filter(Boolean);
    let aceitarDivergencia = false;
    if (differences.length) {
      aceitarDivergencia = window.confirm(
        `A fatura apresenta divergência em: ${differences.join(', ')}.\n\nOK = aceitar a divergência, salvar e enviar ao n8n para análise manual.\nCancelar = não salvar a fatura.`,
      );
      if (!aceitarDivergencia) {
        setBusy(false, 'Fatura não salva. A divergência foi recusada.');
        return;
      }
    }

    setBusy(true, 'Salvando a fatura e os dados revisados no backend...');
    try {
      let canonicalNoteId = '';
      if (selectedNota) {
        const savedNote = await window.SIGP_NFSE.salvarNotaLancadaBackend({
          ...selectedNota,
          entidadeTipo: selectedEntity.tipo,
          entidadeId: String(selectedEntity.id || ''),
          localTipo: selectedEntity.tipo,
          localNome: selectedEntity.nome || selectedNota.localNome,
          localCidade: selectedEntity.cidade || selectedNota.localCidade,
        });
        canonicalNoteId = savedNote.item.id;
        selectedNota = { ...selectedNota, ...savedNote.item, id: canonicalNoteId };
      }
      if (!selectedEntity.id) {
        // C2: local ainda não salvo. Os campos já preenchem a linha do provedor; o PDF e a extração
        // ficam pendentes e são enviados à API quando o cadastro do local for salvo.
        const providerRowId = String(selectedProvider?.id || '');
        if (!providerRowId) throw new Error('Não foi possível identificar a linha do provedor.');
        pendentes.set(providerRowId, { file: selectedFile, dados, expectedProvider });
        setBusy(false, 'Fatura associada ao provedor. O PDF será enviado quando o local for salvo.');
        if (typeof onSaved === 'function') {
          await onSaved({ id: `pendente-${providerRowId}`, pendente: true, nome_arquivo: selectedFile.name, dados });
        }
        setTimeout(close, 600);
        return;
      }
      const savedInvoice = await postInvoice({
        file: selectedFile,
        dados,
        entityTipo: selectedEntity.tipo,
        entityId: selectedEntity.id,
        noteId: canonicalNoteId,
        providerId: selectedProvider?.id || '',
        expectedProvider,
      });
      // A API já atualizou o provedor do local; traz o resultado para o cadastro do navegador.
      // No modal do provedor (local aberto), a linha da tela é atualizada pelo onSaved logo abaixo.
      if (!selectedProvider) {
        await window.SIGP_API.refreshLocationProviders(selectedEntity.tipo, selectedEntity.id).catch(() => false);
      }
      const comparisonStatus = savedInvoice?.dados?.statusComparacao;
      const comparison = savedInvoice?.dados?.comparacao || {};
      const divergencias = [
        comparison.emissorConfere === false ? 'emissor' : '',
        comparison.valorConfere === false ? 'valor' : '',
        comparison.vencimentoConfere === false ? 'vencimento' : '',
      ].filter(Boolean);
      const message = divergencias.length
        ? `Fatura salva e vinculada ao local. Divergência(s) a revisar: ${divergencias.join(', ')}.`
        : comparisonStatus === 'SEM_REFERENCIA'
          ? 'Fatura salva e vinculada ao local. Há informações sem referência para comparação; confira o histórico.'
          : 'Fatura salva e vinculada ao local; comparações concluídas.';
      let finalMessage = message;
      if (aceitarDivergencia && selectedNota) {
        try {
          const analysis = await window.SIGP_ANALISE.enviar({
            notaLancada: selectedNota,
            fatura: savedInvoice,
            local: selectedEntity,
            aceitarDivergencia: true,
          });
          finalMessage += analysis.ok ? ' Análise manual enviada ao n8n.' : '';
        } catch (error) {
          finalMessage += ` A fatura foi salva, mas a análise não foi enviada: ${error.message || 'erro de conexão'}`;
        }
      }
      setBusy(false, finalMessage);
      if (typeof onSaved === 'function') await onSaved(savedInvoice);
      setTimeout(close, 900);
    } catch (error) {
      setBusy(false, `Não foi possível salvar a fatura: ${error.message || 'erro de conexão'}`);
    }
  }

  function init() {
    document.body.insertAdjacentHTML('beforeend', `
      <div class="overlay" id="faturaPdfOverlay">
        <div class="modal" style="max-width:760px; width:100%">
          <h2 id="faturaPdfTitle">Anexar fatura</h2>
          <p class="hint">O PDF é enviado ao webhook configurado do n8n e uma cópia fica armazenada no SIGp. Com o webhook apontando para o n8n auto-hospedado deste projeto, o texto e o OCR são processados localmente, sem serviço externo. Se ainda não houver texto reconhecido, confira e preencha os campos manualmente; divergências com a referência serão sinalizadas antes e depois de salvar.</p>
          <div style="margin:12px 0"><label>Provedor esperado para comparar a origem (opcional: se vazio, vale o emissor da fatura)</label><input class="f" id="faturaPdfProvedorEsperado" type="text" required></div>
          <div class="task-add-row" style="gap:8px; margin:12px 0">
            <input type="file" id="faturaPdfFile" accept="application/pdf,.pdf" hidden>
            <button class="ghost small" type="button" id="faturaPdfSelecionar">Selecionar PDF</button>
            <span class="hint" id="faturaPdfFileName">Selecione a fatura PDF do provedor.</span>
            <button class="primary small" type="button" id="faturaPdfExtrair">Extrair dados</button>
          </div>
          <section id="faturaPdfReview" hidden>
            <div class="nfse-grid">
              <div><label>Emissor / provedor</label><input class="f" id="faturaPdfEmissor" type="text"></div>
              <div><label>CNPJ do emissor (se reconhecido)</label><input class="f" id="faturaPdfCnpj" type="text"></div>
              <div><label>Número da fatura</label><input class="f" id="faturaPdfNumero" type="text"></div>
              <div><label>Data de emissão</label><input class="f" id="faturaPdfEmissao" type="date"></div>
              <div><label>Vencimento</label><input class="f" id="faturaPdfVencimento" type="date" required></div>
              <div><label>Valor da fatura (R$)</label><input class="f" id="faturaPdfValor" type="number" min="0.01" step="0.01" required></div>
              <div class="full"><label>Descrição do serviço (revise para o parecer experimental)</label><input class="f" id="faturaPdfDescricao" type="text" maxlength="1000" placeholder="Ex.: link principal de internet, 300 Mbps"></div>
              <div class="full"><div class="dash-empty" id="faturaPdfCnpjCandidatos"></div></div>
              <div class="full"><div class="dash-empty" id="faturaPdfComparacao"></div></div>
              <div class="full">
                <label style="display:flex; gap:8px; align-items:flex-start">
                  <input type="checkbox" id="faturaPdfConfirmarEmissor" style="width:auto; margin-top:3px">
                  Revisei no PDF o emissor e os dados extraídos.
                </label>
              </div>
            </div>
          </section>
          <div id="faturaPdfStatus" class="hint" style="margin-top:10px; min-height:20px"></div>
          <div class="modal-actions">
            <div class="right">
              <button class="ghost" type="button" id="faturaPdfCancelar">Cancelar</button>
              <button class="primary" type="button" id="faturaPdfSalvar" disabled>Salvar fatura</button>
            </div>
          </div>
        </div>
      </div>`);

    byId('faturaPdfSelecionar').onclick = () => byId('faturaPdfFile').click();
    byId('faturaPdfFile').onchange = () => {
      selectedFile = byId('faturaPdfFile').files?.[0] || null;
      extractionResult = null;
      byId('faturaPdfReview').hidden = true;
      byId('faturaPdfSalvar').disabled = true;
      byId('faturaPdfFileName').textContent = selectedFile?.name || 'Selecione a fatura PDF do provedor.';
      byId('faturaPdfStatus').textContent = '';
    };
    byId('faturaPdfExtrair').onclick = extract;
    byId('faturaPdfSalvar').onclick = save;
    byId('faturaPdfCancelar').onclick = close;
    byId('faturaPdfOverlay').addEventListener('click', (event) => {
      if (event.target === byId('faturaPdfOverlay')) close();
    });
    ['faturaPdfProvedorEsperado', 'faturaPdfEmissor', 'faturaPdfValor', 'faturaPdfVencimento'].forEach((id) => {
      byId(id).addEventListener('input', renderComparisons);
      byId(id).addEventListener('change', renderComparisons);
    });

    byId('faturasWebhookUrl').value = window.SIGP_CONFIG.get('webhookFaturaPdf');
    byId('faturasSalvarWebhook').onclick = () => {
      const url = byId('faturasWebhookUrl').value.trim();
      if (url) {
        try {
          new URL(url);
        } catch (error) {
          byId('faturasStatus').textContent = 'Informe uma URL válida para o webhook do n8n.';
          return;
        }
      }
      window.SIGP_CONFIG.set({ webhookFaturaPdf: url });
      const settingsField = byId('nfse_fatura_webhook_url');
      if (settingsField) settingsField.value = url;
      byId('faturasStatus').textContent = url ? 'URL do webhook salva neste navegador.' : 'URL do webhook removida.';
    };
    byId('faturasAtualizar').onclick = renderTab;
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]);
  }

  function loadStoredEntities() {
    const configs = [
      { tipo: 'agencia', key: 'ti_agencias_v1' },
      { tipo: 'rodoviaria', key: 'ti_rodoviarias_v1' },
      { tipo: 'garagem', key: 'ti_garagens_v1' },
    ];
    storedEntities = configs.flatMap(({ tipo, key }) => {
      const records = JSON.parse(localStorage.getItem(key) || '[]');
      if (!Array.isArray(records)) throw new Error(`Cadastro de ${tipo} inválido no armazenamento local.`);
      return records.filter((record) => record?.id).map((record) => {
        return {
          tipo,
          id: String(record.id),
          nome: String(record.nome || 'Local sem nome'),
          cidade: String(record.cidade || ''),
          provedores: Array.isArray(record.provedores) ? record.provedores : [],
        };
      });
    });
  }

  function syncDeletedInvoiceProvider(invoice, history) {
    const storageKey = ({
      agencia: 'ti_agencias_v1',
      rodoviaria: 'ti_rodoviarias_v1',
      garagem: 'ti_garagens_v1',
    })[invoice.entidade_tipo];
    if (!storageKey) return;

    const records = JSON.parse(localStorage.getItem(storageKey) || '[]');
    const record = records.find((item) => String(item.id) === String(invoice.entidade_id));
    const providers = Array.isArray(record?.provedores) ? record.provedores : [];
    const providerName = String(invoice.provedor_nome || '').trim().toLocaleLowerCase('pt-BR');
    const sameProviderName = (item) => (
      String(item.provedor_nome || item.nome || '').trim().toLocaleLowerCase('pt-BR') === providerName
    );
    const provider = providers.find((item) => (
      invoice.provedor_id && String(item.id) === String(invoice.provedor_id)
    )) || providers.find((item) => (
      String(item.nome || '').trim().toLocaleLowerCase('pt-BR') === providerName
    ));
    if (!provider || String(provider.faturaAtualId || '') !== String(invoice.id)) return;

    const previous = history.find((item) => (
      String(item.id) !== String(invoice.id)
      && item.entidade_tipo === invoice.entidade_tipo
      && String(item.entidade_id) === String(invoice.entidade_id)
      && ((invoice.provedor_id && String(item.provedor_id || '') === String(invoice.provedor_id))
        || sameProviderName(item))
    ));
    if (previous) {
      const data = previous.dados || {};
      const dueDate = String(data.dataVencimento || '');
      provider.faturaAtualId = previous.id;
      provider.valor = Number(data.valorTotal || 0).toFixed(2);
      provider.dataVencimento = dueDate;
      if (dueDate) provider.diaVencimento = String(Number(dueDate.slice(-2)));
    } else {
      delete provider.faturaAtualId;
    }
    localStorage.setItem(storageKey, JSON.stringify(records));
    window.dispatchEvent(new CustomEvent('sigp:locais-atualizados', { detail: { tipo: invoice.entidade_tipo, id: invoice.entidade_id } }));
  }

  async function renderTab() {
    const list = byId('faturasLista');
    if (!list) return;
    try {
      loadStoredEntities();
      const [response, notesResponse] = await Promise.all([
        fetch(`${backendUrl()}/api/faturas`),
        fetch(`${backendUrl()}/api/notas/lancadas`),
      ]);
      const [body, notesBody] = await Promise.all([
        response.json().catch(() => ({})),
        notesResponse.json().catch(() => ({})),
      ]);
      if (!response.ok) throw new Error(body.error || `API respondeu HTTP ${response.status}`);
      if (!notesResponse.ok) throw new Error(notesBody.error || `API de notas respondeu HTTP ${notesResponse.status}`);
      const entityByKey = new Map(storedEntities.map((entity) => [`${entity.tipo}:${entity.id}`, entity]));
      const items = body.items || [];
      const notes = notesBody.items || [];
      list.innerHTML = items.length ? items.map((item) => {
        const entity = entityByKey.get(`${item.entidade_tipo}:${item.entidade_id}`);
        const data = item.dados || {};
        const providerName = item.provedor_nome || data.provedorEsperado || data.emissorNome || '';
        const noteCandidates = notes.filter((note) => (
          note.entidade_tipo === item.entidade_tipo
          && String(note.entidade_id || '') === String(item.entidade_id || '')
        ));
        const linkedNote = notes.find((note) => note.id === item.nota_lancada_id);
        const currentProvider = entity?.provedores.find((provider) => (
          provider.faturaAtualId && String(provider.faturaAtualId) === String(item.id)
        ));
        const comparison = data.comparacao || {};
        const status = data.statusComparacao || 'SEM_REFERENCIA';
        const comparisonLabel = Object.entries(comparison)
          .map(([key, value]) => `${key}: ${value === null ? 'sem referência' : value ? 'confere' : 'diverge'}`)
          .join(' · ');
        return `<div class="dash-row" style="display:block;padding:10px 12px;border:1px solid var(--line);border-radius:10px;margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
            <strong>${escapeHtml(entity?.nome || item.entidade_id)} · ${escapeHtml(providerName || 'Provedor não identificado')}</strong>
            <span class="r-tag">${currentProvider ? 'FATURA ATUAL' : data.documentoAdicional ? 'DOCUMENTO DA MESMA COBRANÇA' : 'HISTÓRICO'} · ${escapeHtml(status)}</span>
          </div>
          <div style="font-size:12px;color:var(--text-dim);display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px">
            <span>Tipo: ${escapeHtml(item.entidade_tipo)}</span><span>Arquivo: ${escapeHtml(item.nome_arquivo)}</span>
            <span>Emissor: ${escapeHtml(data.emissorNome || '-')}</span>
            <span>Fatura: ${escapeHtml(data.numeroFatura || '-')}</span><span>CNPJ: ${escapeHtml(data.cnpjEmissor || '-')}</span>
            <span>Vencimento: ${escapeHtml(data.dataVencimento || '-')}</span>
            <span>Valor: ${Number(data.valorTotal || 0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}</span>
            <span>Serviço: ${escapeHtml(data.descricao || 'não informado')}</span>
            <span>Nota lançada (financeiro): ${escapeHtml(linkedNote ? `${linkedNote.numero || linkedNote.id} · ${linkedNote.provedor_nome || ''}` : item.nota_lancada_id || 'ainda não lançada')}</span>${item.nota_disponivel_id ? `<span>Nota disponível (e-mail): ${escapeHtml(item.nota_disponivel_id)}</span>` : ''}
            <span>Comparações: ${escapeHtml(comparisonLabel || 'sem referência')}</span>
          </div>
          <div class="task-add-row" style="gap:8px;margin-top:8px">
            <input class="f" type="text" maxlength="1000" placeholder="Descrição do serviço" aria-label="Descrição do serviço da fatura"
              data-invoice-description="${escapeHtml(item.id)}" value="${escapeHtml(data.descricao || '')}" style="flex:1;min-width:220px">
            ${item.nota_lancada_id
              ? ''
              : `<select class="f" aria-label="Nota lançada para vincular" data-invoice-note="${escapeHtml(item.id)}" style="flex:1;min-width:220px">
                  <option value="">Selecione uma nota deste local</option>
                  ${noteCandidates.map((note) => {
                    const serviceDescription = (note.servicos || []).map((service) => String(service.descricao || '').trim()).filter(Boolean).join('; ');
                    const label = `${note.numero || note.id} · ${note.provedor_nome || 'Provedor'} · ${Number(note.valor_total || 0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}`;
                    return `<option value="${escapeHtml(note.id)}" data-service-description="${escapeHtml(serviceDescription)}">${escapeHtml(label)}</option>`;
                  }).join('')}
                </select>`}
            <button class="ghost small" type="button" data-link-invoice="${escapeHtml(item.id)}">${item.nota_lancada_id ? 'Salvar descrição' : 'Salvar descrição e vincular nota'}</button>
          </div>
          <div class="task-add-row" style="margin-top:8px"><a class="ghost small" href="${backendUrl()}/api/faturas/${encodeURIComponent(item.id)}/arquivo" target="_blank" rel="noopener">Abrir PDF</a>
            <button class="ghost small" type="button" data-delete-invoice="${escapeHtml(item.id)}">Excluir fatura</button>
            <button class="ghost small" type="button" data-analysis-invoice="${escapeHtml(item.id)}">Enviar para análise</button></div>
        </div>`;
      }).join('') : '<div class="dash-empty">Nenhuma fatura importada. Anexe PDFs pela linha de cada provedor no cadastro do local.</div>';
      list.querySelectorAll('[data-invoice-note]').forEach((select) => {
        select.addEventListener('change', () => {
          const option = select.selectedOptions[0];
          const description = option?.dataset.serviceDescription || '';
          const input = list.querySelector(`[data-invoice-description="${CSS.escape(select.dataset.invoiceNote)}"]`);
          if (input && !input.value.trim() && description) input.value = description;
        });
      });
      list.querySelectorAll('[data-link-invoice]').forEach((button) => {
        button.addEventListener('click', async () => {
          const item = items.find((invoice) => invoice.id === button.dataset.linkInvoice);
          const invoiceId = button.dataset.linkInvoice;
          const noteSelect = list.querySelector(`[data-invoice-note="${CSS.escape(invoiceId)}"]`);
          const descriptionInput = list.querySelector(`[data-invoice-description="${CSS.escape(invoiceId)}"]`);
          const noteId = item?.nota_lancada_id || noteSelect?.value || '';
          const note = notes.find((entry) => entry.id === noteId);
          const description = String(descriptionInput?.value || '').trim();
          if (!item || !noteId || !description) {
            byId('faturasStatus').textContent = 'Selecione uma nota do mesmo local e informe a descrição do serviço.';
            return;
          }
          if (!window.confirm(`Vincular "${item.nome_arquivo}" à nota ${note?.numero || noteId} e recalcular as comparações? Nenhum pagamento será criado.`)) return;
          button.disabled = true;
          button.textContent = 'Salvando...';
          try {
            const response = await fetch(`${backendUrl()}/api/faturas/${encodeURIComponent(item.id)}/vincular`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ notaLancadaId: noteId, descricao: description }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || result.ok !== true) throw new Error(result.error || `API respondeu HTTP ${response.status}`);
            byId('faturasStatus').textContent = 'Descrição salva e fatura vinculada; comparações e conciliações atualizadas sem registrar pagamento.';
            await renderTab();
          } catch (error) {
            button.disabled = false;
            button.textContent = 'Tentar salvar novamente';
            byId('faturasStatus').textContent = `Não foi possível vincular a fatura: ${error.message || 'erro de conexão'}`;
          }
        });
      });
      list.querySelectorAll('[data-delete-invoice]').forEach((button) => {
        button.addEventListener('click', async () => {
          const item = items.find((invoice) => invoice.id === button.dataset.deleteInvoice);
          if (!item || !window.confirm(`Excluir a fatura "${item.nome_arquivo}" e o PDF armazenado? Esta ação não pode ser desfeita.`)) return;
          button.disabled = true;
          button.textContent = 'Excluindo…';
          try {
            const response = await fetch(`${backendUrl()}/api/faturas/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || result.ok === false) throw new Error(result.error || `API respondeu HTTP ${response.status}`);
            syncDeletedInvoiceProvider(item, items);
            byId('faturasStatus').textContent = 'Fatura excluída; conciliações vinculadas foram atualizadas.';
            await renderTab();
          } catch (error) {
            button.disabled = false;
            button.textContent = 'Tentar excluir novamente';
            byId('faturasStatus').textContent = `Não foi possível excluir a fatura: ${error.message || 'erro de conexão'}`;
          }
        });
      });
      list.querySelectorAll('[data-analysis-invoice]').forEach((button) => {
        button.addEventListener('click', async () => {
          button.disabled = true;
          button.textContent = 'Enviando…';
          try {
            const item = items.find((invoice) => invoice.id === button.dataset.analysisInvoice);
            const entity = item && entityByKey.get(`${item.entidade_tipo}:${item.entidade_id}`);
            const result = await window.SIGP_ANALISE.enviar({
              fatura: item,
              local: {
                tipo: item?.entidade_tipo || '',
                id: item?.entidade_id || '',
                nome: entity?.nome || '',
                cidade: entity?.cidade || '',
              },
            });
            button.textContent = result.cancelled ? 'Envio cancelado' : 'Análise enviada';
          } catch (error) {
            button.disabled = false;
            button.textContent = 'Tentar análise novamente';
            byId('faturasStatus').textContent = `Não foi possível enviar a análise: ${error.message || 'erro de conexão'}`;
          }
        });
      });
      if (body.error) throw new Error(body.error);
    } catch (error) {
      list.textContent = `Não foi possível carregar as faturas: ${error.message || 'erro de conexão'}`;
    }
  }

  init();
  window.SIGP_FATURAS = {
    open,
    openForEntity,
    openForProvider,
    renderTab,
    hasPending,
    uploadPending,
    webhookKey: WEBHOOK_KEY,
  };
})();
