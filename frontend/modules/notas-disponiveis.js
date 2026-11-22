// Notas disponíveis do local: documentos que chegaram por e-mail (fatura, boleto, NFS-e/NFCom em XML ou PDF) e foram
// associados em Notas recebidas. Não são notas lançadas: nota lançada (e nota paga) vem do financeiro; quando o
// financeiro lança, as duas se ligam e a cobrança entra na conciliação (SIG/SIE só com todas as evidências).
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const base = () => window.SIGP_CONFIG.apiUrl();
  const data = (iso) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || '')); return m ? `${m[3]}/${m[2]}/${m[1]}` : '—'; };
  const brl = (v) => (Number(v) > 0 ? Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : 'valor não informado');
  const padrao = (v) => !v || String(v).trim() === '999999999';
  const TIPOS = { ag: 'agencia', rv: 'rodoviaria', gr: 'garagem' };

  function cartao(n) {
    const docs = (n.documentos || []).map((d) => `<li>${d.principal ? '<b>Fatura principal</b>' : 'Documento da mesma cobrança'}:
        <a href="${esc(base() + d.url)}" target="_blank" rel="noopener">${esc(d.nome || 'PDF')}</a>
        ${d.xmlUrl ? ` · <a href="${esc(base() + d.xmlUrl)}" target="_blank" rel="noopener">XML ${esc(d.xmlNome || '')}</a>` : ''}</li>`).join('');
    const situacao = n.nota_lancada_id
      ? `<span class="r-tag" title="Nota lançada pelo financeiro">LANÇADA PELO FINANCEIRO</span>`
      : '<span class="r-tag" title="Ainda sem nota lançada do financeiro">AGUARDANDO O FINANCEIRO</span>';
    return `<div class="nd-card">
      <div class="nd-topo"><b>${esc(n.provedor_nome || 'Provedor')}</b>${padrao(n.numero) ? '' : ` · nº ${esc(n.numero)}`} · venc. ${esc(data(n.data_vencimento))} · ${esc(brl(n.valor_total))} ${situacao}</div>
      <ul class="nd-docs">${docs || '<li class="hint">Sem arquivo.</li>'}</ul>
    </div>`;
  }

  async function render(id, prefixoOuTipo, localId) {
    const box = document.getElementById(id);
    if (!box) return;
    if (!localId) { box.innerHTML = '<div class="hint">Salve o local primeiro. As notas disponíveis chegam pela aba Notas recebidas.</div>'; return; }
    box.innerHTML = '<div class="hint">Carregando as notas disponíveis…</div>';
    const tipo = TIPOS[prefixoOuTipo] || prefixoOuTipo;
    try {
      const r = await fetch(`${base()}/api/notas-disponiveis?entidadeTipo=${encodeURIComponent(tipo)}&entidadeId=${encodeURIComponent(localId)}`);
      const j = await r.json().catch(() => ({}));
      if (r.status === 403) { box.innerHTML = '<div class="hint">Seu perfil não vê as notas disponíveis (permissão "Ver faturas").</div>'; return; }
      if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
      const itens = j.items || [];
      box.innerHTML = itens.length ? itens.map(cartao).join('')
        : '<div class="hint">Nenhuma nota disponível. Os documentos que chegam por e-mail aparecem aqui depois de associados em Notas recebidas.</div>';
    } catch (e) {
      box.innerHTML = `<div class="hint">Não foi possível carregar as notas disponíveis: ${esc(e.message)}</div>`;
    }
  }

  window.SIGP_NOTAS_DISPONIVEIS = { render };
})();
