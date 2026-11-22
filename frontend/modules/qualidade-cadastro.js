// Configurações > Qualidade do cadastro: o que falta ou está inconsistente e as correções com prévia.
// 1) Unificar nomes de provedor  2) Dia de vencimento (com sugestão das faturas)  3) Unidade inválida.
// A API faz backup do banco antes de cada correção e o nome novo é calculado no servidor (backend/correcoes_cadastro.py).
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const base = () => window.SIGP_CONFIG.apiUrl();
  const api = async (caminho, corpo) => {
    const r = await fetch(`${base()}${caminho}`, {
      method: corpo === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json' },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || `A API respondeu HTTP ${r.status}.`);
    return j;
  };
  let box = null;
  let dados = { previa: null, qualidade: null };
  let filtroDias = 'todos';

  const pode = () => !window.SIGP_ACESSO || window.SIGP_ACESSO.perfil === 'administrador'
    || (window.SIGP_ACESSO.permissoes || []).includes('locais.editar');

  // Traz para este navegador o que a API corrigiu (sem gravar de volta), para a próxima edição não desfazer.
  async function atualizarNavegador(itens, desativadas = []) {
    const porLocal = new Map();
    itens.forEach((i) => porLocal.set(i.localId, i));
    const locais = (await api('/api/locais?inativos=1')).items || [];
    for (const l of locais) {
      if (porLocal.has(l.id)) await window.SIGP_API.refreshLocationProviders(l.tipo, l.id, { trocarNome: true });
    }
    for (const d of desativadas) {
      for (const k of ['ti_agencias_v1', 'ti_rodoviarias_v1', 'ti_garagens_v1']) {
        try {
          const lista = JSON.parse(localStorage.getItem(k) || '[]');
          if (Array.isArray(lista) && lista.some((x) => String(x.id) === String(d.localId))) {
            localStorage.setItem(k, JSON.stringify(lista.filter((x) => String(x.id) !== String(d.localId))));
          }
        } catch (e) { /* lista inválida: a API já desativou */ }
      }
    }
  }

  // Seções recolhíveis: lembram se estavam abertas entre um desenho e outro.
  const abertas = {};
  const aberta = (k, padrao) => ((abertas[k] ?? padrao) ? ' open' : '');

  function resumo() {
    const q = dados.qualidade;
    if (!q) return '';
    if (!q.total) return '<section class="cfg-cartao"><div class="cfg-cartao-b hint">✅ Nada a corrigir no cadastro.</div></section>';
    const itens = Object.entries(q.resumo).sort((a, b) => b[1] - a[1])
      .map(([nome, n]) => `<span class="qc-chip${/vencimento|inv[aá]lid/i.test(nome) ? ' qc-chip-warn' : ''}"><b>${n}</b>${esc(nome.toLowerCase())}</span>`).join('');
    return `<section class="cfg-cartao"><div class="cfg-cartao-b">
      <div class="qc-chips" aria-label="Resumo da qualidade">${itens}</div>
      <p class="cfg-intro" style="margin:12px 0 0">Total: ${q.total} ponto(s). Os destacados se corrigem aqui embaixo; os demais (endereço, responsável) no cadastro de cada local.</p></div></section>`;
  }

  function blocoUnificar() {
    const grupos = dados.previa.unificar;
    if (!grupos.length) return '<p class="hint">✅ Nenhum provedor com nomes diferentes.</p>';
    return `<p class="cfg-intro">O mesmo provedor escrito de jeitos diferentes conta como provedores distintos nas respostas e nos relatórios. O plano (ex.: 200MB+IP) é mantido no nome.</p>
      ${grupos.map((g, gi) => `<fieldset class="qc-grupo"><legend><label><input type="checkbox" data-qc-grupo="${gi}" checked> <b>${esc(g.provedor)}</b></label>
        <span class="hint">variantes: ${g.variantes.map((v) => esc(v.nome)).join(' · ')}</span></legend>
        <ul>${g.itens.map((i) => `<li>${esc(i.unidade)}: <code>${esc(i.de)}</code> → <code>${esc(i.para)}</code></li>`).join('')}</ul></fieldset>`).join('')}
      <div class="perm-editor-acoes"><span class="hint cfg-f-esq" data-qc-status="unificar" role="status"></span>
        <button type="button" class="primary small" data-qc-acao="unificar">Unificar selecionados</button></div>`;
  }

  function blocoDias() {
    const lista = dados.previa.vencimento;
    if (!lista.length) return '<p class="hint">✅ Todos os provedores têm dia de vencimento.</p>';
    const visiveis = filtroDias === 'sugestao' ? lista.filter((v) => v.sugestao) : lista;
    return `<p class="cfg-intro">O dia alimenta os alertas e o assistente. A sugestão vem das faturas já recebidas; confira antes de salvar. Deixe em branco o que não souber.</p>
      <div class="qc-barra"><select class="f" data-qc-filtro aria-label="Mostrar">
        <option value="todos"${filtroDias === 'todos' ? ' selected' : ''}>Todos (${lista.length})</option>
        <option value="sugestao"${filtroDias === 'sugestao' ? ' selected' : ''}>Só com sugestão (${lista.filter((v) => v.sugestao).length})</option></select>
        ${lista.some((v) => v.sugestao) ? '<button type="button" class="ghost small" data-qc-acao="usar-sugestoes">Usar todas as sugestões</button>' : ''}</div>
      <div class="cfg-tw cfg-tw-caixa qc-dias"><table class="cfg-tabela"><thead><tr><th>Unidade</th><th>Provedor</th><th style="width:90px">Dia</th><th>Sugestão</th></tr></thead><tbody>
      ${visiveis.map((v) => `<tr><td>${esc(v.unidade)}</td><td>${esc(v.provedor)}</td>
        <td><label class="sr-only" for="qcDia${esc(v.localId)}${esc(v.provedorId)}">Dia de vencimento de ${esc(v.provedor)} em ${esc(v.unidade)}</label>
          <input class="f qc-dia" type="number" min="1" max="31" inputmode="numeric" id="qcDia${esc(v.localId)}${esc(v.provedorId)}"
            data-local="${esc(v.localId)}" data-provedor="${esc(v.provedorId)}" data-indice="${v.indice}" data-sugestao="${v.sugestao || ''}"></td>
        <td>${v.sugestao ? `<span class="cfg-pill cfg-pill-ok">dia ${v.sugestao}</span> <span class="hint">${esc(v.fonte)}</span>` : '<span class="hint">sem faturas para sugerir</span>'}</td></tr>`).join('')}
      </tbody></table></div>
      <div class="perm-editor-acoes"><span class="hint cfg-f-esq" data-qc-status="dias" role="status"></span>
        <button type="button" class="primary small" data-qc-acao="dias">Salvar dias preenchidos</button></div>`;
  }

  function blocoInvalidas() {
    const lista = dados.previa.unidadesInvalidas;
    if (!lista.length) return '<p class="hint">✅ Nenhuma unidade inválida.</p>';
    return `<p class="cfg-intro">Nome que parece cabeçalho de planilha importado por engano. Desativar tira da lista e das contagens; o histórico fica guardado.</p>
      <div class="cfg-list">${lista.map((u) => `<div class="cfg-row"><div class="cfg-grow">${esc(u.unidade)}<small>${u.provedores} provedor(es)</small></div>
        <button type="button" class="ghost small" data-qc-acao="desativar" data-local="${esc(u.localId)}">Desativar</button></div>`).join('')}</div>
      <span class="hint" data-qc-status="desativar" role="status"></span>`;
  }

  function desenhar() {
    if (!pode()) { box.innerHTML = '<section class="cfg-cartao"><div class="cfg-cartao-b hint">Seu perfil não pode corrigir o cadastro (permissão "Criar e editar locais").</div></section>'; return; }
    const p = dados.previa;
    const secao = (k, padrao, titulo, sub, corpo) => `<details class="cfg-acc" data-qc-sec="${k}"${aberta(k, padrao)}>
      <summary><b>${titulo}</b><span class="cfg-acc-sub">${sub}</span></summary><div class="cfg-acc-body">${corpo}</div></details>`;
    box.innerHTML = `${resumo()}
      ${secao('dias', true, 'Dia de vencimento', `${p.resumo.vencimento} sem dia · ${p.resumo.vencimentoComSugestao} com sugestão`, blocoDias())}
      ${secao('unificar', p.unificar.length > 0, 'Unificar nomes de provedor', `${p.resumo.unificar} cadastro(s)`, blocoUnificar())}
      ${secao('invalidas', p.unidadesInvalidas.length > 0, 'Unidades inválidas', `${p.resumo.unidadesInvalidas}`, blocoInvalidas())}`;
    const total = dados.qualidade?.total;
    window.SIGP_CONFIG_LAYOUT?.marcar('qualidade', total || '', total ? 'warn' : '');
  }

  async function carregar() {
    const [previa, qualidade] = await Promise.all([api('/api/cadastro/correcoes'), api('/api/base-conhecimento/qualidade')]);
    dados = { previa, qualidade };
  }

  async function render(alvo) {
    box = typeof alvo === 'string' ? document.getElementById(alvo) : alvo;
    if (!box) return;
    if (!pode()) { desenhar(); return; }
    try { await carregar(); desenhar(); } catch (e) { box.innerHTML = `<div class="hint">Não foi possível ler a qualidade do cadastro: ${esc(e.message)}</div>`; return; }
    if (box.dataset.ligado) return;
    box.dataset.ligado = '1';
    box.addEventListener('change', (ev) => {
      if (ev.target.matches('[data-qc-filtro]')) {
        const abertos = [...box.querySelectorAll('details')].map((d) => d.open);
        filtroDias = ev.target.value; desenhar();
        box.querySelectorAll('details').forEach((d, i) => { d.open = abertos[i]; });
      }
    });
    box.addEventListener('click', async (ev) => {
      const b = ev.target.closest('[data-qc-acao]');
      if (!b) return;
      const acao = b.dataset.qcAcao;
      const status = box.querySelector(`[data-qc-status="${acao === 'usar-sugestoes' ? 'dias' : acao}"]`);
      if (acao === 'usar-sugestoes') {
        box.querySelectorAll('.qc-dia').forEach((i) => { if (i.dataset.sugestao && !i.value) i.value = i.dataset.sugestao; });
        if (status) status.textContent = 'Sugestões preenchidas. Confira e clique em "Salvar dias preenchidos".';
        return;
      }
      try {
        b.disabled = true;
        let r = null;
        if (acao === 'unificar') {
          const itens = [...box.querySelectorAll('[data-qc-grupo]:checked')].flatMap((c) => dados.previa.unificar[Number(c.dataset.qcGrupo)].itens);
          if (!itens.length) { status.textContent = 'Selecione pelo menos um provedor.'; return; }
          if (!window.confirm(`Unificar ${itens.length} cadastro(s) de provedor? O sistema faz backup do banco antes.`)) return;
          r = await api('/api/cadastro/correcoes/unificar', { itens });
          await atualizarNavegador(r.itens);
        } else if (acao === 'dias') {
          const itens = [...box.querySelectorAll('.qc-dia')].filter((i) => i.value).map((i) => ({
            localId: i.dataset.local, provedorId: i.dataset.provedor, indice: Number(i.dataset.indice), dia: Number(i.value) }));
          const ruim = itens.find((i) => !(i.dia >= 1 && i.dia <= 31));
          if (ruim) { status.textContent = 'Use um dia de 1 a 31.'; return; }
          if (!itens.length) { status.textContent = 'Preencha pelo menos um dia.'; return; }
          if (!window.confirm(`Salvar o dia de vencimento de ${itens.length} provedor(es)? O sistema faz backup do banco antes.`)) return;
          r = await api('/api/cadastro/correcoes/vencimento', { itens });
          await atualizarNavegador(r.itens);
        } else if (acao === 'desativar') {
          if (!window.confirm('Desativar esta unidade? Ela sai das listas e das contagens; o histórico fica guardado.')) return;
          r = await api('/api/cadastro/correcoes/desativar', { localId: b.dataset.local });
          await atualizarNavegador([], r.itens);
        }
        await carregar();
        desenhar();
        const texto = `Pronto: ${r.aplicados} alteração(ões). Backup antes: ${r.backup}. Recarregue a página (F5) para ver nas outras abas.`;
        const msg = box.querySelector(`[data-qc-status="${acao}"]`);
        if (msg) msg.textContent = texto;
        window.toast?.(texto, 6000);
      } catch (e) {
        if (status) status.textContent = e.message;
      } finally {
        b.disabled = false;
      }
    });
  }

  window.SIGP_QUALIDADE_CADASTRO = { render };
})();
