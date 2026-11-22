// Aba "Assistente", no estilo dos chats de IA: conversas à esquerda (histórico), a conversa no centro e os
// artefatos (tabelas e relatórios) à direita. A API (backend/assistente.py) entende a pergunta, consulta só o que
// o perfil permite e responde com os números do sistema. 👍/👎 viram material de treino (aba "Treinar").
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const base = () => window.SIGP_CONFIG.apiUrl();
  const api = async (caminho, metodo = 'GET', corpo) => {
    const r = await fetch(`${base()}${caminho}`, {
      method: metodo, headers: { 'Content-Type': 'application/json' }, body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || `A API respondeu HTTP ${r.status}.`);
    return j;
  };
  const SUGESTOES = [
    ['Quantas agências estão em atraso?', 'contas vencidas'], ['Quais contas vencem nos próximos dias?', 'a vencer'],
    ['Qual o endereço da agência de Itacaré?', 'endereço'], ['Qual o valor da conta de Itacaré?', 'valor'],
    ['Crie um relatório com a lista de agências', 'relatório PDF e Excel'], ['Gere um relatório das contas vencidas', 'relatório'],
  ];
  const estado = { conversas: [], atual: null, mensagens: [], artefato: null, painel: true, pensando: false, filtro: '', lateral: true };
  // Larguras das colunas (arrastar as divisórias); guardadas neste navegador.
  const LARGURAS = 'sigp_assistente_larguras_v1';
  const PADRAO = { esq: 260, dir: 460 };
  const LIMITES = { esq: [180, 460], dir: [280, 1100] };
  const lerLarguras = () => { try { return { ...PADRAO, ...(JSON.parse(localStorage.getItem(LARGURAS)) || {}) }; } catch (e) { return { ...PADRAO }; } };
  let larguras = lerLarguras();
  let box = null;

  const quando = (iso) => {
    if (!iso) return '';
    const d = new Date(iso), hoje = new Date();
    const dias = Math.floor((new Date(hoje.toDateString()) - new Date(d.toDateString())) / 86400000);
    return dias === 0 ? 'Hoje' : dias === 1 ? 'Ontem' : dias < 7 ? 'Últimos 7 dias' : dias < 30 ? 'Últimos 30 dias' : 'Mais antigas';
  };
  const podeEnsinar = () => !window.SIGP_ACESSO || window.SIGP_ACESSO.perfil === 'administrador'
    || (window.SIGP_ACESSO.permissoes || []).includes('assistente.ensinar');
  const formatarTexto = (t) => esc(t).replace(/\n- /g, '\n• ').replace(/\n/g, '<br>');
  const artefatos = () => estado.mensagens.filter((m) => m.artefato).map((m) => ({ ...m.artefato, msgId: m.id }));

  // ---------------------------------------------------------------- partes
  function lateral() {
    const lista = estado.conversas.filter((c) => !estado.filtro || c.titulo.toLowerCase().includes(estado.filtro.toLowerCase()));
    let grupo = '';
    const itens = lista.map((c) => {
      const g = quando(c.atualizadaEm);
      const cab = g !== grupo ? `<li class="chat-grupo">${esc((grupo = g))}</li>` : '';
      return `${cab}<li><div class="chat-conv${c.id === estado.atual ? ' ativa' : ''}">
        <button type="button" class="chat-conv-abrir" data-abrir="${esc(c.id)}" title="${esc(c.titulo)}">${esc(c.titulo)}${c.artefatos ? ' <span class="chat-tag" aria-label="tem artefatos">📎</span>' : ''}</button>
        <button type="button" class="chat-conv-menu" data-renomear="${esc(c.id)}" aria-label="Renomear ${esc(c.titulo)}">✎</button>
        <button type="button" class="chat-conv-menu" data-apagar="${esc(c.id)}" aria-label="Apagar ${esc(c.titulo)}">🗑</button></div></li>`;
    }).join('');
    return `<div class="chat-lateral-topo"><button type="button" class="primary chat-nova" data-nova>＋ Nova conversa</button>
        <button type="button" class="ghost small chat-recolher" data-recolher aria-label="Recolher a lista de conversas" title="Recolher">⟨</button></div>
      <label class="sr-only" for="chatBusca">Buscar conversas</label>
      <input class="f chat-busca" id="chatBusca" placeholder="Buscar conversas" value="${esc(estado.filtro)}" autocomplete="off">
      <ul class="chat-lista" aria-label="Conversas">${itens || '<li class="hint" style="padding:8px">Nenhuma conversa ainda.</li>'}</ul>
      ${podeEnsinar() ? '<button type="button" class="ghost small chat-treinar" data-treinar>🎓 Treinar o assistente</button>' : ''}`;
  }

  function mensagem(m) {
    const voce = `<div class="chat-linha chat-voce"><div class="chat-balao">${esc(m.pergunta)}</div></div>`;
    if (m.pensando) return `${voce}<div class="chat-linha chat-ia"><div class="chat-avatar" aria-hidden="true">✦</div><div class="chat-corpo" aria-busy="true"><div class="chat-digitando"><span></span><span></span><span></span></div><div class="hint">A IA local roda no computador; pode levar alguns segundos.</div></div></div>`;
    const art = m.artefato ? `<button type="button" class="chat-cartao" data-artefato="${esc(m.id)}">
        <span class="chat-cartao-icone" aria-hidden="true">${m.artefato.tipo === 'relatorio' ? '📄' : '▦'}</span>
        <span><b>${esc(m.artefato.titulo)}</b><br><span class="hint">${m.artefato.total} linha(s)${m.artefato.arquivos?.length ? ' · PDF e Excel' : ''} · abrir</span></span></button>` : '';
    const origem = { regra: 'entendido por regra', 'ia local': 'entendido pela IA local', 'continuação': 'continuação da conversa' }[m.origem] || m.origem || '';
    const tempo = m.duracaoMs ? ` · ${(m.duracaoMs / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} s` : '';
    const aval = m.ferramenta ? (m.util === true ? '<span class="hint">👍 aprovado</span>' : m.util === false ? '<span class="hint">👎 enviado para revisão</span>'
      : `<button type="button" class="chat-acao" data-util="1" data-id="${esc(m.id)}" aria-label="Resposta certa" title="Resposta certa (ensina o assistente)">👍</button>
         <button type="button" class="chat-acao" data-util="0" data-id="${esc(m.id)}" aria-label="Resposta errada" title="Resposta errada">👎</button>`) : '';
    return `${voce}<div class="chat-linha chat-ia"><div class="chat-avatar" aria-hidden="true">✦</div><div class="chat-corpo">
      <div class="chat-texto">${formatarTexto(m.resposta)}</div>${art}
      <div class="chat-rodape"><button type="button" class="chat-acao" data-copiar="${esc(m.id)}" aria-label="Copiar resposta" title="Copiar">⧉</button>${aval}
        <span class="hint">${m.ferramenta && m.util !== null && m.util !== undefined ? '· ' : ''}${esc(origem)}${tempo}</span></div></div></div>`;
  }

  function centro() {
    const vazio = !estado.mensagens.length;
    return `<div class="chat-topo">
        <button type="button" class="ghost small${estado.lateral ? ' chat-so-mobile' : ''}" data-lateral aria-label="Mostrar a lista de conversas" title="Conversas">☰</button>
        <span class="chat-titulo">${esc(estado.conversas.find((c) => c.id === estado.atual)?.titulo || 'Nova conversa')}</span>
        <button type="button" class="ghost small" data-painel aria-pressed="${estado.painel}">${estado.painel ? 'Ocultar' : 'Mostrar'} artefatos${artefatos().length ? ` (${artefatos().length})` : ''}</button>
      </div>
      <div class="chat-rolagem" id="chatRolagem" role="log" aria-live="polite">
        ${vazio ? `<div class="chat-boas-vindas"><div class="chat-logo" aria-hidden="true">✦</div><h3>Como posso ajudar?</h3>
            <p class="hint">Pergunte do seu jeito sobre locais, provedores, contas, vencimentos, endereços e contatos. Os números vêm sempre do sistema.</p>
            <div class="chat-sugestoes">${SUGESTOES.map(([s, d]) => `<button type="button" class="chat-sugestao" data-sugestao="${esc(s)}"><b>${esc(s)}</b><span class="hint">${esc(d)}</span></button>`).join('')}</div></div>`
          : `<div class="chat-fio">${estado.mensagens.map(mensagem).join('')}</div>`}
      </div>
      <form class="chat-entrada" id="chatForm">
        <label for="chatPergunta" class="sr-only">Pergunta</label>
        <textarea id="chatPergunta" rows="1" maxlength="500" placeholder="Pergunte ao assistente… (Enter envia, Shift+Enter quebra a linha)"${estado.pensando ? ' disabled' : ''}></textarea>
        <button type="submit" class="primary chat-enviar" aria-label="Enviar"${estado.pensando ? ' disabled' : ''}>↑</button>
      </form>
      <div class="hint chat-aviso">IA local: nada sai da rede. Confira valores importantes no cadastro.</div>`;
  }

  function painel() {
    const lista = artefatos();
    const atual = lista.find((a) => a.msgId === estado.artefato) || lista[lista.length - 1];
    if (!atual) return '<div class="chat-painel-vazio hint">Tabelas e relatórios gerados nesta conversa aparecem aqui, separados da conversa.</div>';
    const abas = lista.length > 1 ? `<div class="chat-art-abas" role="tablist">${lista.map((a) => `<button type="button" role="tab" aria-selected="${a === atual}" data-artefato="${esc(a.msgId)}">${a.tipo === 'relatorio' ? '📄' : '▦'} ${esc(a.titulo)}</button>`).join('')}</div>` : '';
    const arquivos = (atual.arquivos || []).map((f) => `<a class="ghost small" href="${esc(base() + f.url)}" ${f.formato === 'csv' ? `download="${esc(f.nome)}"` : 'target="_blank" rel="noopener"'}>⬇ ${f.formato === 'pdf' ? 'PDF' : 'Excel (CSV)'}</a>`).join(' ');
    const cab = atual.colunas.map((c) => `<th scope="col">${esc(c.nome)}</th>`).join('');
    const linhas = atual.linhas.map((l) => `<tr>${atual.colunas.map((c) => `<td>${esc(l[c.id])}</td>`).join('')}</tr>`).join('');
    return `${abas}<div class="chat-art-cab"><div><b>${esc(atual.titulo)}</b><div class="hint">${atual.total} linha(s)${atual.linhas.length < atual.total ? ` · mostrando ${atual.linhas.length}` : ''}</div></div>
        <div class="chat-art-acoes">${arquivos}<button type="button" class="ghost small" data-copiar-tabela="${esc(atual.msgId)}">Copiar tabela</button></div></div>
      <div class="chat-art-tabela"><table class="pia-table"><thead><tr>${cab}</tr></thead><tbody>${linhas}</tbody></table></div>`;
  }

  async function treinoHtml() {
    const t = await api('/api/assistente/treinamento');
    const lista = (itens, campo) => itens.length ? `<ul class="chat-treino-lista">${itens.map((i) => `<li><b>${esc(i.pergunta)}</b>${i[campo] ? `<div class="hint">${esc(i[campo])}</div>` : ''}<div class="hint">${esc(i.usuario)} · ${esc(new Date(i.criado_em).toLocaleString('pt-BR'))}</div></li>`).join('')}</ul>` : '<div class="hint">Nada aqui.</div>';
    return `<div class="chat-treino">
      <div class="chat-art-cab"><b>Treinar o assistente</b><button type="button" class="ghost small" data-fechar-treino>Fechar</button></div>
      <p class="hint">O histórico é o material de treino. Respostas com 👍 viram exemplos (o assistente reconhece perguntas parecidas na hora); 👎 e as não entendidas mostram o que falta ensinar.</p>
      <div class="chat-numeros">
        <div><b>${t.perguntas}</b><span>perguntas</span></div><div><b>${t.aprovadas}</b><span>👍 aprovadas</span></div>
        <div><b>${t.reprovadas}</b><span>👎 reprovadas</span></div><div><b>${t.exemplosAprendidos}</b><span>exemplos aprendidos</span></div>
        <div><b>${t.termosAprendidos}</b><span>termos ensinados</span></div></div>
      <div class="hint">Por origem: ${Object.entries(t.porOrigem).map(([k, v]) => `${esc(k || 'não entendida')} ${v}`).join(' · ') || '—'}</div>
      <details class="nr-disc" open><summary>Ensinar um termo</summary><div class="nr-disc-body">
        <div class="hint">Ex.: "matriz" = "Agência ITABUNA CENTRO"; "em débito" = "vencida"; "terminal" = "rodoviaria".</div>
        <form id="chatTermoForm" class="nfse-grid" style="margin-top:6px">
          <label>Quando alguém disser<input class="f" id="chatTermo" maxlength="60" required></label>
          <label>Quer dizer<input class="f" id="chatSignifica" maxlength="80" required></label>
          <div class="task-add-row"><button class="ghost small" type="submit">Ensinar</button><span class="hint" id="chatTermoStatus" role="status"></span></div>
        </form></div></details>
      <details class="nr-disc"><summary>Perguntas não entendidas (${t.naoEntendidas.length})</summary><div class="nr-disc-body">${lista(t.naoEntendidas)}</div></details>
      <details class="nr-disc"><summary>Respostas reprovadas (${t.listaReprovadas.length})</summary><div class="nr-disc-body">${lista(t.listaReprovadas, 'comentario')}</div></details>
      <div class="task-add-row" style="margin-top:10px"><a class="ghost small" href="${esc(base())}/api/assistente/dataset.jsonl" download="sigp-assistente-dataset.jsonl">⬇ Exportar dataset (JSONL)</a>
        <span class="hint">Formato de conversa (system, user, assistant): exemplos dos JSON + aprovados. Serve para um ajuste fino futuro.</span></div>
    </div>`;
  }

  // ---------------------------------------------------------------- desenho
  function desenhar(foco = true) {
    if (!box) return;
    const rolagem = box.querySelector('#chatRolagem');
    const noFim = !rolagem || rolagem.scrollHeight - rolagem.scrollTop - rolagem.clientHeight < 80;
    box.querySelector('.chat-lateral').innerHTML = lateral();
    box.querySelector('.chat-centro').innerHTML = centro();
    const p = box.querySelector('.chat-painel');
    p.hidden = !estado.painel && !estado.treino;
    if (!estado.treino) p.innerHTML = painel();
    aplicarLarguras();
    const r = box.querySelector('#chatRolagem');
    if (r && noFim) r.scrollTop = r.scrollHeight;
    if (foco && !estado.pensando) box.querySelector('#chatPergunta')?.focus();
  }

  async function carregarConversas() {
    try { estado.conversas = (await api('/api/assistente/conversas')).items; } catch (e) { estado.conversas = []; }
  }

  async function abrir(id) {
    estado.atual = id;
    estado.artefato = null;
    box.querySelector('.chat-app').classList.remove('lateral-aberta');
    if (!id) { estado.mensagens = []; desenhar(); return; }
    try {
      const c = await api(`/api/assistente/conversas/${encodeURIComponent(id)}`);
      estado.mensagens = c.itens;
    } catch (e) { estado.mensagens = []; window.toast?.(e.message); }
    desenhar();
  }

  async function perguntar(texto) {
    const pergunta = String(texto || '').trim();
    if (!pergunta || estado.pensando) return;
    estado.pensando = true;
    estado.mensagens.push({ id: 'pensando', pergunta, pensando: true });
    desenhar(false);
    try {
      const r = await api('/api/assistente/perguntar', 'POST', { pergunta, conversaId: estado.atual || undefined });
      estado.mensagens[estado.mensagens.length - 1] = { id: r.id, pergunta, resposta: r.resposta, ferramenta: r.ferramenta, origem: r.origem,
        duracaoMs: r.duracaoMs, artefato: r.artefato, arquivos: r.arquivos, util: null };
      if (r.artefato) { estado.artefato = r.id; estado.painel = true; }
      if (estado.atual !== r.conversaId) { estado.atual = r.conversaId; }
      await carregarConversas();
    } catch (e) {
      estado.mensagens[estado.mensagens.length - 1] = { id: '', pergunta, resposta: `Não consegui responder: ${e.message}` };
    } finally {
      estado.pensando = false;
      desenhar();
    }
  }

  async function abrirTreino() {
    estado.treino = true;
    const p = box.querySelector('.chat-painel');
    p.hidden = false;
    aplicarLarguras();
    p.innerHTML = '<div class="hint" style="padding:12px">Carregando…</div>';
    try { p.innerHTML = await treinoHtml(); } catch (e) { p.innerHTML = `<div class="hint" style="padding:12px">${esc(e.message)}</div>`; }
  }

  function ligar() {
    box.addEventListener('click', async (ev) => {
      const t = ev.target.closest('button, a');
      if (!t) return;
      if (t.dataset.nova !== undefined) { abrir(null); return; }
      if (t.dataset.abrir) { abrir(t.dataset.abrir); return; }
      if (t.dataset.sugestao) { perguntar(t.dataset.sugestao); return; }
      if (t.dataset.lateral !== undefined) {
        if (window.matchMedia('(max-width: 760px)').matches) box.querySelector('.chat-app').classList.toggle('lateral-aberta');
        else { estado.lateral = true; desenhar(false); }
        return;
      }
      if (t.dataset.recolher !== undefined) {
        if (window.matchMedia('(max-width: 760px)').matches) box.querySelector('.chat-app').classList.remove('lateral-aberta');
        else { estado.lateral = false; desenhar(false); }
        return;
      }
      if (t.dataset.painel !== undefined) { estado.painel = !estado.painel; estado.treino = false; desenhar(false); return; }
      if (t.dataset.artefato) { estado.artefato = t.dataset.artefato; estado.painel = true; estado.treino = false; desenhar(false); return; }
      if (t.dataset.treinar !== undefined) { abrirTreino(); return; }
      if (t.dataset.fecharTreino !== undefined) { estado.treino = false; desenhar(false); return; }
      if (t.dataset.renomear) {
        const c = estado.conversas.find((x) => x.id === t.dataset.renomear);
        const titulo = window.prompt('Novo título da conversa:', c?.titulo || '');
        if (!titulo) return;
        try { await api(`/api/assistente/conversas/${encodeURIComponent(t.dataset.renomear)}`, 'PATCH', { titulo }); await carregarConversas(); desenhar(false); } catch (e) { window.toast?.(e.message); }
        return;
      }
      if (t.dataset.apagar) {
        if (!window.confirm('Apagar esta conversa? As respostas avaliadas continuam ensinando o assistente.')) return;
        try {
          await api(`/api/assistente/conversas/${encodeURIComponent(t.dataset.apagar)}`, 'DELETE');
          await carregarConversas();
          if (estado.atual === t.dataset.apagar) abrir(null); else desenhar(false);
        } catch (e) { window.toast?.(e.message); }
        return;
      }
      if (t.dataset.copiar) {
        const m = estado.mensagens.find((x) => x.id === t.dataset.copiar);
        try { await navigator.clipboard.writeText(m?.resposta || ''); window.toast?.('Resposta copiada.'); } catch (e) { /* sem permissão */ }
        return;
      }
      if (t.dataset.copiarTabela) {
        const a = artefatos().find((x) => x.msgId === t.dataset.copiarTabela);
        if (!a) return;
        const tsv = [a.colunas.map((c) => c.nome).join('\t'), ...a.linhas.map((l) => a.colunas.map((c) => l[c.id] ?? '').join('\t'))].join('\n');
        try { await navigator.clipboard.writeText(tsv); window.toast?.('Tabela copiada: cole no Excel.'); } catch (e) { /* sem permissão */ }
        return;
      }
      if (t.dataset.util) {
        const sim = t.dataset.util === '1';
        const comentario = sim ? '' : (window.prompt('O que você esperava? (ajuda a treinar o assistente)') || '');
        try {
          await api('/api/assistente/avaliar', 'POST', { id: t.dataset.id, util: sim, comentario });
          const m = estado.mensagens.find((x) => x.id === t.dataset.id);
          if (m) m.util = sim;
          desenhar(false);
        } catch (e) { window.toast?.(e.message); }
      }
    });
    box.addEventListener('submit', async (ev) => {
      if (ev.target.id === 'chatForm') { ev.preventDefault(); perguntar(box.querySelector('#chatPergunta').value); return; }
      if (ev.target.id === 'chatTermoForm') {
        ev.preventDefault();
        const status = box.querySelector('#chatTermoStatus');
        try {
          const r = await api('/api/assistente/termos', 'POST', { termo: box.querySelector('#chatTermo').value, significa: box.querySelector('#chatSignifica').value });
          await abrirTreino();
          box.querySelector('#chatTermoStatus').textContent = `Aprendido: "${r.item.termo}" = "${r.item.significa}".`;
        } catch (e) { status.textContent = e.message; }
      }
    });
    box.addEventListener('keydown', (ev) => {
      if (ev.target.id === 'chatPergunta' && ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); perguntar(ev.target.value); }
    });
    box.addEventListener('input', (ev) => {
      if (ev.target.id === 'chatPergunta') { ev.target.style.height = 'auto'; ev.target.style.height = `${Math.min(ev.target.scrollHeight, 160)}px`; }
      if (ev.target.id === 'chatBusca') {
        estado.filtro = ev.target.value;
        const pos = ev.target.selectionStart;
        box.querySelector('.chat-lateral').innerHTML = lateral();
        const campo = box.querySelector('#chatBusca');
        campo.focus();
        campo.setSelectionRange(pos, pos);
      }
    });
  }

  // ---------------------------------------------------------------- divisórias arrastáveis
  function aplicarLarguras() {
    const app = box?.querySelector('.chat-app');
    if (!app) return;
    const total = app.getBoundingClientRect().width || 1200;
    const esq = Math.min(Math.max(larguras.esq, LIMITES.esq[0]), LIMITES.esq[1]);
    // O centro nunca fica com menos de 320 px.
    const dir = Math.min(Math.max(larguras.dir, LIMITES.dir[0]), Math.max(LIMITES.dir[0], total - (estado.lateral ? esq : 0) - 332));
    app.style.setProperty('--chat-esq', `${esq}px`);
    app.style.setProperty('--chat-dir', `${dir}px`);
    const painelVisivel = !box.querySelector('.chat-painel').hidden;
    app.classList.toggle('sem-lateral', !estado.lateral);
    app.classList.toggle('sem-painel', !painelVisivel);
    app.querySelectorAll('.chat-divisor').forEach((d) => {
      const lado = d.dataset.divisor;
      d.hidden = lado === 'esq' ? !estado.lateral : !painelVisivel;
      d.setAttribute('aria-valuenow', String(lado === 'esq' ? esq : dir));
    });
  }

  function guardarLarguras() { try { localStorage.setItem(LARGURAS, JSON.stringify(larguras)); } catch (e) { /* sem espaço */ } }

  function ligarDivisores() {
    const app = box.querySelector('.chat-app');
    app.querySelectorAll('.chat-divisor').forEach((d) => {
      const lado = d.dataset.divisor;
      d.addEventListener('pointerdown', (ev) => {
        ev.preventDefault();
        d.setPointerCapture(ev.pointerId);
        app.classList.add('arrastando');
        const rect = app.getBoundingClientRect();
        const mover = (e) => {
          larguras[lado] = lado === 'esq' ? e.clientX - rect.left : rect.right - e.clientX;
          aplicarLarguras();
        };
        const soltar = () => {
          app.classList.remove('arrastando');
          d.removeEventListener('pointermove', mover);
          d.removeEventListener('pointerup', soltar);
          d.removeEventListener('pointercancel', soltar);
          guardarLarguras();
        };
        d.addEventListener('pointermove', mover);
        d.addEventListener('pointerup', soltar);
        d.addEventListener('pointercancel', soltar);
      });
      d.addEventListener('keydown', (ev) => {
        const passo = ev.shiftKey ? 64 : 16;
        const sinal = { ArrowLeft: -1, ArrowRight: 1 }[ev.key];
        if (!sinal && ev.key !== 'Home') return;
        ev.preventDefault();
        if (ev.key === 'Home') larguras[lado] = PADRAO[lado];
        else larguras[lado] += (lado === 'esq' ? sinal : -sinal) * passo;
        aplicarLarguras();
        guardarLarguras();
      });
      d.addEventListener('dblclick', () => { larguras[lado] = PADRAO[lado]; aplicarLarguras(); guardarLarguras(); });
    });
    window.addEventListener('resize', aplicarLarguras);
  }

  async function render() {
    const alvo = document.getElementById('view_assistente');
    if (!alvo) return;
    if (!box) {
      box = alvo;
      const divisor = (lado, rotulo) => `<div class="chat-divisor" data-divisor="${lado}" role="separator" aria-orientation="vertical" tabindex="0"
        aria-label="${rotulo}" aria-valuemin="${LIMITES[lado][0]}" aria-valuemax="${LIMITES[lado][1]}"
        title="Arraste para ajustar · setas do teclado · dois cliques volta ao padrão"></div>`;
      box.innerHTML = `<div class="chat-app"><aside class="chat-lateral" aria-label="Conversas"></aside>
        ${divisor('esq', 'Largura da lista de conversas')}
        <section class="chat-centro" aria-label="Conversa"></section>
        ${divisor('dir', 'Largura do painel de artefatos')}
        <aside class="chat-painel" aria-label="Artefatos"></aside></div>`;
      ligar();
      ligarDivisores();
      aplicarLarguras();  // já com as larguras guardadas, antes de carregar as conversas (sem "pulo" na tela)
    }
    await carregarConversas();
    desenhar();
  }

  window.SIGP_ASSISTENTE = { render, perguntar, abrir };
})();
