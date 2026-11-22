// Situação da conta de cada local (selo fixo nas listas e filtro "Situação da conta").
// Não é marcador e não fica gravada no local: vem dos alertas da API (GET /api/alertas, a mesma regra do SIG,
// do e-mail diário e do assistente) e some sozinha quando o pagamento é confirmado. Precisa da permissão do SIG
// (sig.ver); sem ela, as listas ficam sem selo e o filtro some.
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  // Ordem = gravidade (o selo mostra a pior situação do local).
  const SITUACOES = [
    { status: 'VENCIDO', id: 'vencida', rotulo: 'Vencida', cor: 'var(--danger)' },
    { status: 'VENCE_HOJE', id: 'vence_hoje', rotulo: 'Vence hoje', cor: 'var(--danger)' },
    { status: 'VENCE_EM_BREVE', id: 'vence_em_breve', rotulo: 'A vencer', cor: 'var(--warn)' },
    { status: 'FATURA_NAO_RECEBIDA', id: 'nao_recebida', rotulo: 'Fatura não chegou', cor: 'var(--warn)' },
  ];
  const POR_STATUS = Object.fromEntries(SITUACOES.map((s, i) => [s.status, { ...s, ordem: i }]));
  let porLocal = new Map(); // id do local -> { pior, itens: [alerta] }
  let disponivel = false;
  let carregando = null;

  function carregar() {
    if (carregando) return carregando;
    const dias = Number(window.CONFIG?.alertaFaturaDias) || 7;
    carregando = fetch(`${window.SIGP_CONFIG.apiUrl()}/api/alertas?dias=${dias}`)
      .then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !Array.isArray(j.items)) throw new Error(`HTTP ${r.status}`);
        const mapa = new Map();
        j.items.forEach((a) => {
          const s = POR_STATUS[a.status];
          if (!s || !a.entidadeId) return;
          const atual = mapa.get(String(a.entidadeId)) || { pior: s, itens: [] };
          if (s.ordem < atual.pior.ordem) atual.pior = s;
          atual.itens.push(a);
          mapa.set(String(a.entidadeId), atual);
        });
        porLocal = mapa;
        disponivel = true;
      })
      .catch(() => { disponivel = false; porLocal = new Map(); })
      .finally(() => {
        carregando = null;
        document.querySelectorAll('select.sc-filtro').forEach((s) => {
          if (!s.options.length) s.innerHTML = opcoes();
          s.hidden = !disponivel;
          if (!disponivel) s.value = '';
        });
        window.dispatchEvent(new CustomEvent('sigp:situacao-atualizada'));
      });
    return carregando;
  }

  function selo(local) {
    const info = local && porLocal.get(String(local.id));
    if (!info) return '';
    const s = info.pior;
    const extra = s.id === 'vence_em_breve' ? (() => {
      const dias = Math.min(...info.itens.filter((a) => a.status === 'VENCE_EM_BREVE').map((a) => Number(a.dias) || 0));
      return Number.isFinite(dias) ? ` em ${dias}d` : '';
    })() : '';
    const titulo = info.itens.map((a) => a.mensagem || `${a.provedor || 'provedor'}: ${a.status}`).join('\n');
    return `<span class="sc-selo" style="border-color:${s.cor}; color:${s.cor}" title="${esc(`Situação da conta (automática)\n${titulo}`)}">● ${esc(s.rotulo + extra)}${info.itens.length > 1 ? ` · ${info.itens.length}` : ''}</span>`;
  }

  // Valores do filtro: '' (todas), 'pendente' (qualquer situação), 'em_dia' (nenhuma) ou o id da situação.
  function passaNoFiltro(local, valor) {
    if (!valor || !disponivel) return true;
    const info = porLocal.get(String(local.id));
    if (valor === 'pendente') return !!info;
    if (valor === 'em_dia') return !info;
    return !!info && info.itens.some((a) => (POR_STATUS[a.status] || {}).id === valor);
  }

  const opcoes = () => `<option value="">Situação da conta: todas</option><option value="pendente">Com pendência</option>`
    + SITUACOES.map((s) => `<option value="${s.id}">${esc(s.rotulo)}</option>`).join('')
    + '<option value="em_dia">Sem pendência</option>';

  // Pagamento marcado ou cadastro salvo muda a situação: recarrega (com folga para a API gravar).
  let timer = null;
  window.addEventListener('sigp:locais-gravados', () => { clearTimeout(timer); timer = setTimeout(carregar, 900); });
  setInterval(() => { if (document.visibilityState === 'visible' && disponivel) carregar(); }, 5 * 60 * 1000);

  window.SIGP_SITUACAO_CONTA = { carregar, selo, passaNoFiltro, opcoes, disponivel: () => disponivel };
})();
