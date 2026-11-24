(() => {
  const byId = (id) => document.getElementById(id);
  const LOCATION_KEYS = {
    agencia: 'ti_agencias_v1',
    rodoviaria: 'ti_rodoviarias_v1',
    garagem: 'ti_garagens_v1',
  };
  const TYPE_LABELS = {
    agencia: 'Agência',
    rodoviaria: 'Rodoviária',
    garagem: 'Garagem',
  };
  let items = [];
  let locations = [];
  let selectedNewLocation = null;
  const comparisons = new Map();

  function backendUrl() {
    return window.SIGP_API.backendUrl().replace(/\/$/, '');
  }

  function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = String(value ?? '');
    return element.innerHTML;
  }

  async function request(url, options = {}) {
    const response = await fetch(`${backendUrl()}${url}`, options);
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.ok === false) {
      throw new Error(result.error || `A API respondeu HTTP ${response.status}.`);
    }
    return result;
  }

  const XML_TYPES = { nfse_abrasf: 'NFS-e (ABRASF)', nfse_nacional: 'NFS-e nacional', nfe: 'NF-e', nfcom: 'NFCom' };
  const FIELD_LABELS = { numero: 'Número', valorTotal: 'Valor', dataVencimento: 'Vencimento', cnpjEmissor: 'CNPJ do emissor' };
  // XML da nota fiscal que veio com a fatura: o XML vale para os campos fiscais; o PDF continua guardado.
  function xmlBlock(item, data) {
    const xml = data.xmlFiscal;
    const missingPdf = data.semPdf
      ? '<div class="hint" role="alert">Chegou só o XML da nota fiscal. A fatura PDF também é obrigatória: associe quando ela chegar.</div>'
      : '';
    const invalid = (data.classificacao?.xmlInvalidos || []).length
      ? `<div class="hint" role="alert">XML anexado não pôde ser lido: ${escapeHtml(data.classificacao.xmlInvalidos.join('; '))}</div>`
      : '';
    if (!xml || !xml.ok) return missingPdf || invalid ? `<div class="full">${missingPdf}${invalid}</div>` : '';
    const divergences = (data.divergenciasXml || []).map((d) =>
      `<div><b>${escapeHtml(FIELD_LABELS[d.campo] || d.campo)}:</b> PDF ${escapeHtml(d.campo === 'valorTotal' ? formatMoney(d.pdf) : d.pdf)} × XML ${escapeHtml(d.campo === 'valorTotal' ? formatMoney(d.xml) : d.xml)}</div>`
    ).join('');
    return `<div class="full" data-role="xml-info"><b>XML da nota fiscal</b>
      <div>${escapeHtml(XML_TYPES[xml.tipoXml] || 'Nota fiscal')} nº ${escapeHtml(xml.numero || '—')}${xml.serie ? ` · série ${escapeHtml(xml.serie)}` : ''} · ${escapeHtml(xml.emissorNome || '—')} · ${escapeHtml(formatMoney(xml.valorTotal))} · vencimento ${escapeHtml(xml.dataVencimento || '—')}</div>
      <div class="hint">Os campos fiscais abaixo vêm do XML (prioridade sobre a leitura do PDF). Ao associar, o PDF e o XML ficam no local como nota disponível (a nota lançada vem do financeiro).</div>
      ${divergences ? `<div class="hint" role="alert">PDF e XML não conferem; vale o XML:${divergences}</div>` : ''}
      ${missingPdf}${invalid}
      ${item.xmlUrl ? `<a class="note-file" href="${escapeHtml(backendUrl() + item.xmlUrl)}" download="${escapeHtml(data.xmlArquivo?.nome || 'nota-fiscal.xml')}">Baixar XML</a>` : ''}
    </div>`;
  }
  // Documento que a IA considerou "não é cobrança de provedor": mostra o porquê e as duas decisões possíveis.
  function triageBlock(data) {
    const t = data.triagem || {};
    const ia = data.classificacao?.ia || {};
    const conf = t.confianca ?? ia.confianca;
    return `<div class="full" data-role="triage" style="margin-top:10px">
      <div><b>A IA ignorou este documento.</b> ${escapeHtml(t.motivo || ia.motivo || 'Sem motivo informado.')}</div>
      <div class="hint">Tipo sugerido: ${escapeHtml(t.tipoDocumento || ia.tipoDocumento || '—')}${conf != null ? ` · confiança ${Math.round(Number(conf) * 100)}%` : ''}. Sua decisão ensina a IA.</div>
      <div class="task-add-row" style="margin-top:6px">
        <button class="ghost small" type="button" data-action="ignore-confirm">Concordo: não é cobrança</button>
        <button class="primary small" type="button" data-action="rescue">É cobrança: trazer para a caixa</button>
      </div>
    </div>`;
  }
  // Resumo das últimas leituras do Gmail e atalho para revisar os ignorados (fica acima da lista).
  async function renderTriageSummary() {
    const box = byId('notasRecebidasTriagem');
    if (!box) return;
    try {
      const r = await request('/api/notas-recebidas/triagem?limite=1');
      const e = (r.execucoes || [])[0];
      const filtro = byId('notasRecebidasFiltro').value;
      const partes = [];
      if (e) {
        partes.push(`<b>Última leitura do Gmail</b> · ${escapeHtml(formatDate(e.em))}: ${e.documentos} documento(s) — ${e.paraCaixa} para a caixa, ${e.ignorados} ignorado(s) pela IA${e.resgatados ? `, ${e.resgatados} resgatado(s)` : ''}.`);
      }
      if (r.ignoradosPendentes && filtro !== 'IGNORADA_IA') {
        partes.push(`<button class="ghost small" type="button" data-action="show-ignored">Revisar ${r.ignoradosPendentes} ignorado(s) pela IA</button>`);
      }
      if (filtro === 'IGNORADA_IA' && items.length) {
        partes.push(`<button class="ghost small" type="button" data-action="ignore-confirm-all">Concordo com todos desta lista (${items.length})</button>`);
      }
      box.innerHTML = partes.length ? `<div class="hint" style="margin:8px 0">${partes.join(' ')}</div>` : '';
    } catch (error) {
      box.textContent = '';
    }
  }
  async function confirmIgnored(ids) {
    if (!ids.length) return;
    try {
      const r = await request('/api/notas-recebidas/ignorados/confirmar', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids, operador: currentOperator() }),
      });
      byId('notasRecebidasStatus').textContent = `${r.confirmados.length} documento(s) confirmado(s) como "não é cobrança". Eles ficam no filtro “Descartada”.`;
      await renderTab(true);
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
    }
  }
  async function relinkAviso(card) {
    try {
      const r = await request(`/api/notas-recebidas/${encodeURIComponent(card.dataset.noteId)}/vincular-aviso`, { method: 'POST' });
      byId('notasRecebidasStatus').textContent = {
        pagamento_registrado: 'Aviso vinculado: pagamento registrado e conciliado.',
        vinculado: 'Aviso vinculado à cobrança.',
        vinculado_disponivel: 'Aviso vinculado à nota disponível do local.',
        pagamento_confirmado_provedor: 'Pagamento confirmado pelo provedor: o provedor do local ficou marcado como pago.',
        ja_pago: 'A cobrança já estava paga.',
        varias_candidatas: 'Ainda há mais de uma cobrança possível.',
      }[r.acao] || 'Ainda não achei a cobrança deste provedor.';
      await renderTab(true);
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
    }
  }
  async function rescueIgnored(card) {
    try {
      await request(`/api/notas-recebidas/${encodeURIComponent(card.dataset.noteId)}/resgatar`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operador: currentOperator() }),
      });
      byId('notasRecebidasStatus').textContent = 'Documento trazido para a caixa. A IA vai aprender que isto é cobrança.';
      await renderTab(true);
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
    }
  }
  function statusLabel(status) {
    return {
      AGUARDANDO_ASSOCIACAO: 'Aguardando associação',
      ASSOCIADA: 'Associada',
      REVISAO: 'Revisão',
      EM_ANALISE: 'Em análise',
      IGNORADA_IA: 'Ignorado pela IA',
      AVISO: 'Aviso vinculado',
      DESCARTADA: 'Descartada',
    }[status] || status;
  }

  // Valor padrão para chave/número vazios ou inválidos (o mesmo do backend: backend/campos.py).
  const DEFAULT_ID = '999999999';
  const DISCARD_REASONS = {
    nao_cobranca: 'Não é cobrança de internet/telecom',
    duplicada: 'Duplicada',
    ilegivel: 'Ilegível ou sem texto',
    fora_escopo: 'Fora do escopo (outro serviço ou empresa)',
    outro: 'Outro motivo',
  };

  function currentOperator() {
    try { return window.SIGP_LOGIN?.usuarioAtual?.() || ''; } catch { return ''; }
  }

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString('pt-BR');
  }

  function formatMoney(value) {
    const amount = Number(value);
    return Number.isFinite(amount) && amount > 0
      ? amount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
      : '—';
  }

  function dateInputValue(value) {
    const match = String(value || '').match(/^\d{4}-\d{2}-\d{2}/);
    return match ? match[0] : '';
  }

  function optionsForLocations(type, selectedId = '') {
    const list = locations.filter((location) => location.tipo === type && location.ativo !== false);
    return `<option value="">Selecione o local</option>${list.map((location) =>
      `<option value="${escapeHtml(location.id)}" ${location.id === selectedId ? 'selected' : ''}>${escapeHtml(location.nome)}${location.cidade ? ` — ${escapeHtml(location.cidade)}` : ''}</option>`
    ).join('')}`;
  }

  // Listas da caixa. Cada lista é um bloco recolhível; dentro dela, os e-mails formam um accordion clássico
  // (um aberto por vez) e as partes de cada e-mail são listas expansíveis (disclosure) independentes.
  const GROUPS = [
    { key: 'alta', title: 'Alta probabilidade de ser conta de internet', open: true,
      hint: 'Provedor, termo de internet ou histórico do local encontrado, a IA concorda e os campos principais estão preenchidos.' },
    { key: 'inconclusivo', title: 'Inconclusivo', open: true,
      hint: 'Falta informação para decidir: PDF não lido, campos vazios ou incorretos, ou regra e IA discordam. Revise.' },
    { key: 'baixa', title: 'Baixa probabilidade de ser conta', open: false,
      hint: 'Sem sinal de internet e a IA diz que não é cobrança. Ficam para revisão; depois de 3 confirmações do mesmo remetente, os próximos são descartados sozinhos.' },
    { key: 'analise', title: 'Em análise', open: true, hint: 'Notas em dúvida, separadas da fila até você decidir.' },
    { key: 'avisos', title: 'Avisos vinculados a cobranças', open: false,
      hint: 'Lembretes, avisos de atraso e pagamentos confirmados pelo provedor, já ligados à cobrança lançada. Pagamento confirmado marca a cobrança como paga.' },
    { key: 'associadas', title: 'Associadas', open: false, hint: 'Já vinculadas a um local.' },
    { key: 'descartadas', title: 'Descartadas', open: false, hint: 'Fora da fila; podem ser restauradas.' },
  ];
  const groupState = new Map(); // lista -> aberta?
  const openNotes = new Map(); // lista -> id do e-mail aberto (accordion: um por lista)
  const discState = new Map(); // "id:parte" -> aberta?
  const INTERNET_CATEGORIES = ['FATURA_INTERNET', 'NOTA_SERVICO_INTERNET'];
  const pct = (v) => `${Math.round(Number(v || 0) * 100)}%`;

  // Três níveis (mesma regra do WF-08, n8n/wf08/wf08_lib.js). Notas novas trazem a decisão em triagem.probabilidade;
  // as antigas são avaliadas aqui. Só agrupa: não muda o status.
  function avaliarInternet(item) {
    const data = item.dados || {};
    const c = data.classificacao || {};
    const ia = c.ia || {};
    const t = data.triagem || {};
    const favor = [];
    if (INTERNET_CATEGORIES.includes(c.categoria)) {
      favor.push(c.categoria === 'FATURA_INTERNET' ? 'Regra do SIGp: fatura de internet' : 'Regra do SIGp: nota de serviço de internet');
    }
    if (c.provedoresEncontrados?.length) favor.push(`Provedor no texto: ${c.provedoresEncontrados.join(', ')}`);
    if (c.provedoresPorRemetente?.length) favor.push(`Remetente de provedor cadastrado: ${c.provedoresPorRemetente.join(', ')}`);
    if (c.palavrasInternet?.length) favor.push(`Termos de internet: ${c.palavrasInternet.join(', ')}`);
    const historico = (item.sugestoesLocal || []).find((s) => /^(Histórico|Provedor )/.test(s.motivo || ''));
    if (historico) favor.push(historico.motivo);
    const iaNao = !ia.erro && ia.tipoDocumento === 'outro' && Number(ia.confianca) >= 0.8;
    const ilegivel = Boolean(c.ocrErro) || /OCR sem frases|sem texto legível/i.test(ia.motivo || '');
    const contra = [];
    if (iaNao) contra.push(`IA: não é cobrança de internet (${pct(ia.confianca)})${ia.motivo ? ` · ${ia.motivo}` : ''}`);
    if (!favor.length) contra.push('Nenhum provedor, termo de internet ou histórico de local encontrado');
    if (ilegivel) contra.push(/senha/i.test(c.ocrErro || '') ? 'PDF protegido por senha' : 'PDF sem texto legível: confira o arquivo');
    const faltam = [
      !(Number(data.valorTotal) > 0) && 'valor',
      !dateInputValue(data.dataVencimento) && data.tipoDocumento !== 'nota_fiscal' && 'vencimento',
      !data.emissorNome && 'emissor',
    ].filter(Boolean);
    let nivel;
    let motivo;
    if (item.status === 'IGNORADA_IA') { nivel = 'baixa'; motivo = t.motivoProbabilidade || 'A IA considerou que não é cobrança'; }
    else if (['alta', 'baixa', 'inconclusivo'].includes(t.probabilidade)) { nivel = t.probabilidade; motivo = t.motivoProbabilidade || ''; }
    else if (ilegivel) { nivel = 'inconclusivo'; motivo = 'O PDF não foi lido'; }
    else if (!favor.length && iaNao) { nivel = 'baixa'; motivo = 'Sem sinal de internet e a IA diz que não é cobrança'; }
    else if (ia.erro) { nivel = 'inconclusivo'; motivo = 'A IA não respondeu'; }
    else if (favor.length && iaNao) { nivel = 'inconclusivo'; motivo = 'A regra vê internet, mas a IA diz que não é cobrança'; }
    else if (favor.length) { nivel = 'alta'; motivo = 'Sinal de internet e a IA concorda'; }
    else { nivel = 'inconclusivo'; motivo = 'Só a IA indica cobrança; nenhum provedor ou termo de internet encontrado'; }
    if (nivel === 'alta' && faltam.length) { nivel = 'inconclusivo'; motivo = `Parece internet, mas falta: ${faltam.join(', ')}`; }
    return { nivel, motivo, alta: nivel === 'alta', favor, contra, ia, faltam };
  }

  function groupOf(item) {
    return {
      EM_ANALISE: 'analise', ASSOCIADA: 'associadas', DESCARTADA: 'descartadas', AVISO: 'avisos',
    }[item.status] || avaliarInternet(item).nivel;
  }

  function shortDate(value) {
    const d = dateInputValue(value);
    return d ? d.split('-').reverse().join('/') : '—';
  }

  function badge(item, aval) {
    const ia = aval.ia || {};
    const iaTxt = ia.tipoDocumento && !ia.erro ? ` · IA ${pct(ia.confianca)}` : '';
    if (item.status === 'IGNORADA_IA') {
      const t = (item.dados || {}).triagem || {};
      return `<span class="nr-badge nr-badge--warn">Ignorado pela IA · ${pct(t.confianca ?? ia.confianca)}</span>`;
    }
    if (item.status === 'AVISO') {
      return `<span class="nr-badge nr-badge--ok">${escapeHtml(EVENTO_LABELS[(item.dados?.aviso || {}).evento] || 'Aviso')}</span>`;
    }
    if (['ASSOCIADA', 'DESCARTADA', 'EM_ANALISE'].includes(item.status)) {
      return `<span class="nr-badge">${escapeHtml(statusLabel(item.status))}</span>`;
    }
    if (aval.nivel === 'alta') return `<span class="nr-badge nr-badge--ok">Alta${iaTxt}</span>`;
    if (aval.nivel === 'baixa') return `<span class="nr-badge">Baixa${iaTxt}</span>`;
    return `<span class="nr-badge nr-badge--warn">Inconclusivo${iaTxt}</span>`;
  }

  const EVENTO_LABELS = {
    fatura_nova: 'Fatura nova', segunda_via: '2ª via', lembrete_vencimento: 'Lembrete de vencimento',
    aviso_atraso: 'Aviso de atraso', pagamento_confirmado: 'Pagamento confirmado',
  };
  // Situação 1: o que o SIGp fez com um lembrete, aviso de atraso ou pagamento confirmado do provedor.
  function avisoBlock(data) {
    const a = data.aviso;
    if (!a) return '';
    const evento = EVENTO_LABELS[a.evento] || a.evento;
    const cand = (a.candidatas || []).map((c) => `${escapeHtml(c.provedor)} · ${escapeHtml(c.local)} · nº ${escapeHtml(c.numero || '—')} · venc. ${escapeHtml(shortDate(c.vencimento))} · ${escapeHtml(formatMoney(c.valor))}`);
    const texto = {
      pagamento_registrado: `Pagamento registrado automaticamente: ${escapeHtml(formatMoney(a.valorPago))} em ${escapeHtml(shortDate(a.dataPagamento))}, conciliado com a cobrança lançada. O provedor do local ficou marcado como pago.`,
      ja_pago: 'Esta cobrança já tinha pagamento registrado; nada foi alterado.',
      vinculado: 'Vinculado à cobrança lançada. Os alertas de vencimento continuam valendo até o pagamento.',
      vinculado_disponivel: 'Vinculado à nota disponível do local (ainda sem nota lançada do financeiro). Os alertas de vencimento continuam valendo até o pagamento.',
      pagamento_confirmado_provedor: `Pagamento confirmado pelo provedor em ${escapeHtml(shortDate(a.dataPagamento))}: o provedor do local ficou marcado como pago (alertas). A nota paga continua vindo do financeiro.`,
      sem_vinculo: 'Não achei a cobrança deste provedor. Associe a fatura do mês primeiro (ou confira o provedor).',
      varias_candidatas: 'Há mais de uma cobrança possível; associe à certa pela parte "Associar a um local".',
    }[a.acao] || '';
    return `<div class="full" data-role="aviso" style="margin-top:10px">
      <div><b>${escapeHtml(evento)}.</b> ${texto}</div>
      ${['sem_vinculo', 'varias_candidatas'].includes(a.acao) ? '<div class="task-add-row" style="margin-top:6px"><button class="ghost small" type="button" data-action="relink">Tentar vincular de novo</button><span class="hint">Depois de lançar a cobrança do mês.</span></div>' : ''}
      ${cand.length ? `<div class="hint">${['vinculado', 'pagamento_registrado', 'ja_pago', 'vinculado_disponivel', 'pagamento_confirmado_provedor'].includes(a.acao) ? 'Cobrança' : 'Cobranças possíveis'}:<br>${cand.join('<br>')}</div>` : ''}
    </div>`;
  }

  // Entrada manual: quem enviou, a observação, a IA (aguardando / não chamada / disse que não é cobrança) e a cópia que
  // chegou por e-mail. No documento do e-mail: a entrada manual da mesma fatura e o local dela já selecionado.
  function manualBlock(item, data) {
    const avisos = [];
    if (item.origemManual) {
      const m = data.entradaManual || {};
      avisos.push(`Enviado pela tela${m.usuario ? ` por ${escapeHtml(m.usuario)}` : ''} em ${escapeHtml(formatDate(m.em || item.created_at))}${m.observacao ? ` · “${escapeHtml(m.observacao)}”` : ''}. Sem e-mail, sem etiqueta no Gmail.`);
      if (data.aguardandoIA) avisos.push('A IA está lendo o documento (cerca de 1 minuto). Use “Atualizar” para ver o resultado.');
      if (data.iaNaoChamada) avisos.push(`A IA não foi chamada (${escapeHtml(data.iaNaoChamada)}). Use “Extrair dados do PDF”.`);
      if (data.decisaoIA === 'ignorar') avisos.push(`A IA achou que não é cobrança${data.triagem?.motivo ? ` (${escapeHtml(data.triagem.motivo)})` : ''}. Como foi enviado à mão, ficou em Revisão: se for cobrança, associe e a IA aprende.`);
      if (data.chegouPorEmail?.id) avisos.push(`A mesma fatura chegou por e-mail (${escapeHtml(data.chegouPorEmail.motivo || '')}). Associe a cópia do e-mail ao mesmo local para ela receber a etiqueta.`);
    }
    const c = item.correspondenteManual;
    if (c) {
      const quando = `${escapeHtml(formatDate(c.adicionadaEm))}${c.por ? ` por ${escapeHtml(c.por)}` : ''}`;
      avisos.push(c.status === 'ASSOCIADA' && c.entidadeId
        ? `Esta fatura já tinha sido adicionada à mão em ${quando} (${escapeHtml(c.motivo)}). O local dela já está selecionado: confira e valide para juntar à mesma cobrança e aplicar a etiqueta no Gmail.`
        : `Esta fatura já foi adicionada à mão em ${quando} (${escapeHtml(c.motivo)}) e ainda não foi associada. Associe esta cópia do e-mail e descarte a entrada manual como duplicada.`);
    }
    return avisos.length ? `<div class="nr-aviso" role="note" data-role="manual">${avisos.map((a) => `<div>${a}</div>`).join('')}</div>` : '';
  }

  function podeAdicionar() {
    const eu = window.SIGP_ACESSO;
    return !eu || eu.perfil === 'administrador' || (eu.permissoes || []).includes('notas_recebidas.associar');
  }

  async function enviarManual() {
    const pdf = byId('nrManualPdf').files[0];
    const xml = byId('nrManualXml').files[0];
    const status = byId('nrManualStatus');
    if (!pdf && !xml) { status.textContent = 'Escolha a fatura em PDF, o XML da nota ou os dois.'; return; }
    const form = new FormData();
    if (pdf) form.append('pdf', pdf, pdf.name);
    if (xml) form.append('xml', xml, xml.name);
    form.append('observacao', byId('nrManualObs').value || '');
    const botao = byId('nrManualEnviar');
    botao.disabled = true;
    status.textContent = 'Enviando…';
    try {
      const r = await request('/api/notas-recebidas/manual', { method: 'POST', body: form });
      ['nrManualPdf', 'nrManualXml', 'nrManualObs'].forEach((id) => { byId(id).value = ''; });
      status.textContent = r.iaAvisada
        ? 'Recebido. A IA está lendo o documento; em cerca de 1 minuto ele aparece com os dados e o local sugerido.'
        : r.aviso;
      await renderTab(true);
      if (r.iaAvisada) setTimeout(() => renderTab(true), 60000);
    } catch (error) {
      status.textContent = error.message;
    } finally {
      botao.disabled = false;
    }
  }

  function disclosure(noteId, key, title, body, defaultOpen) {
    const saved = discState.get(`${noteId}:${key}`);
    const open = saved === undefined ? defaultOpen : saved;
    return `<details class="nr-disc" data-disc="${key}"${open ? ' open' : ''}>
      <summary>${escapeHtml(title)}</summary>
      <div class="nr-disc-body">${body}</div>
    </details>`;
  }

  function renderCard(item, group = groupOf(item)) {
    const data = item.dados || {};
    const classification = data.classificacao || {};
    const issuer = data.emissorNome || data.empresaDestinataria || data.destinatarioNome || data.tomadorNome
      || data.empresa || data.razaoSocial || 'Empresa não identificada';
    const suggestions = Array.isArray(item.sugestoesLocal) ? item.sugestoesLocal : [];
    // A melhor sugestão (CNPJ/nome; depois o histórico do provedor) vem pré-selecionada. Associar continua exigindo confirmação.
    const suggested = suggestions[0] || null;
    const assigned = item.local
      ? `${TYPE_LABELS[item.entidade_tipo] || item.entidade_tipo}: ${item.local.nome}${item.local.cidade ? ` — ${item.local.cidade}` : ''}`
      : '';
    const newLocationForItem = selectedNewLocation?.noteId === item.id ? selectedNewLocation.local : null;
    const doManual = item.correspondenteManual?.entidadeId ? item.correspondenteManual : null;
    const selectedLocation = newLocationForItem
      && (!item.entidade_tipo || newLocationForItem.tipo === item.entidade_tipo)
      ? newLocationForItem.id
      : item.entidade_id || doManual?.entidadeId || suggested?.id || '';
    const selectedType = newLocationForItem
      && (!item.entidade_tipo || newLocationForItem.tipo === item.entidade_tipo)
      ? newLocationForItem.tipo
      : item.entidade_tipo || doManual?.entidadeTipo || suggested?.tipo || 'agencia';
    const auth = (() => {
      try { return ({ user: window.SIGP_LOGIN?.usuarioAtual?.() || '' }); } catch { return {}; }
    })();
    const mailSubject = `Nota fiscal recebida: ${item.assunto || item.nome_arquivo}`;
    const mailBody = `Olá,\n\nSegue a nota fiscal ${item.nome_arquivo} para processamento financeiro.\n\nO PDF deve ser anexado manualmente a este e-mail.\n\nOperador: ${auth.user || ''}`;
    const aval = avaliarInternet(item);
    const ignored = item.status === 'IGNORADA_IA';
    const finalStatus = ['ASSOCIADA', 'DESCARTADA'].includes(item.status);
    const missingRequired = !data.emissorNome || !(Number(data.valorTotal) > 0) || !dateInputValue(data.dataVencimento);
    const open = openNotes.get(group) === item.id;
    const pid = `nr-${String(item.id).replace(/[^\w-]/g, '')}`;

    const motivoBody = `
      ${aval.motivo ? `<div data-role="nivel-motivo"><b>${escapeHtml({ alta: 'Alta probabilidade', baixa: 'Baixa probabilidade', inconclusivo: 'Inconclusivo' }[aval.nivel] || '')}</b> · ${escapeHtml(aval.motivo)}</div>` : ''}
      ${data.evento?.tipo && data.evento.tipo !== 'fatura_nova' ? `<div><b>Tipo de e-mail</b> · ${escapeHtml(EVENTO_LABELS[data.evento.tipo] || data.evento.tipo)}${data.evento.origem === 'ia' ? ' (pela IA)' : data.evento.frase ? ` (frase: “${escapeHtml(data.evento.frase)}”)` : ''}</div>` : ''}
      ${aval.favor.length ? `<div><b>A favor de internet</b><ul class="nr-reasons">${aval.favor.map((r) => `<li>${escapeHtml(r)}</li>`).join('')}</ul></div>` : ''}
      ${aval.contra.length ? `<div><b>Contra</b><ul class="nr-reasons">${aval.contra.map((r) => `<li>${escapeHtml(r)}</li>`).join('')}</ul></div>` : ''}
      ${classification.categoria ? `<div><b>Classificação inicial</b><div>${escapeHtml(classification.categoria)} · confiança ${Math.round(Number(classification.confianca || 0) * 100)}% · ${escapeHtml(classification.metodo || 'regras locais')}${classification.provedoresEncontrados?.length ? ` · Provedor: ${escapeHtml(classification.provedoresEncontrados.join(', '))}` : ''}</div>
        ${classification.palavrasFiscais?.length || classification.palavrasInternet?.length ? `<div class="hint">Evidências: ${[...(classification.palavrasFiscais || []), ...(classification.palavrasInternet || [])].map(escapeHtml).join(', ')}</div>` : ''}
        ${classification.revisaoManual ? '<div class="hint">A classificação não é conclusiva; revise este PDF. Ele foi mantido na caixa.</div>' : ''}</div>` : ''}`;

    // Ajuda curta vira ⓘ com tooltip no rótulo; só o caso "valor padrão usado" aparece escrito.
    const tip = (texto) => `<span class="nr-tip" title="${escapeHtml(texto)}" aria-label="${escapeHtml(texto)}">ⓘ</span>`;
    const numeroPadrao = data.numero === DEFAULT_ID;
    const chavePadrao = data.chave === DEFAULT_ID;
    const dadosBody = `
      ${item.leituraDesatualizada ? '<div class="nr-aviso" role="note" data-role="stale-reading">Lida com regras antigas de extração. Use “Extrair dados do PDF” (no rodapé) para reler com as regras atuais (a leitura nova é gravada).</div>' : ''}
      ${xmlBlock(item, data)}
      <div class="nr-g12">
        <label class="c6">Provedor / emissor da nota
          <input class="f" data-role="issuer" maxlength="300" value="${escapeHtml(data.emissorNome || '')}" required>
        </label>
        <label class="c3"><span class="nr-l">Nº da nota ${tip(`Se vazio ou inválido, vale ${DEFAULT_ID}.`)}</span>
          <input class="f nr-mono" data-role="number" maxlength="80" value="${escapeHtml(data.numero || '')}" placeholder="${DEFAULT_ID}">
          ${numeroPadrao ? `<span class="hint">Não identificado${data.numeroOriginal ? ` (lido: “${escapeHtml(data.numeroOriginal)}”)` : ''}: valor padrão.</span>` : ''}
        </label>
        <label class="c3">Série
          <input class="f nr-mono" data-role="serie" maxlength="20" value="${escapeHtml(data.serie || '')}" readonly title="Lida do documento">
        </label>
        <label class="c3">Valor total
          <input class="f" data-role="amount" type="number" min="0.01" step="0.01" value="${escapeHtml(data.valorTotal ?? '')}" required>
        </label>
        <label class="c3"><span class="nr-l">Emissão ${tip('Se vazia, vale a data de recebimento.')}</span>
          <input class="f" data-role="issue-date" type="date" value="${escapeHtml(dateInputValue(data.dataEmissao))}">
          <span class="hint" data-role="issue-origin">${data.dataEmissaoOrigem === 'recebimento' ? 'Não encontrada: usada a data de recebimento.' : ''}</span>
        </label>
        <label class="c3">Vencimento
          <input class="f" data-role="due-date" type="date" value="${escapeHtml(dateInputValue(data.dataVencimento))}" required>
        </label>
        <div class="c3 nr-campo"><span class="nr-rotulo">CNPJ no PDF</span><div class="nr-valor nr-mono" data-role="cnpj">${escapeHtml(data.cnpjDestinatario || data.cnpjTomador || data.cnpjEmissor || '—')}</div></div>
        <label class="c12"><span class="nr-l">Chave da nota ${tip(`Se vazia ou inválida, vale ${DEFAULT_ID}.`)}</span>
          <input class="f nr-mono" data-role="key" maxlength="160" value="${escapeHtml(data.chave || '')}" placeholder="${DEFAULT_ID}">
          ${chavePadrao ? `<span class="hint">Não identificada${data.chaveOriginal ? ` (lida: “${escapeHtml(data.chaveOriginal)}”)` : ''}: valor padrão.</span>` : ''}
        </label>
        <label class="c12">Descrição do serviço
          <input class="f" data-role="description" maxlength="1000" value="${escapeHtml(data.descricaoServico || '')}">
        </label>
        ${(data.identificadoresCliente || []).length ? `<div class="c12 nr-campo" data-role="codigos-cliente"><span class="nr-rotulo">Código do cliente / contrato / instalação</span><div class="nr-valor">${data.identificadoresCliente.map((i) => `${escapeHtml({ cliente: 'Cliente', contrato: 'Contrato', instalacao: 'Instalação' }[i.tipo] || i.tipo)}: ${escapeHtml(i.valor)}`).join(' · ')}</div></div>` : ''}
      </div>`;

    const podeAssociar = !(ignored || item.status === 'AVISO' || data.semArquivo);
    const associarCard = podeAssociar ? `<section class="nr-card">
        <h5 class="nr-card-t">Associar a um local</h5>
        ${assigned ? `<div class="nr-campo"><span class="nr-rotulo">Local associado</span><div class="nr-valor">${escapeHtml(assigned)}</div></div>` : ''}
        <label>Tipo de local
          <select class="f" data-role="type">
            ${Object.entries(TYPE_LABELS).map(([type, label]) => `<option value="${type}" ${selectedType === type ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </label>
        <label>Local
          <select class="f" data-role="location">${optionsForLocations(selectedType, selectedLocation)}</select>
        </label>
        ${suggestions.length ? `<div class="hint">Sugestão (confirme antes de validar): ${suggestions.slice(0, 3).map((candidate) =>
          `${escapeHtml(TYPE_LABELS[candidate.tipo] || candidate.tipo)}: ${escapeHtml(candidate.nome)}${candidate.cidade ? ` — ${escapeHtml(candidate.cidade)}` : ''} (${escapeHtml(candidate.motivo)})`
        ).join('; ')}${suggestions.length > 3 ? ` e mais ${suggestions.length - 3}` : ''}</div>` : ''}
        ${item.provedorEmVariosLocais ? `<div class="hint" role="note" data-role="varios-locais">Este provedor atende ${item.provedorEmVariosLocais} locais e a fatura não tem código do cliente já conhecido: confira o local. Depois desta associação, o código lido fica guardado e as próximas faturas vêm com o local certo.</div>` : ''}
        <div class="nr-comparacao" data-role="comparison" aria-live="polite"></div>
      </section>` : '';

    const formularios = `
      <div class="nr-aviso" data-role="analysis-form" hidden>
        <label>O que precisa ser conferido? (opcional)
          <input class="f" data-role="analysis-note" maxlength="500" value="${escapeHtml(data.analise?.observacao || '')}" placeholder="Ex.: confirmar com o gerente qual local, valor diferente do contrato">
        </label>
        <div class="task-add-row">
          <button class="primary small" type="button" data-action="analysis-confirm">Confirmar: deixar em análise</button>
          <button class="ghost small" type="button" data-action="analysis-cancel">Cancelar</button>
        </div>
        <div class="hint">Nada é associado nem apagado. A nota sai da fila e fica no filtro “Em análise”; de lá você associa, descarta ou volta para a fila.</div>
      </div>
      <div class="nr-aviso nr-aviso--risco" data-role="discard-form" hidden>
        <div class="nr-g12">
          <label class="c6">Motivo do descarte
            <select class="f" data-role="discard-reason">
              <option value="">Selecione o motivo</option>
              ${Object.entries(DISCARD_REASONS).map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`).join('')}
            </select>
          </label>
          <label class="c6">Detalhe (opcional)
            <input class="f" data-role="discard-detail" maxlength="500" placeholder="Ex.: conta de energia, boleto de hotel">
          </label>
        </div>
        <div class="task-add-row">
          <button class="primary small" type="button" data-action="discard-confirm">Confirmar descarte</button>
          <button class="ghost small" type="button" data-action="discard-cancel">Cancelar</button>
        </div>
        <div class="hint">O PDF e o registro não são apagados; a nota pode ser restaurada no filtro “Descartada”. O descarte ensina o sistema o que não é cobrança.</div>
      </div>`;

    const docTipo = data.semPdf ? 'XML' : 'PDF';
    const arquivosCard = `<section class="nr-card">
        <h5 class="nr-card-t">${item.origemManual ? 'Arquivos' : 'Arquivos e e-mail'}</h5>
        ${item.status === 'ASSOCIADA' ? `<div class="hint">${item.origemManual ? 'Sem etiqueta no Gmail: o documento foi enviado pela tela.' : `Etiqueta Gmail: ${escapeHtml(item.etiqueta_gmail || 'aguardando')} · ${escapeHtml(item.etiqueta_status || 'pendente')}`}</div>
          ${item.notaDisponivelId ? `<div class="hint">Nota disponível no local: ${escapeHtml(item.notaDisponivelId)}${item.notaLancadaId ? ` · lançada pelo financeiro: ${escapeHtml(item.notaLancadaId)}` : ' · aguardando o lançamento do financeiro'}</div>` : ''}
          ${item.etiqueta_erro ? `<div class="hint" role="alert">Falha ao organizar no Gmail: ${escapeHtml(item.etiqueta_erro)}</div>` : ''}` : ''}
        ${data.semArquivo ? `<div class="hint">E-mail sem anexo. Trecho: ${escapeHtml(data.descricaoServico || '—')}</div>` : `
        <div class="nr-anexo">
          <span class="nr-anexo-ico${data.semPdf ? ' nr-anexo-ico--xml' : ''}" aria-hidden="true">${docTipo}</span>
          <span class="nr-anexo-info"><span class="nr-anexo-nome" title="${escapeHtml(item.nome_arquivo)}">${escapeHtml(item.nome_arquivo)}</span>
            <span class="nr-anexo-meta">Documento original · ${item.origemManual ? 'enviado pela tela' : 'anexo do e-mail'}${item.xmlUrl && !data.semPdf ? ' · com XML da nota' : ''}</span></span>
        </div>
        <div class="nr-anexo-acoes">
          <a class="note-file" href="${escapeHtml(backendUrl() + item.downloadUrl)}" target="_blank" rel="noopener">${data.semPdf ? 'Abrir XML' : 'Abrir / imprimir PDF'}</a>
          <a class="note-file" href="${escapeHtml(backendUrl() + item.downloadUrl)}" download="${escapeHtml(item.nome_arquivo)}">Baixar cópia</a>
          ${item.xmlUrl && !data.semPdf ? `<a class="note-file" href="${escapeHtml(backendUrl() + item.xmlUrl)}" download="${escapeHtml(data.xmlArquivo?.nome || 'nota-fiscal.xml')}">XML</a>` : ''}
        </div>`}
        <a class="note-file nr-anexo-email" href="mailto:?subject=${encodeURIComponent(mailSubject)}&body=${encodeURIComponent(mailBody)}">✉ Preparar e-mail ao financeiro</a>
      </section>`;

    const acoesRodape = `
      ${data.semPdf || ignored || item.status === 'AVISO' ? '' : '<button class="ghost small" type="button" data-action="extract">Extrair dados do PDF</button>'}
      ${!ignored && item.status !== 'AVISO' && !['ASSOCIADA', 'DESCARTADA', 'EM_ANALISE'].includes(item.status) ? '<button class="ghost small" type="button" data-action="analysis" title="Nota em dúvida: sai da fila e fica separada até você decidir">Deixar em análise</button>' : ''}
      ${item.status === 'EM_ANALISE' ? '<button class="ghost small" type="button" data-action="release">Voltar para a fila</button>' : ''}
      ${!ignored && item.status !== 'AVISO' && !finalStatus ? '<button class="ghost small nr-risco" type="button" data-action="discard">Descartar nota</button>' : ''}
      ${item.status === 'DESCARTADA' ? '<button class="ghost small" type="button" data-action="restore">Restaurar nota</button>' : ''}`;

    const subtitulo = (() => {
      const mes = /^(\d{4})-(\d{2})/.exec(String(data.competencia || data.dataVencimento || ''));
      const xml = data.xmlFiscal?.ok ? data.xmlFiscal : null;
      const partes = [
        mes ? `${data.tipoDocumento === 'nota_fiscal' ? 'Nota fiscal' : 'Fatura'} do mês ${mes[2]}/${mes[1]}` : (item.assunto || ''),
        xml ? `${XML_TYPES[xml.tipoXml] || 'Nota fiscal'} nº ${xml.numero || '—'}${xml.serie ? ` · série ${xml.serie}` : ''}` : '',
      ].filter(Boolean);
      return partes.join(' · ');
    })();
    const remetente = String(item.remetente || '').replace('[object Object]', '').trim() || '— (não informado pelo Gmail)';

    return `<div class="nr-item${open ? ' is-open' : ''}" data-note-id="${escapeHtml(item.id)}" data-group="${group}">
      <h4 class="nr-item-h">
        <button type="button" class="nr-acc-btn" data-action="toggle-note" id="${pid}-btn" aria-expanded="${open}" aria-controls="${pid}-pan">
          <span class="nr-acc-main"><span class="nr-acc-title">${escapeHtml(issuer)}</span><span class="nr-acc-sub">${escapeHtml(item.assunto || item.nome_arquivo)}</span></span>
          <span class="nr-acc-meta">${escapeHtml(formatMoney(data.valorTotal))}<br>venc. ${escapeHtml(shortDate(data.dataVencimento))}</span>
          <span class="nr-acc-meta">${escapeHtml(formatDate(item.recebida_em || item.created_at))}</span>
          ${item.origemManual ? `<span class="nr-badge" data-role="manual-badge" title="Enviado pela tela, sem e-mail">${data.aguardandoIA ? 'Manual · aguardando a IA' : 'Manual'}</span>` : ''}
          ${badge(item, aval)}
          <span class="nr-acc-icon" aria-hidden="true"></span>
        </button>
      </h4>
      <div class="nr-acc-panel nr-modal" id="${pid}-pan" role="dialog" aria-modal="true" aria-labelledby="${pid}-tit"${open ? '' : ' hidden'}>
        <div class="nr-modal-box">
          <header class="nr-m-head">
            <div class="nr-m-id"><h3 class="nr-m-tit" id="${pid}-tit">${escapeHtml(issuer)}</h3><div class="nr-m-sub">${escapeHtml(subtitulo)}</div></div>
            <div class="nr-m-dir">
              <div class="nr-m-valor-box"><div class="nr-m-valor">${escapeHtml(formatMoney(data.valorTotal))}</div><div class="nr-m-venc">venc. ${escapeHtml(shortDate(data.dataVencimento))}</div></div>
              ${badge(item, aval)}
              <button type="button" class="nr-m-fechar" data-action="close-note" aria-label="Fechar">✕</button>
            </div>
          </header>
          <div class="nr-m-meta">
            <span>Status: <b class="nr-m-status">${escapeHtml(statusLabel(item.status))}</b></span>
            <span>Remetente: <b>${escapeHtml(remetente)}</b></span>
            <span>Recebido em: <b>${escapeHtml(formatDate(item.recebida_em || item.created_at))}</b></span>
          </div>
          <div class="nr-m-corpo">
            <div class="nr-m-esq">
              ${formularios}
              ${manualBlock(item, data)}
              ${ignored ? triageBlock(data) : ''}
              ${avisoBlock(data)}
              ${item.status === 'DESCARTADA' ? `<div class="nr-aviso" role="note">Descartada: ${escapeHtml(DISCARD_REASONS[data.descarte?.motivo] || data.descarte?.motivo || '—')}${data.descarte?.detalhe ? ` · ${escapeHtml(data.descarte.detalhe)}` : ''}${data.descarte?.operador ? ` · por ${escapeHtml(data.descarte.operador)}` : ''}</div>` : ''}
              ${item.status === 'EM_ANALISE' ? `<div class="nr-aviso" role="note">Em análise desde ${escapeHtml(formatDate(data.analise?.em))}${data.analise?.operador ? ` · por ${escapeHtml(data.analise.operador)}` : ''}${data.analise?.observacao ? ` · ${escapeHtml(data.analise.observacao)}` : ''}</div>` : ''}
              <section class="nr-card">
                <h5 class="nr-card-t">Dados da nota <small>${data.xmlFiscal?.ok ? 'Fonte: XML (prioridade sobre o PDF)' : 'Fonte: leitura do PDF'}</small></h5>
                ${dadosBody}
              </section>
              ${disclosure(item.id, 'motivo', 'ⓘ Por que está nesta lista', motivoBody, false)}
            </div>
            <div class="nr-m-dir-col">
              ${associarCard}
              ${arquivosCard}
            </div>
          </div>
          <footer class="nr-m-rodape">
            <div class="nr-m-rodape-esq">${acoesRodape}<span class="hint" data-role="extract-status" aria-live="polite"></span></div>
            ${podeAssociar ? `<div class="nr-m-rodape-dir"><span class="hint">Confira os dados da nota antes de validar.</span>
              <button class="primary" type="button" data-action="compare"${selectedLocation ? '' : ' disabled'}>Validar nota no local</button></div>` : ''}
          </footer>
        </div>
      </div>
    </div>`;
  }

  function renderGroups() {
    const byGroup = new Map(GROUPS.map((g) => [g.key, []]));
    items.forEach((item) => byGroup.get(groupOf(item)).push(item));
    const present = GROUPS.filter((g) => byGroup.get(g.key).length);
    return present.map((g) => {
      const saved = groupState.get(g.key);
      const open = saved === undefined ? (g.open || present.length === 1) : saved;
      return `<details class="nr-list" data-list="${g.key}"${open ? ' open' : ''}>
        <summary><span class="nr-list-title">${escapeHtml(g.title)}</span><span class="nr-count">${byGroup.get(g.key).length}</span><span class="hint">${escapeHtml(g.hint)}</span></summary>
        <div class="nr-acc" data-accordion="${g.key}">${byGroup.get(g.key).map((item) => renderCard(item, g.key)).join('')}</div>
      </details>`;
    }).join('');
  }

  // Accordion clássico: abrir um e-mail fecha o que estava aberto na mesma lista.
  function setNoteOpen(card, open) {
    const button = card.querySelector('[data-action="toggle-note"]');
    const panel = card.querySelector('.nr-acc-panel');
    button.setAttribute('aria-expanded', String(open));
    panel.hidden = !open;
    card.classList.toggle('is-open', open);
    document.body.classList.toggle('nr-modal-aberto', Boolean(document.querySelector('#notasRecebidasLista .nr-item.is-open')));
    if (open) panel.querySelector('.nr-m-fechar')?.focus({ preventScroll: true });
  }
  // A nota aberta é um modal: abrir uma fecha a que estava aberta (em qualquer lista).
  function toggleNote(card) {
    const group = card.dataset.group;
    const opening = openNotes.get(group) !== card.dataset.noteId;
    document.querySelectorAll('#notasRecebidasLista .nr-item.is-open').forEach((other) => setNoteOpen(other, false));
    openNotes.clear();
    if (opening) setNoteOpen(card, true);
    openNotes.set(group, opening ? card.dataset.noteId : null);
  }
  function openDisclosure(card, key) {
    const d = card?.querySelector(`details.nr-disc[data-disc="${key}"]`);
    if (d) d.open = true;
  }
  // Abre a lista, o e-mail e todas as partes (usado por atalhos e testes).
  function abrir(id) {
    const card = [...document.querySelectorAll('#notasRecebidasLista [data-note-id]')].find((el) => el.dataset.noteId === id);
    if (!card) return false;
    const list = card.closest('details.nr-list');
    if (list) list.open = true;
    groupState.set(card.dataset.group, true);
    if (openNotes.get(card.dataset.group) !== id) toggleNote(card);
    card.querySelectorAll('details.nr-disc').forEach((d) => {
      d.open = true;
      discState.set(`${id}:${d.dataset.disc}`, true);
    });
    return true;
  }

  // Cada atualização da lista recebe um número; só a mais recente pode desenhar a lista
  // (evita que uma resposta antiga, de outro filtro, sobrescreva a atual).
  let renderSeq = 0;
  async function loadData(seq = renderSeq) {
    const status = byId('notasRecebidasFiltro').value;
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    const [notesResponse, locationsResponse, ignoredResponse] = await Promise.all([
      request(`/api/notas-recebidas${query}`),
      request('/api/locais'),
      status ? Promise.resolve({ items: [] }) : request('/api/notas-recebidas?status=IGNORADA_IA'),
    ]);
    if (seq !== renderSeq) return false;
    items = [...(notesResponse.items || []), ...(ignoredResponse.items || [])];
    locations = locationsResponse.items || [];
    return true;
  }

  async function renderTab(preserveStatus = false) {
    const list = byId('notasRecebidasLista');
    if (!list) return;
    const seq = ++renderSeq;
    const manual = byId('notasRecebidasManual');
    if (manual) manual.hidden = !podeAdicionar();  // a API confere de novo (permissão de associar notas)
    list.innerHTML = '<div class="dash-empty">Carregando notas recebidas…</div>';
    if (!preserveStatus) byId('notasRecebidasStatus').textContent = '';
    try {
      if (!(await loadData(seq))) return;
      list.innerHTML = items.length
        ? renderGroups()
        : '<div class="dash-empty">Nenhuma nota recebida para este filtro.</div>';
      document.body.classList.toggle('nr-modal-aberto', Boolean(list.querySelector('.nr-item.is-open')));
      renderTriageSummary();
    } catch (error) {
      list.innerHTML = '<div class="dash-empty">Não foi possível carregar as notas recebidas.</div>';
      byId('notasRecebidasStatus').textContent = error.message;
    }
  }

  async function extractFields(card) {
    const item = items.find((entry) => entry.id === card.dataset.noteId);
    if (!item) return;
    const button = card.querySelector('[data-action="extract"]');
    const status = card.querySelector('[data-role="extract-status"]');
    button.disabled = true;
    button.textContent = 'Extraindo…';
    status.textContent = '';
    try {
      const result = await request(`/api/notas-recebidas/${encodeURIComponent(item.id)}/extrair`, {
        method: 'POST',
      });
      const fields = result.dados || {};
      const fieldMap = {
        emissorNome: 'issuer',
        numero: 'number',
        chave: 'key',
        valorTotal: 'amount',
        dataEmissao: 'issue-date',
        dataVencimento: 'due-date',
        descricaoServico: 'description',
      };
      Object.entries(fieldMap).forEach(([key, role]) => {
        const input = card.querySelector(`[data-role="${role}"]`);
        const value = fields[key];
        if (!input || value === null || value === undefined || value === '') return;
        // Não sobrescreve o que o usuário digitou; troca vazio ou valor padrão pela nova leitura.
        if (input.value && input.value !== DEFAULT_ID && input.dataset.extracted !== input.value) return;
        input.value = value;
        input.dataset.extracted = String(value);
      });
      const origin = card.querySelector('[data-role="issue-origin"]');
      if (origin) {
        origin.textContent = fields.dataEmissaoOrigem === 'recebimento'
          ? 'Não encontrada no documento: usada a data de recebimento.'
          : 'Lida no documento.';
      }
      const cnpj = fields.cnpjDestinatario || fields.cnpjEmissor;
      if (cnpj) card.querySelector('[data-role="cnpj"]').textContent = cnpj;
      const missing = Array.isArray(fields.camposParaRevisar) ? fields.camposParaRevisar : [];
      const source = result.ocrUsado ? 'OCR da imagem' : 'texto do PDF';
      if (result.gravada) {
        card.querySelector('[data-role="stale-reading"]')?.remove();
        item.leituraDesatualizada = false;
      }
      openDisclosure(card, 'dados');
      status.textContent = `Extração concluída usando ${source}${result.gravada ? ' e gravada' : ''}. Revise os campos antes de associar.`
        + (missing.length ? ` Não identificados: ${missing.join(', ')}.` : '');
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = 'Extrair dados do PDF';
    }
  }

  function collectReviewedData(card) {
    return {
      emissorNome: card.querySelector('[data-role="issuer"]').value.trim(),
      numero: card.querySelector('[data-role="number"]').value.trim(),
      chave: card.querySelector('[data-role="key"]').value.trim(),
      valorTotal: Number(card.querySelector('[data-role="amount"]').value),
      dataEmissao: card.querySelector('[data-role="issue-date"]').value,
      dataVencimento: card.querySelector('[data-role="due-date"]').value,
      descricaoServico: card.querySelector('[data-role="description"]').value.trim(),
    };
  }

  function activeComparison(card) {
    const saved = comparisons.get(card.dataset.noteId);
    if (!saved) return null;
    const data = collectReviewedData(card);
    const type = card.querySelector('[data-role="type"]').value;
    const localId = card.querySelector('[data-role="location"]').value;
    if (JSON.stringify(saved.data) !== JSON.stringify(data) || saved.type !== type || saved.localId !== localId) {
      comparisons.delete(card.dataset.noteId);
      card.querySelector('[data-role="comparison"]').replaceChildren();
      return null;
    }
    return saved;
  }

  function renderComparison(card, comparison) {
    openDisclosure(card, 'associar');
    const target = card.querySelector('[data-role="comparison"]');
    const candidates = comparison.candidatas || [];
    if (!candidates.length) {
      const otherNotes = comparison.outrasNotasMesmoProvedor || [];
      target.innerHTML = `<div class="full"><b>Nenhuma nota correspondente encontrada neste local.</b>
        <div>Esta associação criará uma nova nota disponível no local e manterá os registros anteriores.</div>
        ${otherNotes.length ? `<div class="hint">Há ${otherNotes.length} outra(s) nota(s) do mesmo provedor com vencimento diferente; elas serão preservadas.</div>` : ''}
        <button class="primary small" type="button" data-action="commit">Associar como nova nota disponível</button>
        <button class="ghost small" type="button" data-action="keep">Não associar agora</button></div>`;
      return;
    }
    const selectedId = target.querySelector('[data-role="candidate"]')?.value || candidates[0].notaDisponivelId;
    const selected = candidates.find((candidate) => candidate.notaDisponivelId === selectedId) || candidates[0];
    const candidateOptions = candidates.length > 1
      ? `<label class="full">Nota disponível para comparar
          <select class="f" data-role="candidate">${candidates.map((candidate) =>
        `<option value="${escapeHtml(candidate.notaDisponivelId)}" ${candidate.notaDisponivelId === selected.notaLancadaId ? 'selected' : ''}>${escapeHtml(candidate.numero || candidate.chave || candidate.notaDisponivelId)} — ${escapeHtml(candidate.dataVencimento || 'sem vencimento')}</option>`
      ).join('')}</select>
        </label>` : '';
    const differences = selected.diferencas || [];
    const differenceMarkup = differences.length
      ? `<div class="full"><b>Divergências encontradas — nota atual × nota recebida</b>
          <div>${differences.map((difference) =>
        `<div><b>${escapeHtml(difference.campo)}:</b> ${escapeHtml(difference.atual ?? '—')} → ${escapeHtml(difference.recebida ?? '—')}</div>`
      ).join('')}</div>
          <label class="full"><input type="checkbox" data-role="confirm-update"> Aceito as divergências e autorizo atualizar esta nota e substituir o PDF vinculado.</label>
          <button class="primary small" type="button" data-action="commit" disabled>Aceitar divergências e atualizar</button>
        </div>`
      : `<div class="full"><b>Nota disponível desta cobrança encontrada, sem divergências.</b> O documento entra junto (não substitui).
          <div>Número: ${escapeHtml(selected.numero || '—')} · Vencimento: ${escapeHtml(selected.dataVencimento || '—')} · Valor: ${escapeHtml(formatMoney(selected.valorTotal))}</div>
          <button class="primary small" type="button" data-action="commit">Juntar à nota disponível (mesma cobrança)</button>
        </div>`;
    target.innerHTML = `<div class="full">${candidateOptions}${differenceMarkup}
      <button class="ghost small" type="button" data-action="keep">Não associar agora</button></div>`;
  }

  async function compareTarget(card) {
    const item = items.find((entry) => entry.id === card.dataset.noteId);
    const type = card.querySelector('[data-role="type"]').value;
    const localId = card.querySelector('[data-role="location"]').value;
    const data = collectReviewedData(card);
    if (!item || !localId) {
      byId('notasRecebidasStatus').textContent = 'Escolha o tipo e o local alvo antes de validar.';
      return;
    }
    // Obrigatórios: emissor, valor e vencimento (entrada manual se o OCR não achou).
    // Número/chave vazios recebem o valor padrão; emissão vazia vira a data de recebimento.
    const missingRequired = [
      !data.emissorNome ? ['issuer', 'emissor/provedor'] : null,
      !Number.isFinite(data.valorTotal) || data.valorTotal <= 0 ? ['amount', 'valor'] : null,
      !data.dataVencimento ? ['due-date', 'data de vencimento'] : null,
    ].filter(Boolean);
    card.querySelectorAll('[data-role="issuer"],[data-role="amount"],[data-role="due-date"]')
      .forEach((input) => input.removeAttribute('aria-invalid'));
    if (missingRequired.length) {
      missingRequired.forEach(([role]) => card.querySelector(`[data-role="${role}"]`).setAttribute('aria-invalid', 'true'));
      openDisclosure(card, 'dados');
      card.querySelector(`[data-role="${missingRequired[0][0]}"]`).focus();
      byId('notasRecebidasStatus').textContent =
        `Preencha manualmente: ${missingRequired.map(([, label]) => label).join(', ')} (obrigatórios).`;
      return;
    }
    const button = card.querySelector('[data-action="compare"]');
    button.disabled = true;
    try {
      const response = await request(`/api/notas-recebidas/${encodeURIComponent(item.id)}/comparar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entidadeTipo: type, entidadeId: localId, dados: data }),
      });
      comparisons.set(item.id, { type, localId, data, comparacao: response.comparacao });
      renderComparison(card, response.comparacao);
      byId('notasRecebidasStatus').textContent =
        'Comparação concluída. Se houver divergência, escolha explicitamente se deseja atualizar ou manter sem associar.';
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  async function commitAssociation(card) {
    const item = items.find((entry) => entry.id === card.dataset.noteId);
    const validated = activeComparison(card);
    if (!item || !validated) {
      byId('notasRecebidasStatus').textContent = 'Valide novamente o destino; os dados ou local foram alterados.';
      return;
    }
    const candidates = validated.comparacao.candidatas || [];
    const candidateId = card.querySelector('[data-role="candidate"]')?.value
      || (candidates.length === 1 ? candidates[0].notaDisponivelId : '');
    const candidate = candidates.find((entry) => entry.notaDisponivelId === candidateId);
    if (candidate?.diferencas?.length && !card.querySelector('[data-role="confirm-update"]')?.checked) {
      byId('notasRecebidasStatus').textContent = 'Marque o aceite explícito das divergências para atualizar a nota.';
      return;
    }
    const auth = (() => {
      try { return ({ user: window.SIGP_LOGIN?.usuarioAtual?.() || '' }); } catch { return {}; }
    })();
    const button = card.querySelector('[data-action="commit"]');
    if (button) button.disabled = true;
    try {
      const data = collectReviewedData(card);
      const result = await request(`/api/notas-recebidas/${encodeURIComponent(item.id)}/associar`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entidadeTipo: validated.type,
          entidadeId: validated.localId,
          operador: auth.user || '',
          dados: data,
          notaDisponivelId: candidateId,
          confirmarAtualizacao: Boolean(candidate?.diferencas?.length),
        }),
      });
      const localWarning = await addAssociatedNoteToLocal(item, result, data, validated.type, validated.localId);
      byId('notasRecebidasStatus').textContent =
        `Nota disponível associada ao local${result.notaLancada ? ' e ligada à nota lançada pelo financeiro' : ' (aguardando o lançamento do financeiro)'}. O n8n pode aplicar a etiqueta Gmail “${result.gmailLabel}”.${localWarning}`;
      comparisons.delete(item.id);
      selectedNewLocation = null;
      await renderTab(true);
    } catch (error) {
      if (button) button.disabled = false;
      byId('notasRecebidasStatus').textContent = error.message;
    }
  }

  function keepUnassociated(card) {
    const item = items.find((entry) => entry.id === card.dataset.noteId);
    if (!item || item.status === 'ASSOCIADA') return;
    comparisons.delete(item.id);
    card.querySelector('[data-role="comparison"]').replaceChildren();
    byId('notasRecebidasStatus').textContent =
      'Associação não feita. A nota continua como estava; use “Deixar em análise” se ela estiver em dúvida.';
  }
  async function markForAnalysis(card) {
    const item = items.find((entry) => entry.id === card.dataset.noteId);
    if (!item) return;
    const button = card.querySelector('[data-action="analysis-confirm"]');
    button.disabled = true;
    try {
      await request(`/api/notas-recebidas/${encodeURIComponent(item.id)}/analise`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ observacao: card.querySelector('[data-role="analysis-note"]').value.trim(), operador: currentOperator() }),
      });
      comparisons.delete(item.id);
      byId('notasRecebidasStatus').textContent = 'Nota deixada em análise. Ela fica no filtro “Em análise” até você associar, descartar ou voltar para a fila.';
      await renderTab(true);
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
      button.disabled = false;
    }
  }
  async function releaseFromAnalysis(card) {
    const item = items.find((entry) => entry.id === card.dataset.noteId);
    if (!item) return;
    try {
      await request(`/api/notas-recebidas/${encodeURIComponent(item.id)}/liberar`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operador: currentOperator() }),
      });
      byId('notasRecebidasStatus').textContent = 'Nota devolvida para a fila de associação.';
      await renderTab(true);
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
    }
  }

  async function discardNote(card) {
    const item = items.find((entry) => entry.id === card.dataset.noteId);
    if (!item) return;
    const reason = card.querySelector('[data-role="discard-reason"]').value;
    if (!reason) {
      byId('notasRecebidasStatus').textContent = 'Escolha o motivo do descarte.';
      card.querySelector('[data-role="discard-reason"]').focus();
      return;
    }
    const button = card.querySelector('[data-action="discard-confirm"]');
    button.disabled = true;
    try {
      await request(`/api/notas-recebidas/${encodeURIComponent(item.id)}/descartar`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          motivo: reason,
          detalhe: card.querySelector('[data-role="discard-detail"]').value.trim(),
          operador: currentOperator(),
        }),
      });
      byId('notasRecebidasStatus').textContent = 'Nota descartada. Ela continua disponível no filtro “Descartada”.';
      await renderTab(true);
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
      button.disabled = false;
    }
  }

  async function restoreNote(card) {
    const item = items.find((entry) => entry.id === card.dataset.noteId);
    if (!item) return;
    try {
      await request(`/api/notas-recebidas/${encodeURIComponent(item.id)}/restaurar`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operador: currentOperator() }),
      });
      byId('notasRecebidasStatus').textContent = 'Nota restaurada para a caixa de recebidas.';
      await renderTab(true);
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
    }
  }

  async function addAssociatedNoteToLocal(item, result, data, type, localId) {
    const storageKey = LOCATION_KEYS[type];
    if (!storageKey) return 'Tipo de local não reconhecido para atualizar o cadastro local.';
    try {
      const records = JSON.parse(localStorage.getItem(storageKey) || '[]');
      if (!Array.isArray(records)) throw new Error(`O cadastro ${storageKey} não é uma lista.`);
      const local = records.find((entry) => String(entry.id) === String(localId));
      if (!local) throw new Error('O local associado não foi encontrado no cadastro deste navegador.');
      if (!Array.isArray(local.notasFiscais)) local.notasFiscais = [];

      // Documento do e-mail é NOTA DISPONÍVEL (fica na API, aparece no local); nota lançada é só do financeiro.
      // Linha antiga "nota lançada" do Gmail (id gmail-...) sai da cópia deste navegador.
      local.notasFiscais = local.notasFiscais.filter((entry) => !(String(entry.notaLancada?.id || '').startsWith('gmail-') && !entry.notaPaga));
      // P2-04: aplica no cadastro do navegador o mesmo provedor que a API atualizou (nome, valor, vencimento).
      // Sem isso, a próxima gravação do local a partir do navegador desfaria a atualização.
      let providerMessage = '';
      const provider = result.provedor;
      if (provider && (['criado', 'atualizado'].includes(result.provedorAcao) || (result.codigosAprendidos || []).length)) {
        if (!Array.isArray(local.provedores)) local.provedores = [];
        const index = local.provedores.findIndex((entry) => entry && String(entry.id || '') === String(provider.id));
        if (index >= 0) local.provedores[index] = { ...local.provedores[index], ...provider };
        else local.provedores.push(provider);
        providerMessage = result.provedorAcao === 'criado'
          ? ` Provedor “${provider.nome}” criado no local com vencimento em ${provider.dataVencimento}.`
          : ` Provedor “${provider.nome}” atualizado: vencimento ${provider.dataVencimento}, valor R$ ${provider.valor}.`;
      } else if (result.provedorAviso) {
        providerMessage = ` ${result.provedorAviso}`;
      }
      if ((result.codigosAprendidos || []).length) {
        providerMessage += ` Código do cliente/contrato guardado no provedor: ${result.codigosAprendidos.join(', ')}.`;
      }
      if ((result.codigosEmOutroLocal || []).length) {
        providerMessage += ` O código ${result.codigosEmOutroLocal.join(', ')} já está em outro local deste provedor e não foi guardado aqui.`;
      }
      if (result.documentoAdicional) {
        providerMessage += ' Esta cobrança já tinha fatura: o documento entrou como adicional (a fatura principal foi mantida).';
      }
      localStorage.setItem(storageKey, JSON.stringify(records));
      window.dispatchEvent(new CustomEvent('sigp:locais-atualizados', { detail: { tipo: type, id: localId } }));
      await window.SIGP_API.persistLocation(storageKey);
      return providerMessage;
    } catch (error) {
      return ` A nota foi gravada na API, mas não foi possível atualizar o cadastro local: ${error.message}`;
    }
  }

  function rememberNewLocation(item) {
    const key = LOCATION_KEYS[item.tipo];
    if (!key) return;
    const current = JSON.parse(localStorage.getItem(key) || '[]');
    if (!Array.isArray(current)) throw new Error(`O cadastro local ${key} não é uma lista.`);
    if (!current.some((entry) => String(entry.id) === String(item.id))) {
      localStorage.setItem(key, JSON.stringify([...current, item]));
    }
  }

  async function createLocation() {
    const type = byId('notaRecebidaNovoTipo').value;
    const name = byId('notaRecebidaNovoNome').value.trim();
    const city = byId('notaRecebidaNovaCidade').value.trim();
    if (!name) {
      byId('notasRecebidasStatus').textContent = 'Informe o nome do novo local.';
      return;
    }
    const button = byId('notaRecebidaCriarLocal');
    button.disabled = true;
    try {
      const result = await request(`/api/locais/${type}/item`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome: name, cidade: city }),
      });
      rememberNewLocation(result.item);
      const target = items.find((entry) => entry.status !== 'ASSOCIADA');
      selectedNewLocation = target ? { local: result.item, noteId: target.id } : null;
      byId('notaRecebidaNovoNome').value = '';
      byId('notaRecebidaNovaCidade').value = '';
      byId('notasRecebidasStatus').textContent = target
        ? `Local “${result.item.nome}” cadastrado e selecionado para a primeira nota aguardando associação.`
        : `Local “${result.item.nome}” cadastrado.`;
      await renderTab(true);
    } catch (error) {
      byId('notasRecebidasStatus').textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  byId('notasRecebidasAtualizar').addEventListener('click', renderTab);
  byId('notasRecebidasFiltro').addEventListener('change', renderTab);
  byId('notasRecebidasTriagem')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    if (button.dataset.action === 'show-ignored') {
      byId('notasRecebidasFiltro').value = 'IGNORADA_IA';
      renderTab();
    }
    if (button.dataset.action === 'ignore-confirm-all'
      && window.confirm(`Confirmar que os ${items.length} documento(s) desta lista não são cobrança de provedor?`)) {
      confirmIgnored(items.filter((i) => i.status === 'IGNORADA_IA').map((i) => i.id));
    }
  });
  byId('notaRecebidaCriarLocal').addEventListener('click', createLocation);
  byId('nrManualEnviar')?.addEventListener('click', enviarManual);
  byId('notasRecebidasLista').addEventListener('change', (event) => {
    const card = event.target.closest('[data-note-id]');
    if (!card) return;
    if (event.target.dataset.role === 'type') {
      const locationSelect = card.querySelector('[data-role="location"]');
      locationSelect.innerHTML = optionsForLocations(event.target.value);
    }
    if (['type', 'location'].includes(event.target.dataset.role)) {
      // "Validar nota no local" (único botão primário) só com o local escolhido.
      const validar = card.querySelector('[data-action="compare"]');
      if (validar) validar.disabled = !card.querySelector('[data-role="location"]')?.value;
    }
    if (event.target.dataset.role === 'confirm-update') {
      const button = card.querySelector('[data-action="commit"]');
      if (button) button.disabled = !event.target.checked;
      return;
    }
    if (event.target.dataset.role === 'candidate') {
      const saved = comparisons.get(card.dataset.noteId);
      if (saved) renderComparison(card, saved.comparacao);
      return;
    }
    comparisons.delete(card.dataset.noteId);
    card.querySelector('[data-role="comparison"]')?.replaceChildren();
  });
  byId('notasRecebidasLista').addEventListener('input', (event) => {
    const card = event.target.closest('[data-note-id]');
    if (!card || !event.target.dataset.role || event.target.dataset.role === 'confirm-update') return;
    comparisons.delete(card.dataset.noteId);
    card.querySelector('[data-role="comparison"]')?.replaceChildren();
  });
  // Modal da nota: Esc ou clique fora da caixa fecha (o cabeçalho na lista também fecha).
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const aberto = document.querySelector('#notasRecebidasLista .nr-item.is-open');
    if (aberto && !aberto.querySelector('.nr-modal')?.hidden) toggleNote(aberto);
  });
  byId('notasRecebidasLista').addEventListener('mousedown', (event) => {
    if (!event.target.classList?.contains('nr-modal')) return;
    const card = event.target.closest('[data-note-id]');
    if (card) toggleNote(card);
  });
  byId('notasRecebidasLista').addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const card = button.closest('[data-note-id]');
    if (button.dataset.action === 'toggle-note') toggleNote(card);
    if (button.dataset.action === 'close-note' && card.classList.contains('is-open')) toggleNote(card);
    if (button.dataset.action === 'extract') extractFields(card);
    if (button.dataset.action === 'compare') compareTarget(card);
    if (button.dataset.action === 'commit') commitAssociation(card);
    if (button.dataset.action === 'keep') keepUnassociated(card);
    if (button.dataset.action === 'analysis') card.querySelector('[data-role="analysis-form"]').hidden = false;
    if (button.dataset.action === 'analysis-cancel') card.querySelector('[data-role="analysis-form"]').hidden = true;
    if (button.dataset.action === 'analysis-confirm') markForAnalysis(card);
    if (button.dataset.action === 'release') releaseFromAnalysis(card);
    if (button.dataset.action === 'ignore-confirm') confirmIgnored([card.dataset.noteId]);
    if (button.dataset.action === 'rescue') rescueIgnored(card);
    if (button.dataset.action === 'discard') card.querySelector('[data-role="discard-form"]').hidden = false;
    if (button.dataset.action === 'discard-cancel') card.querySelector('[data-role="discard-form"]').hidden = true;
    if (button.dataset.action === 'discard-confirm') discardNote(card);
    if (button.dataset.action === 'restore') restoreNote(card);
    if (button.dataset.action === 'relink') relinkAviso(card);
  });

  // Guarda o que o operador abriu ou fechou, para a lista não recolher a cada atualização.
  byId('notasRecebidasLista').addEventListener('toggle', (event) => {
    const d = event.target;
    if (d.matches?.('details.nr-list')) groupState.set(d.dataset.list, d.open);
    if (d.matches?.('details.nr-disc')) {
      const card = d.closest('[data-note-id]');
      if (card) discState.set(`${card.dataset.noteId}:${d.dataset.disc}`, d.open);
    }
  }, true);
  // Teclado no accordion: setas, Home e End passam entre os e-mails da mesma lista.
  byId('notasRecebidasLista').addEventListener('keydown', (event) => {
    const button = event.target.closest?.('[data-action="toggle-note"]');
    if (!button || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    const all = [...button.closest('.nr-acc').querySelectorAll(':scope > .nr-item [data-action="toggle-note"]')];
    const i = all.indexOf(button);
    const next = { ArrowDown: all[(i + 1) % all.length], ArrowUp: all[(i - 1 + all.length) % all.length], Home: all[0], End: all[all.length - 1] }[event.key];
    event.preventDefault();
    next?.focus();
  });

  window.SIGP_NOTAS_RECEBIDAS = { renderTab, abrir };
})();
