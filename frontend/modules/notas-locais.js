const SIGP_NOTAS_LOCAIS = (() => {
  const drafts = new Map();
  let editorServices = [];
  const fieldGroups = {
    lancada: [
      { key: 'chave', label: 'Chave da nota', type: 'text', full: true },
      { key: 'numero', label: 'Número da nota', type: 'text' },
      { key: 'serie', label: 'Série', type: 'text' },
      { key: 'provedorNome', label: 'Provedor', type: 'text' },
      { key: 'localNome', label: 'Local', type: 'text' },
      { key: 'localCidade', label: 'Cidade', type: 'text' },
      { key: 'valor', label: 'Valor total (R$)', type: 'number' },
      { key: 'dataEmissao', label: 'Emissão', type: 'date' },
      { key: 'dataVencimento', label: 'Vencimento', type: 'date' },
      { key: 'observacao', label: 'Observação', type: 'text', full: true },
    ],
    paga: [
      { key: 'chave', label: 'Chave da nota paga', type: 'text', full: true },
      { key: 'numero', label: 'Número da nota', type: 'text' },
      { key: 'serie', label: 'Série', type: 'text' },
      { key: 'provedorNome', label: 'Provedor', type: 'text' },
      { key: 'localNome', label: 'Local', type: 'text' },
      { key: 'localCidade', label: 'Cidade', type: 'text' },
      { key: 'valor', label: 'Valor total (R$)', type: 'number' },
      { key: 'valorPago', label: 'Valor pago (R$)', type: 'number' },
      { key: 'dataEmissao', label: 'Emissão', type: 'date' },
      { key: 'dataPagamento', label: 'Data de pagamento', type: 'date' },
      { key: 'observacao', label: 'Observação', type: 'text', full: true },
    ],
  };

  function uid() {
    return typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `nf-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function dateInputValue(value) {
    const text = String(value ?? '').trim();
    const isoDate = text.match(/^(\d{4}-\d{2}-\d{2})(?:$|T)/);
    if (isoDate) return isoDate[1];
    const brazilianDate = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (brazilianDate) return `${brazilianDate[3]}-${brazilianDate[2]}-${brazilianDate[1]}`;
    return '';
  }

  function cloneRows(rows = []) {
    return rows.map((row) => ({
      ...row,
      notaLancada: row.notaLancada ? { ...row.notaLancada } : null,
      notaPaga: row.notaPaga ? { ...row.notaPaga } : null,
      conciliacao: row.conciliacao ? { ...row.conciliacao } : null,
    }));
  }

  const STATUS_LABELS = {
    MATCH: 'MATCH · lançada, paga e fatura conferem',
    AGUARDANDO_FATURA: 'AGUARDANDO FATURA · lançada e paga conferem; anexe a fatura na aba Faturas',
    PAGO_PARCIAL: 'PAGO PARCIAL',
    DIVERGENCIA: 'DIVERGÊNCIA · corrija a nota e salve novamente',
    PENDENTE: 'PENDENTE · revise a classificação dos serviços',
  };

  function noteState(row) {
    if (row.erroSincronizacao) return `Erro: ${row.erroSincronizacao}`;
    if (row.conciliacao?.status) return STATUS_LABELS[row.conciliacao.status] || row.conciliacao.status;
    if (row.notaLancada && row.notaPaga) return 'Aguardando salvar o local para validar';
    if (row.notaPaga) return 'Nota paga importada · aguardando nota lançada ou associação manual';
    if (row.notaLancada) return 'Nota lançada importada · aguardando nota paga';
    return 'Aguardando importação';
  }

  function renderRows(containerId) {
    const state = drafts.get(containerId);
    const container = document.getElementById(containerId);
    if (!state || !container) return;
    container.replaceChildren();

    state.rows.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'nf-local-row';

      const numberLine = document.createElement('div');
      numberLine.className = 'nf-local-number-line';
      const number = document.createElement('input');
      number.className = 'f';
      number.type = 'text';
      number.placeholder = 'Número da nota';
      number.value = item.numero || item.notaLancada?.numero || item.notaPaga?.numero || '';
      number.addEventListener('input', () => {
        item.numero = number.value;
      });
      numberLine.appendChild(number);

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'ghost small nf-local-remove';
      remove.title = 'Remover linha';
      remove.setAttribute('aria-label', 'Remover linha de nota');
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        state.rows.splice(index, 1);
        renderRows(containerId);
      });
      numberLine.appendChild(remove);
      row.appendChild(numberLine);

      const actions = document.createElement('div');
      actions.className = 'nf-local-actions';
      [
        ['lancada', 'Importar NF · Nota lançada'],
        ['paga', '💰 Marcar como pago'],
      ].forEach(([type, label]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = type === 'lancada' ? 'primary small' : 'ghost small';
        button.textContent = label;
        if (type === 'paga') {
          button.title = 'Marcar como pago importando a NF/XML de pagamento';
          button.setAttribute('aria-label', button.title);
        }
        button.addEventListener('click', () => openEditor(containerId, index, type));
        actions.appendChild(button);
      });
      row.appendChild(actions);

      if (item.notaLancada) {
        const analysis = document.createElement('button');
        const context = typeof state.context === 'function' ? state.context() : (state.context || {});
        analysis.type = 'button';
        analysis.className = 'ghost small';
        analysis.textContent = 'Enviar para análise';
        analysis.disabled = !context.id;
        analysis.title = context.id ? 'Enviar os documentos deste local ao n8n' : 'Salve o cadastro do local antes de analisar';
        analysis.addEventListener('click', async () => {
          analysis.disabled = true;
          analysis.textContent = 'Enviando…';
          try {
            const result = await window.SIGP_ANALISE.enviar({
              notaLancada: item.notaLancada,
              notaPaga: item.notaPaga,
              local: {
                tipo: context.tipo,
                id: context.id,
                nome: context.nome || '',
                cidade: context.cidade || '',
              },
            });
            if (result.cancelled) {
              showMessage('Envio cancelado. Nenhuma análise manual foi disparada.');
            } else {
              showMessage(`Análise enviada ao n8n · ${result.status}.`);
            }
          } catch (error) {
            showMessage(`Não foi possível enviar a análise: ${error.message || 'erro de conexão'}`);
          } finally {
            analysis.disabled = !context.id;
            analysis.textContent = 'Enviar para análise';
          }
        });
        actions.appendChild(analysis);
      }

      if (item.notaLancada?.xmlUrl) {
        // XML da nota fiscal que veio com a fatura (Gmail): fica na nota do local.
        const xmlLink = document.createElement('a');
        xmlLink.className = 'note-file';
        xmlLink.href = `${(window.SIGP_API?.backendUrl?.() || '').replace(/\/$/, '')}${item.notaLancada.xmlUrl}`;
        xmlLink.download = item.notaLancada.xmlNome || `nota-${item.notaLancada.numero || 'fiscal'}.xml`;
        xmlLink.textContent = 'XML da nota fiscal';
        actions.appendChild(xmlLink);
      }
      const services = item.notaLancada?.servicos || item.notaPaga?.servicos || [];
      if (services.length) {
        const serviceSummary = document.createElement('div');
        serviceSummary.className = 'nf-local-status';
        serviceSummary.textContent = services.map((service) => {
          const amount = Number(service.valorTotal || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
          return `${service.descricao} · ${amount} · ${service.classificacao || 'PENDENTE'}`;
        }).join(' | ');
        row.appendChild(serviceSummary);
      }

      const status = document.createElement('div');
      status.className = 'nf-local-status';
      status.textContent = noteState(item);
      row.appendChild(status);
      container.appendChild(row);
    });
  }

  function setRows(containerId, rows, context = {}) {
    drafts.set(containerId, { rows: cloneRows(rows), context });
    const addButton = document.querySelector(`[data-nf-add-for="${containerId}"]`);
    if (addButton) {
      addButton.onclick = () => {
        const state = drafts.get(containerId);
        state.rows.push({ id: uid(), numero: '', notaLancada: null, notaPaga: null, conciliacao: null });
        renderRows(containerId);
      };
    }
    renderRows(containerId);
  }

  function getRows(containerId) {
    const state = drafts.get(containerId);
    if (!state) return [];
    return cloneRows(state.rows).filter((row) => row.numero || row.notaLancada || row.notaPaga);
  }

  function openEditor(containerId, index, type) {
    const state = drafts.get(containerId);
    const row = state?.rows[index];
    if (!row) return;
    const overlay = document.getElementById('nfLocalEditorOverlay');
    const form = document.getElementById('nfLocalEditorForm');
    const fields = fieldGroups[type];
    // Primeiro pagamento de uma nota lançada: o formulário já vem com a identidade, o valor e os serviços
    // dela (é o pagamento desta nota). O usuário confere, classifica os serviços e informa a data do pagamento.
    const fromLaunched = type === 'paga' && !row.notaPaga && row.notaLancada
      ? {
        // Chave lida tem prioridade; sem chave, o padrão (que nunca serve de identidade).
        chave: String(row.notaLancada.chave || '').trim() || '999999999',
        numero: row.notaLancada.numero || '',
        serie: row.notaLancada.serie || '',
        provedorNome: row.notaLancada.provedorNome || '',
        localNome: row.notaLancada.localNome || '',
        localCidade: row.notaLancada.localCidade || '',
        valor: row.notaLancada.valor ?? row.notaLancada.valorTotal ?? '',
        valorPago: row.notaLancada.valor ?? row.notaLancada.valorTotal ?? '',
        dataEmissao: row.notaLancada.dataEmissao || '',
        dataPagamento: new Date().toISOString().slice(0, 10),
        servicos: row.notaLancada.servicos || [],
      }
      : null;
    const existing = type === 'lancada' ? row.notaLancada : (row.notaPaga || fromLaunched);
    const grid = document.getElementById('nfLocalEditorFields');
    const context = typeof state.context === 'function' ? state.context() : (state.context || {});
    document.getElementById('nfLocalEditorTitle').textContent = type === 'lancada' ? 'Nota lançada' : 'Nota paga';
    document.getElementById('nfLocalEditorSub').textContent = context.nome
      ? `${context.nome}${context.cidade ? ` · ${context.cidade}` : ''}`
      : 'Importe o arquivo ou preencha os campos manualmente.';
    grid.replaceChildren();

    fields.forEach((field) => {
      const wrap = document.createElement('div');
      if (field.full) wrap.className = 'full';
      const label = document.createElement('label');
      label.textContent = field.label;
      const input = document.createElement('input');
      input.className = 'f';
      input.type = field.type;
      input.step = field.type === 'number' ? '0.01' : '';
      input.dataset.nfField = field.key;
      const value = existing?.[field.key] ?? (field.key === 'localCidade' ? context.cidade : '');
      input.value = field.type === 'date' ? dateInputValue(value) : (value ?? '');
      wrap.append(label, input);
      grid.appendChild(wrap);
    });

    form.dataset.containerId = containerId;
    form.dataset.rowIndex = String(index);
    form.dataset.noteType = type;
    form.dataset.contextName = context.nome || '';
    form.dataset.contextCity = context.cidade || '';
    document.getElementById('nfLocalEditorFile').value = '';
    editorServices = (existing?.servicos || []).map((service) => ({ ...service }));
    renderServiceItems();
    overlay.classList.add('open');
    const keyField = grid.querySelector('[data-nf-field="chave"]');
    if (keyField) keyField.focus();
  }

  function readEditorFields() {
    const values = {};
    document.querySelectorAll('#nfLocalEditorFields [data-nf-field]').forEach((input) => {
      values[input.dataset.nfField] = input.value.trim();
    });
    return values;
  }

  function fillEditor(note) {
    Object.entries(note || {}).forEach(([key, value]) => {
      const input = document.querySelector(`#nfLocalEditorFields [data-nf-field="${key}"]`);
      if (input && value != null && value !== '') input.value = input.type === 'date' ? dateInputValue(value) : value;
    });
    editorServices = (note?.servicos || []).map((service) => ({ ...service }));
    renderServiceItems();
  }

  function renderServiceItems() {
    const container = document.getElementById('nfLocalServiceItems');
    if (!container) return;
    container.replaceChildren();
    editorServices.forEach((service, index) => {
      const card = document.createElement('div');
      card.className = 'nf-local-service-item';
      const description = document.createElement('textarea');
      description.className = 'f nf-local-service-description';
      description.rows = 2;
      description.placeholder = 'Descrição do serviço cobrado';
      description.value = service.descricao || '';
      description.dataset.serviceField = 'descricao';
      card.appendChild(description);

      const details = document.createElement('div');
      details.className = 'nf-local-service-details';
      [
        ['codigo', 'Código', service.codigo || ''],
        ['quantidade', 'Quantidade', service.quantidade ?? 0],
        ['valorUnitario', 'Valor unitário', service.valorUnitario ?? 0],
        ['valorTotal', 'Total do item', service.valorTotal ?? 0],
      ].forEach(([key, labelText, value]) => {
        const wrap = document.createElement('label');
        wrap.textContent = labelText;
        const input = document.createElement('input');
        input.className = 'f';
        input.type = key === 'codigo' ? 'text' : 'number';
        if (key !== 'codigo') input.step = '0.01';
        input.value = value;
        input.dataset.serviceField = key;
        details.append(wrap, input);
      });
      card.appendChild(details);

      const review = document.createElement('div');
      review.className = 'nf-local-service-review';
      const classificationLabel = document.createElement('label');
      classificationLabel.textContent = 'Análise do item';
      const classification = document.createElement('select');
      classification.className = 'f';
      classification.dataset.serviceField = 'classificacao';
      [
        ['PENDENTE', 'Aguardando análise'],
        ['CONTRATADO', 'Serviço contratado'],
        ['DIVERGENTE', 'Não contratado / divergente'],
      ].forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        classification.appendChild(option);
      });
      classification.value = service.classificacao || 'PENDENTE';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'ghost small';
      remove.textContent = 'Remover item';
      remove.addEventListener('click', () => {
        editorServices.splice(index, 1);
        renderServiceItems();
      });
      review.append(classificationLabel, classification, remove);
      card.appendChild(review);
      container.appendChild(card);
    });
  }

  function readServiceItems() {
    return Array.from(document.querySelectorAll('#nfLocalServiceItems .nf-local-service-item'))
      .map((card) => {
        const value = (key) => card.querySelector(`[data-service-field="${key}"]`)?.value || '';
        return {
          id: editorServices[Array.from(card.parentElement.children).indexOf(card)]?.id || uid(),
          codigo: value('codigo'),
          descricao: value('descricao').trim(),
          quantidade: Number(value('quantidade') || 0),
          valorUnitario: Number(value('valorUnitario') || 0),
          valorTotal: Number(value('valorTotal') || 0),
          classificacao: value('classificacao') || 'PENDENTE',
        };
      })
      .filter((service) => service.descricao);
  }

  function showMessage(message) {
    if (typeof window.toast === 'function') window.toast(message, 4500);
    else console.info(message);
  }

  async function resolveMunicipalityName(code) {
    if (!code) return '';
    try {
      const response = await fetch(`https://servicodados.ibge.gov.br/api/v1/localidades/municipios/${encodeURIComponent(code)}`);
      if (!response.ok) return `IBGE ${code}`;
      const municipio = await response.json();
      return municipio.nome || `IBGE ${code}`;
    } catch (error) {
      return `IBGE ${code}`;
    }
  }

  function initEditor() {
    document.body.insertAdjacentHTML('beforeend', `
      <div class="overlay nf-local-editor-overlay" id="nfLocalEditorOverlay">
        <div class="modal nf-local-editor-modal">
          <h2 id="nfLocalEditorTitle">Nota fiscal</h2>
          <div class="sub" id="nfLocalEditorSub"></div>
          <form id="nfLocalEditorForm">
            <div class="nf-local-import-bar">
              <button type="button" class="ghost small" id="nfLocalChooseFile">Escolher arquivo XML/JSON</button>
              <input id="nfLocalEditorFile" type="file" accept=".xml,.json,.txt,.pdf" hidden>
              <span class="hint" id="nfLocalFileName">Ou preencha os campos abaixo.</span>
            </div>
            <div class="field-grid" id="nfLocalEditorFields"></div>
            <section class="nf-local-service-review-section">
              <h3>Itens de serviço</h3>
              <p>Revise cada cobrança. Itens pendentes não liberam a conciliação automática.</p>
              <div id="nfLocalServiceItems"></div>
              <button type="button" class="ghost small" id="nfLocalAddService">+ adicionar serviço</button>
            </section>
            <div class="modal-actions">
              <div class="right">
                <button type="button" class="ghost" id="nfLocalEditorCancel">Cancelar</button>
                <button type="submit" class="primary">Usar nesta linha</button>
              </div>
            </div>
          </form>
        </div>
      </div>
    `);

    const overlay = document.getElementById('nfLocalEditorOverlay');
    const form = document.getElementById('nfLocalEditorForm');
    const fileInput = document.getElementById('nfLocalEditorFile');
    document.getElementById('nfLocalChooseFile').onclick = () => fileInput.click();
    document.getElementById('nfLocalAddService').onclick = () => {
      editorServices.push({ id: uid(), descricao: '', quantidade: 1, valorUnitario: 0, valorTotal: 0, classificacao: 'PENDENTE' });
      renderServiceItems();
    };
    document.getElementById('nfLocalEditorCancel').onclick = () => overlay.classList.remove('open');
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) overlay.classList.remove('open');
    });
    fileInput.onchange = async () => {
      const file = fileInput.files?.[0];
      if (!file) return;
      if (file.name.toLowerCase().endsWith('.pdf')) {
        showMessage('PDF selecionado; preencha os campos manualmente ou importe XML/JSON.');
        document.getElementById('nfLocalFileName').textContent = file.name;
        return;
      }
      const tipo = file.name.toLowerCase().endsWith('.xml') ? 'xml' : 'json';
      const resultado = window.SIGP_NFSE?.importarNotaArquivo({
        tipo,
        conteudo: await file.text(),
        arquivoNome: file.name,
        registrarEvento: false,
      });
      if (!resultado?.ok) {
        showMessage('Não foi possível normalizar o arquivo. Revise os dados ou preencha manualmente.');
        return;
      }
      const localNome = form.dataset.contextName || resultado.nota.localNome;
      let localCidade = form.dataset.contextCity || resultado.nota.localCidade;
      if (!localCidade && resultado.nota.municipioCodigo) {
        localCidade = await resolveMunicipalityName(resultado.nota.municipioCodigo);
      }
      fillEditor({ ...resultado.nota, localNome, localCidade });
      document.getElementById('nfLocalFileName').textContent = file.name;
    };

    document.getElementById('nfLocalEditorForm').addEventListener('submit', (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const containerId = form.dataset.containerId;
      const rowIndex = Number(form.dataset.rowIndex);
      const type = form.dataset.noteType;
      const state = drafts.get(containerId);
      const row = state?.rows[rowIndex];
      if (!row) return;
      const fields = readEditorFields();
      const note = window.SIGP_NFSE.normalizarNFSE({
        ...fields,
        valor: fields.valor,
        valorPago: fields.valorPago,
        servicos: readServiceItems(),
        status: type === 'lancada' ? 'PENDENTE' : 'PAGA',
        observacao: fields.observacao || (type === 'lancada' ? 'Importada no cadastro do local' : 'Pagamento importado no cadastro do local'),
      });
      if (!note.chave && !note.numero) {
        // Regra do usuário: sem chave e número vale o valor padrão; o provedor identifica a cobrança do mês.
        if (!String(note.provedorNome || '').trim()) {
          showMessage('Informe o provedor da nota (sem chave e número, ele identifica a cobrança do mês).');
          return;
        }
        note.numero = '999999999';
        showMessage('Nota sem chave e número: usado o valor padrão 999999999. Se já houver nota deste provedor no mesmo mês, ela será atualizada.');
      }
      if (type === 'paga' && note.valorPago <= 0) {
        showMessage('Informe o valor efetivamente pago.');
        return;
      }
      // Editar mantém o mesmo registro (id) e o que o formulário não mostra (ex.: link do XML da nota).
      const anterior = type === 'lancada' ? row.notaLancada : row.notaPaga;
      const salvo = anterior ? { ...anterior, ...note, id: anterior.id || note.id } : note;
      if (type === 'lancada') row.notaLancada = salvo;
      else row.notaPaga = salvo;
      // A classificação é do serviço, não do documento: vale para o mesmo serviço na nota lançada e no pagamento.
      const outro = type === 'lancada' ? row.notaPaga : row.notaLancada;
      const chaveServico = (s) => String(s?.descricao || '').trim().toLowerCase();
      if (outro && Array.isArray(outro.servicos)) {
        const classes = new Map((salvo.servicos || []).map((s) => [chaveServico(s), s.classificacao]));
        outro.servicos = outro.servicos.map((s) => (classes.has(chaveServico(s)) ? { ...s, classificacao: classes.get(chaveServico(s)) } : s));
      }
      row.numero = note.numero || row.numero;
      row.chave = note.chave || row.chave;
      row.status = type === 'lancada' ? 'LANCADA' : row.status;
      renderRows(containerId);
      overlay.classList.remove('open');
    });
  }

  async function syncRecord(record, entityType) {
    const api = window.SIGP_NFSE;
    // Linha "nota lançada" criada pela antiga associação do Gmail (id gmail-...): é nota disponível, não lançada.
    // Não é reenviada como nota lançada (a API recusaria); o pagamento da linha, se houver, segue.
    const rows = cloneRows(record.notasFiscais || []).map((row) => {
      if (!String(row?.notaLancada?.id || '').startsWith('gmail-')) return row;
      const { notaLancada, conciliacao, ...resto } = row;
      return resto.notaPaga ? { ...resto, status: 'PENDENTE' } : null;
    }).filter(Boolean);
    const entityNames = { ag: 'agencia', rv: 'rodoviaria', gr: 'garagem' };
    const contexto = {
      entidadeTipo: entityNames[entityType] || entityType,
      entidadeId: record.id,
      localTipo: entityNames[entityType] || entityType,
      localNome: record.nome || '',
      localCidade: record.cidade || '',
    };

    for (const row of rows) {
      if (!row.notaLancada) {
        if (!row.notaPaga) continue;
        try {
          const paymentId = row.notaPaga.id || uid();
          const paidResponse = await api.salvarNotaPagaBackend({
            ...row.notaPaga,
            ...contexto,
            id: paymentId,
          }, {
            id: paymentId,
            valorPago: row.notaPaga.valorPago,
            dataPagamento: row.notaPaga.dataPagamento,
            localCidade: row.notaPaga.localCidade || contexto.localCidade,
          });
          row.notaPaga = { ...row.notaPaga, ...contexto, id: paidResponse.item.id };
          row.erroSincronizacao = '';
        } catch (error) {
          row.erroSincronizacao = error.message || 'Falha ao sincronizar a nota paga.';
        }
        continue;
      }
      try {
        const launchedResponse = await api.salvarNotaLancadaBackend({
          ...row.notaLancada,
          ...contexto,
          id: row.notaLancada.id || uid(),
        });
        row.notaLancada = {
          ...row.notaLancada,
          ...contexto,
          id: launchedResponse.item.id,
          // Serviços como a API gravou (ex.: valor do item preenchido com o total da nota).
          ...(launchedResponse.item.servicos?.length ? { servicos: launchedResponse.item.servicos } : {}),
        };
        // Recorrência: a API atualizou a nota do mesmo mês (mesmo local e empresa) em vez de criar outra.
        if (launchedResponse.item.recorrencia) row.recorrencia = launchedResponse.item.recorrencia;
        row.status = 'LANCADA';

        if (!row.notaPaga) continue;
        // Pagamento sem serviços informados paga os serviços da nota lançada desta linha (com a classificação dela).
        if (!(row.notaPaga.servicos || []).length && (row.notaLancada.servicos || []).length) {
          row.notaPaga = { ...row.notaPaga, servicos: row.notaLancada.servicos.map((s) => ({ ...s })) };
        }
        const paidResponse = await api.salvarNotaPagaBackend({
          ...row.notaPaga,
          ...contexto,
          id: row.notaPaga.id || uid(),
        }, {
          id: row.notaPaga.id || uid(),
          valorPago: row.notaPaga.valorPago,
          dataPagamento: row.notaPaga.dataPagamento,
          localCidade: row.notaPaga.localCidade || contexto.localCidade,
          notaLancadaId: launchedResponse.item.id,
        });
        row.notaPaga = { ...row.notaPaga, ...contexto, id: paidResponse.item.id };
        // A API concilia ao receber o pagamento e avisa o n8n quando o status muda (MATCH, DIVERGENCIA,
        // AGUARDANDO_FATURA); o navegador não envia mais o evento.
        const reconciliation = paidResponse.conciliacao
          || await api.conciliarNotasBackendNFSE(launchedResponse.item.id, paidResponse.item.id);
        row.conciliacao = reconciliation.resultado;
        row.status = reconciliation.status;
        row.erroSincronizacao = '';
      } catch (error) {
        row.erroSincronizacao = error.message || 'Falha ao sincronizar a nota.';
        row.status = row.notaPaga ? 'PENDENTE' : 'LANCADA';
      }
    }
    // Duas linhas que agora apontam para a mesma nota (recorrência do mês) viram uma só.
    const byNote = new Map();
    const merged = [];
    rows.forEach((row) => {
      const noteId = row.notaLancada?.id;
      if (!noteId || !byNote.has(noteId)) {
        if (noteId) byNote.set(noteId, row);
        merged.push(row);
        return;
      }
      const kept = byNote.get(noteId);
      kept.notaLancada = { ...kept.notaLancada, ...row.notaLancada };
      if (!kept.notaPaga && row.notaPaga) kept.notaPaga = row.notaPaga;
      kept.recorrencia = kept.recorrencia || row.recorrencia;
    });
    return merged;
  }

  initEditor();
  return { setRows, getRows, syncRecord };
})();

if (typeof window !== 'undefined') window.SIGP_NOTAS_LOCAIS = SIGP_NOTAS_LOCAIS;