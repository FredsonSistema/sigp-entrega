// Aba "Painel da IA": acerto da LLM por mês (triagem, campos lidos, local sugerido), tempo por documento,
// memória do modelo e saúde do banco. Dados de GET /api/llm/metricas e GET /api/saude/banco.
(() => {
  const byId = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const apiBase = () => window.SIGP_API.backendUrl().replace(/\/$/, '');
  const pct = (v) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`);
  const segundos = (ms) => (ms ? `${(ms / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s` : '—');
  const bytes = (n) => {
    const v = Number(n) || 0;
    if (v >= 1e9) return `${(v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} GB`;
    if (v >= 1e6) return `${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB`;
    return `${Math.round(v / 1e3)} KB`;
  };
  const mesCurto = (m) => {
    const [a, n] = m.split('-').map(Number);
    return new Intl.DateTimeFormat('pt-BR', { month: 'short', year: '2-digit' }).format(new Date(a, n - 1, 1));
  };
  const CAMPOS = { emissorNome: 'Emissor', numero: 'Número', chave: 'Chave', valorTotal: 'Valor', dataVencimento: 'Vencimento' };

  async function get(path, options) {
    const r = await fetch(`${apiBase()}${path}`, options);
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || `A API respondeu HTTP ${r.status}.`);
    return j;
  }

  function card(titulo, valor, detalhe, id) {
    return `<div class="pia-card"${id ? ` data-role="${id}"` : ''}><div class="pia-card-t">${escapeHtml(titulo)}</div>
      <div class="pia-card-v">${escapeHtml(valor)}</div><div class="hint">${escapeHtml(detalhe)}</div></div>`;
  }

  function barras(mensal) {
    return `<div class="pia-bars" role="img" aria-label="Acurácia da triagem por mês">${mensal.map((m) => {
      const h = m.acuracia === null ? 0 : Math.max(3, m.acuracia * 100);
      return `<div class="pia-bar" title="${escapeHtml(mesCurto(m.mes))}: ${pct(m.acuracia)} (${m.acertos}/${m.decididos})">
        <div class="pia-bar-track"><span style="height:${h}%"></span></div>
        <b>${pct(m.acuracia)}</b><span>${escapeHtml(mesCurto(m.mes))}</span></div>`;
    }).join('')}</div>`;
  }

  function tabela(mensal) {
    const linhas = mensal.map((m) => `<tr>
      <td>${escapeHtml(mesCurto(m.mes))}</td><td>${m.documentos}</td>
      <td>${m.niveis.alta} / ${m.niveis.inconclusivo} / ${m.niveis.baixa}</td>
      <td>${m.decididos ? `${pct(m.acuracia)} <span class="hint">(${m.acertos}/${m.decididos})</span>` : '—'}</td>
      <td>${pct(m.comExemplos.acuracia)} × ${pct(m.semExemplos.acuracia)}</td>
      <td>${pct(m.campos.acuracia)}</td><td>${pct(m.local.acuracia)}</td>
      <td>${segundos(m.tempoMedianoMs)}</td><td>${m.descartesAutomaticos}</td></tr>`).join('');
    return `<div class="pia-table-wrap"><table class="pia-table">
      <thead><tr><th>Mês</th><th>Documentos</th><th>Alta / Inconcl. / Baixa</th><th>Acerto da triagem</th>
      <th>Com × sem exemplos</th><th>Campos sem correção</th><th>Local sugerido certo</th><th>Tempo mediano</th><th>Descartes automáticos</th></tr></thead>
      <tbody>${linhas}</tbody></table></div>`;
  }

  function painelIA(d) {
    const t = d.total;
    const modelo = d.modelo || {};
    const carregado = (modelo.carregados || [])[0];
    const memoria = modelo.disponivel
      ? (carregado ? `${bytes(modelo.memoriaEmUsoBytes)} em uso` : 'Nenhum modelo carregado agora')
      : 'Ollama indisponível';
    const porCampo = Object.entries(t.campos.porCampo || {}).filter(([, v]) => v.total)
      .map(([k, v]) => `${CAMPOS[k] || k} ${pct(v.acuracia)}`).join(' · ');
    return `
      <div class="pia-cards">
        ${card('Acerto da triagem', pct(t.acuracia), t.decididos ? `${t.acertos} de ${t.decididos} decididos · ${t.falsoPositivo} falso(s) positivo(s), ${t.falsoNegativo} falso(s) negativo(s)` : 'Ainda sem documentos decididos no período', 'acuracia')}
        ${card('Documentos lidos', String(t.documentos), `Alta ${t.niveis.alta} · Inconclusivo ${t.niveis.inconclusivo} · Baixa ${t.niveis.baixa}${t.niveis.sem_nivel ? ` · antes da triagem ${t.niveis.sem_nivel}` : ''}`)}
        ${card('Aprendizado (exemplos)', `${pct(t.comExemplos.acuracia)} × ${pct(t.semExemplos.acuracia)}`, `Acerto com exemplos do operador (${t.comExemplos.decididos}) × sem exemplos (${t.semExemplos.decididos})`)}
        ${card('Campos sem correção', pct(t.campos.acuracia), porCampo || 'Medido nas associações')}
        ${card('Local sugerido certo', pct(t.local.acuracia), t.local.total ? `${t.local.acertos} de ${t.local.total} associações` : 'Medido a partir de 14/11/2026')}
        ${card('Tempo por documento', segundos(t.tempoMedianoMs), t.tempoP95Ms ? `mediana · 95% em até ${segundos(t.tempoP95Ms)}` : 'Medido a partir de 14/11/2026')}
        ${card('Memória do modelo', memoria, `${modelo.modeloConfigurado || ''}${carregado ? ` carregado` : ''} · local, sem custo por token`, 'memoria')}
        ${card('Descartes automáticos', String(t.descartesAutomaticos), 'Remetentes confirmados 3 vezes como "não é cobrança"')}
      </div>
      <h4 class="pia-sub">Acerto da triagem por mês</h4>
      ${barras(d.mensal)}
      <details class="nr-disc"><summary>Tabela mensal</summary><div class="nr-disc-body">${tabela(d.mensal)}</div></details>
      <details class="nr-disc"><summary>Como as métricas são calculadas</summary><div class="nr-disc-body hint">
        Acerto da triagem: a IA disse "cobrança" ou "não é cobrança" e você confirmou (associou, resgatou, ou descartou como "não é cobrança").
        Notas sem decisão e descartes por outro motivo (duplicada, ilegível) ficam fora. Descartes automáticos não contam como acerto.
        Campos sem correção: emissor, número, chave, valor e vencimento lidos × o que você confirmou ao associar.
        Local sugerido: a primeira sugestão de local × o local escolhido. Tempo: duração da chamada ao modelo local.</div></details>`;
  }

  const STATUS = { ok: ['OK', 'pia-ok'], atencao: ['Atenção', 'pia-warn'], erro: ['Erro', 'pia-err'] };
  function painelBanco(s) {
    const [rotulo, classe] = STATUS[s.status] || ['—', ''];
    const ultimo = s.backups.ultimo;
    const pastas = Object.values(s.arquivos.pastas || {});
    const arquivos = pastas.reduce((a, p) => a + p.arquivos, 0);
    const arquivosBytes = pastas.reduce((a, p) => a + p.bytes, 0);
    return `
      <div class="pia-banco-h"><span class="pia-status ${classe}" data-role="saude-status">${rotulo}</span>
        <span class="hint">Verificado em ${escapeHtml(new Date(s.verificadoEm).toLocaleString('pt-BR'))}</span></div>
      ${s.avisos.length ? `<ul class="nr-reasons" role="alert">${s.avisos.map((a) => `<li>${escapeHtml(a)}</li>`).join('')}</ul>` : ''}
      <div class="pia-cards">
        ${card('Verificação', s.verificacao.ok ? 'Íntegro' : 'Com problemas', s.verificacao.tipo === 'integrity_check' ? 'verificação completa' : 'verificação rápida')}
        ${card('Tamanho do banco', bytes(s.tamanho.bytes), `${bytes(s.tamanho.livresBytes)} livres · diário ${escapeHtml(s.tamanho.journal)}`)}
        ${card('Último backup', ultimo ? `há ${Number(s.backups.idadeHoras).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} h` : 'Nenhum', `${s.backups.quantidade} cópia(s) verificada(s) · 7 diárias + 4 semanais`, 'backup')}
        ${card('PDFs e XMLs', `${arquivos} arquivo(s)`, `${bytes(arquivosBytes)} · ${s.arquivos.orfaos} sem registro · ${s.arquivos.ausentes} faltando`)}
        ${card('Notas recebidas', String(s.tabelas.notas_recebidas ?? '—'), `Lançadas ${s.tabelas.notas_lancadas ?? '—'} · pagas ${s.tabelas.notas_pagas ?? '—'} · locais ${s.tabelas.locais ?? '—'}`)}
      </div>
      <div class="task-add-row" style="margin-top:10px">
        <button class="ghost small" type="button" data-action="backup">Fazer backup agora</button>
        <button class="ghost small" type="button" data-action="manutencao">Rodar manutenção</button>
        <button class="ghost small" type="button" data-action="completo">Verificação completa</button>
        <span class="hint">O n8n faz backup e manutenção todo dia às 03:00. As cópias ficam em backend/data/${escapeHtml(s.backups.pasta)}; guarde uma cópia fora deste computador.</span>
      </div>`;
  }

  async function render(completo = false) {
    const box = byId('view_ia');
    if (!box) return;
    if (!box.dataset.pronto) {
      box.innerHTML = `<div class="vg-brand"><h2>Painel da IA</h2></div>
        <p class="sub">Quanto a LLM local acerta e aprende com as suas decisões, quanto custa rodar e se o banco está saudável.</p>
        <div class="nfse-card"><div class="nfse-header"><div><span class="section-label">LLM</span><h3>Acertos e aprendizado</h3></div>
          <label class="hint">Período <select class="f" id="piaMeses"><option value="3">3 meses</option><option value="6" selected>6 meses</option><option value="12">12 meses</option></select></label></div>
          <div id="piaIA"><div class="dash-empty">Carregando…</div></div></div>
        <div class="nfse-card" style="margin-top:16px"><div class="nfse-header"><div><span class="section-label">Banco de dados</span><h3>Saúde do banco</h3></div></div>
          <div id="piaBanco"><div class="dash-empty">Carregando…</div></div><div id="piaBancoStatus" class="hint" role="status" aria-live="polite"></div></div>`;
      box.dataset.pronto = '1';
      byId('piaMeses').addEventListener('change', () => render());
      byId('piaBanco').addEventListener('click', acaoBanco);
    }
    const meses = byId('piaMeses').value;
    const [ia, banco] = await Promise.allSettled([
      get(`/api/llm/metricas?meses=${encodeURIComponent(meses)}`),
      get(`/api/saude/banco${completo ? '?completo=1' : ''}`),
    ]);
    byId('piaIA').innerHTML = ia.status === 'fulfilled' ? painelIA(ia.value)
      : `<div class="backup-warn" role="alert">Não foi possível carregar as métricas: ${escapeHtml(ia.reason.message)}</div>`;
    byId('piaBanco').innerHTML = banco.status === 'fulfilled' ? painelBanco(banco.value)
      : `<div class="backup-warn" role="alert">Não foi possível verificar o banco: ${escapeHtml(banco.reason.message)}</div>`;
  }

  async function acaoBanco(event) {
    const botao = event.target.closest('[data-action]');
    if (!botao) return;
    const status = byId('piaBancoStatus');
    botao.disabled = true;
    try {
      if (botao.dataset.action === 'backup') {
        const r = await get('/api/saude/banco/backup', { method: 'POST' });
        status.textContent = `Backup ${r.arquivo} criado e verificado (${bytes(r.bytes)}).`;
      } else if (botao.dataset.action === 'manutencao') {
        const r = await get('/api/saude/banco/manutencao', { method: 'POST' });
        status.textContent = `Manutenção concluída${r.vacuum ? ' (com compactação)' : ''}.`;
      }
      await render(botao.dataset.action === 'completo');
    } catch (error) {
      status.textContent = error.message;
    } finally {
      botao.disabled = false;
    }
  }

  window.SIGP_PAINEL_IA = { render };
})();
