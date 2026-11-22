// Aba SIE — Sistema de Informação Executiva: só ciclos fechados (nota lançada + nota paga + fatura com MATCH)
// e a análise executiva gravada pelo n8n. Dados de GET /api/sie/resumo.
(() => {
  const formatMoney = (value) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value) || 0);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
  const apiBase = () => window.SIGP_CONFIG.apiUrl();

  function monthLabel(value) {
    const [year, month] = value.split('-').map(Number);
    return new Intl.DateTimeFormat('pt-BR', { month: 'short', year: '2-digit' }).format(new Date(year, month - 1, 1));
  }

  function renderBars(rows) {
    const maximum = Math.max(1, ...rows.map((row) => Number(row.valor) || 0));
    return rows.map((row) => `<div class="sig-bar-row" title="${escapeHtml(row.nome)}: ${formatMoney(row.valor)}">
        <div class="sig-bar-label">${escapeHtml(row.nome)}</div>
        <div class="sig-bar-track"><span style="width:${Math.max(3, (row.valor / maximum) * 100)}%"></span></div>
        <div class="sig-bar-value">${formatMoney(row.valor)}</div>
      </div>`).join('') || '<div class="dash-empty">Nenhum ciclo fechado no período.</div>';
  }

  function renderMonthly(rows) {
    const maximum = Math.max(1, ...rows.map((row) => Number(row.valor) || 0));
    return rows.map((row) => `<div class="sig-month" aria-label="${escapeHtml(monthLabel(row.mes))}: ${formatMoney(row.valor)}">
        <div class="sig-month-bars"><span class="sig-month-paid" style="height:${row.valor ? Math.max(2, (row.valor / maximum) * 100) : 0}%" title="${formatMoney(row.valor)}"></span></div>
        <span>${escapeHtml(monthLabel(row.mes))}</span>
      </div>`).join('');
  }

  function renderAnalyses(items) {
    if (!items.length) {
      return '<div class="dash-empty">Nenhuma análise executiva ainda. O n8n gera uma quando o gerente valida um ciclo fechado na aba SIG.</div>';
    }
    const IMPACTO = { nenhum: 'Nenhum', baixo: 'Baixo', medio: 'Médio', alto: 'Alto' };
    return items.map((item) => {
      const decisao = item.dados?.decisaoGerente;
      const impacto = item.dados?.resumoExecutivoLLM?.impacto;
      return `<article style="margin-bottom:12px">
        <p class="hint">${escapeHtml(new Date(item.created_at).toLocaleString('pt-BR'))}${item.titulo ? ` · <strong>${escapeHtml(item.titulo)}</strong>` : ''}${impacto ? ` · impacto ${escapeHtml(IMPACTO[impacto] || impacto)}` : ''}${item.modelo ? ` · ${escapeHtml(item.modelo)}` : ''}</p>
        <div style="white-space:pre-wrap">${escapeHtml(item.conteudo)}</div>
        ${decisao ? `<p class="hint">${decisao.status === 'CORRIGIDA' ? 'Validada com correção' : 'Validada'} pelo gerente ${escapeHtml(decisao.usuario || '')}${decisao.justificativa ? ` · ${escapeHtml(decisao.justificativa)}` : ''}</p>` : ''}
      </article>`;
    }).join('');
  }

  function renderReceivedInvoices(items) {
    const labels = {
      AGUARDANDO_PAGAMENTO: 'Aguardando pagamento',
      AGUARDANDO_FATURA: 'Aguardando fatura',
      PAGO_PARCIAL: 'Pagamento parcial',
      MATCH: 'Conferida (MATCH)',
      DIVERGENCIA: 'Divergência',
      PENDENTE: 'Pendente',
    };
    if (!items.length) return '<div class="dash-empty">Nenhuma nota recebida associada no período.</div>';
    return items.map((item) => `<article class="nfse-card" style="margin-top:10px">
      <h4>${escapeHtml(item.provedor)}${item.numero ? ` · nº ${escapeHtml(item.numero)}` : ''}</h4>
      <div class="nfse-grid">
        <div><b>Local</b><div>${escapeHtml(item.local ? `${item.local.nome}${item.local.cidade ? ` — ${item.local.cidade}` : ''}` : 'Local indisponível')}</div></div>
        <div><b>Valor</b><div>${formatMoney(item.valor)}</div></div>
        <div><b>Vencimento</b><div>${escapeHtml(item.dataVencimento || '—')}</div></div>
        <div><b>Andamento no SIG</b><div>${escapeHtml(labels[item.statusFluxo] || item.statusFluxo)}</div></div>
        <div><b>Etiqueta Gmail</b><div>${escapeHtml(item.etiquetaStatus || '—')}</div></div>
      </div>
    </article>`).join('');
  }

  function renderView(data) {
    const k = data.indicadores;
    const variation = data.variacaoMensal
      ? `${data.variacaoMensal.percentual > 0 ? '+' : ''}${data.variacaoMensal.percentual}% em ${escapeHtml(monthLabel(data.variacaoMensal.mesAtual))}`
      : 'sem base de comparação';
    return `
      <div class="vg-brand"><h2>SIE · Sistema de Informação Executiva</h2></div>
      <p class="sub">Os indicadores consideram somente ciclos fechados (nota lançada, paga e fatura conferidas) e <strong>validados pelo gerente</strong> na aba SIG. Notas recebidas por Gmail ainda em andamento aparecem na seção própria abaixo.</p>
      <p class="hint"><a class="note-file" href="${`${location.protocol}//${location.hostname}:5000/`}" target="_blank" rel="noopener">Painel de análises da IA (legado)</a> · histórico das conciliações recebidas do n8n e das análises da IA. Decisões registradas lá não alteram o SIGp; decida aqui.</p>
      <form class="sig-filters" id="sieFilters">
        <div><label for="sieInicio">De</label><input class="f" id="sieInicio" name="inicio" type="date" value="${escapeHtml(data.periodo.inicio)}"></div>
        <div><label for="sieFim">Até</label><input class="f" id="sieFim" name="fim" type="date" value="${escapeHtml(data.periodo.fim)}"></div>
        <div class="sig-filter-actions"><button class="primary small" type="submit">Aplicar</button></div>
      </form>
      <div id="sieError" class="backup-warn" role="alert" hidden></div>
      <div class="sig-kpis">
        <article class="dash-card"><h3>Custo fechado</h3><strong>${formatMoney(k.valorFechado)}</strong><span>${k.ciclosFechados} ciclo(s) fechado(s)</span></article>
        <article class="dash-card"><h3>Custo médio por ciclo</h3><strong>${formatMoney(k.custoMedioPorCiclo)}</strong><span>${k.locaisAtendidos} local(is)</span></article>
        <article class="dash-card"><h3>Taxa de fechamento</h3><strong>${k.taxaFechamento}%</strong><span>de ${k.notasNoPeriodo} nota(s) no período</span></article>
        <article class="dash-card"><h3>Variação mensal</h3><strong>${data.variacaoMensal ? `${data.variacaoMensal.percentual}%` : '—'}</strong><span>${variation}</span></article>
        <article class="dash-card"><h3>Em divergência</h3><strong>${formatMoney(k.valorEmDivergencia)}</strong><span>${k.divergenciasAbertas} nota(s) — detalhe no SIG</span></article>
        <article class="dash-card"><h3>Aguardando o gerente</h3><strong>${formatMoney(k.valorAguardandoGerente || 0)}</strong><span>${k.aguardandoGerente || 0} ciclo(s) fechado(s) ainda sem validação${k.devolvidosPeloGerente ? ` · ${k.devolvidosPeloGerente} devolvido(s)` : ''}</span></article>
      </div>
      <div class="sig-chart-grid">
        <section class="nfse-card"><h3>Análise executiva (IA)</h3>${renderAnalyses(data.analises || [])}</section>
        <section class="nfse-card"><h3>Custo fechado por mês</h3><div class="sig-month-chart" role="img" aria-label="Custo fechado por mês">${renderMonthly(data.mensal)}</div></section>
        <section class="nfse-card"><h3>Por local</h3><div class="sig-ranked">${renderBars(data.porLocal)}</div></section>
        <section class="nfse-card"><h3>Por provedor</h3><div class="sig-ranked">${renderBars(data.porProvedor)}</div></section>
      </div>
      <section class="nfse-card" style="margin-top:16px">
        <h3>Notas recebidas por Gmail · andamento</h3>
        <p class="hint">A lista acompanha notas associadas no SIG. Valores só entram nos indicadores de custo fechado após conciliação de três vias (MATCH).</p>
        ${renderReceivedInvoices(data.notasRecebidas || [])}
      </section>`;
  }

  async function load(container, query = '') {
    const response = await fetch(`${apiBase()}/api/sie/resumo${query ? `?${query}` : ''}`);
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
    container.innerHTML = renderView(data);
    container.querySelector('#sieFilters').addEventListener('submit', async (event) => {
      event.preventDefault();
      const params = new URLSearchParams(new FormData(event.target));
      try {
        await load(container, params.toString());
      } catch (error) {
        const box = container.querySelector('#sieError');
        box.textContent = `Falha ao aplicar o período: ${error.message}.`;
        box.hidden = false;
      }
    });
  }

  async function render() {
    const container = document.getElementById('view_sie');
    if (!container) return;
    container.innerHTML = '<div class="dash-empty" role="status">Carregando o SIE…</div>';
    try {
      await load(container);
    } catch (error) {
      container.innerHTML = `<div class="backup-warn" role="alert">Não foi possível carregar o SIE: ${escapeHtml(error.message || 'falha de comunicação com a API')}.</div>
        <button type="button" class="ghost small" id="sieRetry">Tentar novamente</button>`;
      container.querySelector('#sieRetry').addEventListener('click', render);
    }
  }

  window.SIGP_SIE = { render };
})();
