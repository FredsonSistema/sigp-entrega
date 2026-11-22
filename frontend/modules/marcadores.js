// Marcadores e grupos de localidades (backend/marcadores.py).
// - Marcador: etiqueta posta à mão em cada local (Regional Itabuna, Terceirizado, CS...). Fica no local ("marcadores").
// - Grupo: regra só com dados do cadastro (provedor, cidade, tipo, link reserva, marcador, sem provedor); os locais
//   entram e saem sozinhos. Quem calcula os membros é a API (mesma regra do assistente).
// Partes: catálogo em cache, editor de marcadores no formulário do local, pílulas e filtro das listas e a tela
// Configurações > Marcadores e grupos.
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const chave = (v) => String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim();
  const cor = (v) => (/^#[0-9a-fA-F]{6}$/.test(String(v || '')) ? v : '#999999');
  const base = () => window.SIGP_CONFIG.apiUrl();
  const api = async (caminho, metodo = 'GET', corpo) => {
    const r = await fetch(`${base()}${caminho}`, {
      method: metodo, headers: { 'Content-Type': 'application/json' },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw Object.assign(new Error(j.error || `A API respondeu HTTP ${r.status}.`), { status: r.status });
    return j;
  };
  const pode = () => !window.SIGP_ACESSO || window.SIGP_ACESSO.perfil === 'administrador'
    || (window.SIGP_ACESSO.permissoes || []).includes('locais.editar');
  const CAMPOS = [
    ['provedor', 'Provedor é'], ['cidade', 'Cidade é'], ['tipo', 'Tipo é'], ['reserva', 'Link reserva'],
    ['marcador', 'Tem o marcador'], ['sem_provedor', 'Sem provedor cadastrado'],
  ];
  const TIPOS = [['agencia', 'Agência'], ['rodoviaria', 'Rodoviária'], ['garagem', 'Garagem']];
  const ROTULO_TIPO = { agencia: 'agência', rodoviaria: 'rodoviária', garagem: 'garagem' };

  // ---------------------------------------------------------------- catálogo (cache)
  let itens = [];
  let carregado = false;
  let carregando = null;
  function carregar() {
    if (carregando) return carregando;
    carregando = api('/api/marcadores')
      .then((j) => { itens = j.items || []; carregado = true; })
      .catch(() => { /* sem permissão ou API fora: listas seguem sem marcadores */ })
      .finally(() => {
        carregando = null;
        atualizarDatalist();
        atualizarFiltros();
        window.dispatchEvent(new CustomEvent('sigp:marcadores-atualizados'));
      });
    return carregando;
  }
  const soMarcadores = () => itens.filter((m) => m.tipo === 'marcador');
  const soGrupos = () => itens.filter((m) => m.tipo === 'grupo');
  const porNome = (nome) => soMarcadores().find((m) => chave(m.nome) === chave(nome)
    || (m.apelidos || []).some((a) => chave(a) === chave(nome)));
  const gruposDoLocal = (id) => soGrupos().filter((g) => (g.membros || []).some((x) => String(x.id) === String(id)));

  function pilula(nome, c, opcoes = {}) {
    const k = cor(c);
    const estilo = opcoes.grupo
      ? `border:1px dashed ${k}; color:${k}`
      : `background:${k}26; border:1px solid ${k}`;
    return `<span class="mk-pill${opcoes.grupo ? ' mk-grupo' : ''}" style="${estilo}" title="${esc(opcoes.titulo || (opcoes.grupo ? 'Grupo (automático pelo cadastro)' : 'Marcador'))}">${opcoes.grupo ? '◎ ' : ''}${esc(nome)}${opcoes.remover ? ` <button type="button" class="mk-x" data-mk-remover="${esc(nome)}" aria-label="Tirar ${esc(nome)}">×</button>` : ''}</span>`;
  }

  // Pílulas na lista (coluna do nome): marcadores do local e os grupos em que ele está.
  function pilulas(local) {
    if (!local) return '';
    const marc = (local.marcadores || []).map((n) => pilula((porNome(n) || {}).nome || n, (porNome(n) || {}).cor));
    const grupos = gruposDoLocal(local.id).map((g) => pilula(g.nome, g.cor, { grupo: true, titulo: `Grupo: ${g.regraTexto || ''}` }));
    const todas = [...marc, ...grupos];
    return todas.length ? `<div class="mk-pills mk-na-lista">${todas.join('')}</div>` : '';
  }

  // ---------------------------------------------------------------- filtro das listas
  function opcoesFiltro(valor) {
    const op = (v, t) => `<option value="${esc(v)}"${v === valor ? ' selected' : ''}>${esc(t)}</option>`;
    const m = soMarcadores().map((x) => op(`m:${x.id}`, `${x.nome} (${x.locais})`)).join('');
    const g = soGrupos().map((x) => op(`g:${x.id}`, `${x.nome} (${x.locais})`)).join('');
    return op('', 'Todos os marcadores e grupos') + (m ? `<optgroup label="Marcadores">${m}</optgroup>` : '') + (g ? `<optgroup label="Grupos">${g}</optgroup>` : '');
  }
  function atualizarFiltros() {
    document.querySelectorAll('select.mk-filtro:not(.sc-filtro)').forEach((s) => {
      const atual = s.value;
      s.innerHTML = opcoesFiltro(atual);
      if (atual && ![...s.options].some((o) => o.value === atual)) s.value = '';
    });
  }
  function passaNoFiltro(local, valor) {
    if (!valor) return true;
    const [tipo, id] = [valor.slice(0, 1), valor.slice(2)];
    const item = itens.find((x) => x.id === id);
    if (!item) return true;
    if (tipo === 'g') return (item.membros || []).some((x) => String(x.id) === String(local.id));
    const alvos = new Set([item.nome, ...(item.apelidos || [])].map(chave));
    return (local.marcadores || []).some((n) => alvos.has(chave(n)));
  }
  const textoBusca = (local) => [...(local.marcadores || []), ...gruposDoLocal(local.id).map((g) => g.nome)].join(' ');

  // ---------------------------------------------------------------- editor no formulário do local
  function atualizarDatalist() {
    let dl = document.getElementById('sigpMarcadoresLista');
    if (!dl) {
      dl = document.createElement('datalist');
      dl.id = 'sigpMarcadoresLista';
      document.body.appendChild(dl);
    }
    dl.innerHTML = soMarcadores().map((m) => `<option value="${esc(m.nome)}">${esc(m.descricao || '')}</option>`).join('');
  }
  function desenharEditor(box) {
    const lista = JSON.parse(box.dataset.mkValor || '[]');
    const grupos = gruposDoLocal(box.dataset.mkLocal);
    box.innerHTML = `<div class="mk-pills">${lista.map((n) => pilula(n, (porNome(n) || {}).cor, { remover: true })).join('') || '<span class="hint">Nenhum marcador.</span>'}</div>
      <div class="mk-add"><input type="text" class="f" list="sigpMarcadoresLista" data-mk-novo placeholder="Marcador (ex.: Regional Itabuna, Terceirizado, CS)" maxlength="60">
        <button type="button" class="ghost small" data-mk-adicionar>+ adicionar marcador</button></div>
      <div class="hint">Grupos (automáticos pelo cadastro salvo): ${grupos.length ? grupos.map((g) => pilula(g.nome, g.cor, { grupo: true, titulo: g.regraTexto })).join(' ') : 'nenhum'}.
        Novo marcador digitado entra no catálogo (Configurações › Marcadores e grupos).</div>`;
  }
  function montarEditor(id, lista, localId) {
    const box = document.getElementById(id);
    if (!box) return;
    box.dataset.mkValor = JSON.stringify((Array.isArray(lista) ? lista : []).map((n) => (porNome(n) || {}).nome || n));
    box.dataset.mkLocal = localId || '';
    if (!box.dataset.mkLigado) {
      box.dataset.mkLigado = '1';
      const adicionar = () => {
        const campo = box.querySelector('[data-mk-novo]');
        const digitado = String(campo.value || '').replace(/\s+/g, ' ').trim().slice(0, 60);
        if (!digitado) return;
        const nome = (porNome(digitado) || {}).nome || digitado;
        const atual = JSON.parse(box.dataset.mkValor || '[]');
        if (!atual.some((n) => chave(n) === chave(nome))) atual.push(nome);
        box.dataset.mkValor = JSON.stringify(atual);
        desenharEditor(box);
        box.querySelector('[data-mk-novo]').focus();
      };
      box.addEventListener('click', (ev) => {
        const tirar = ev.target.closest('[data-mk-remover]');
        if (tirar) {
          box.dataset.mkValor = JSON.stringify(JSON.parse(box.dataset.mkValor || '[]').filter((n) => n !== tirar.dataset.mkRemover));
          desenharEditor(box);
        } else if (ev.target.closest('[data-mk-adicionar]')) adicionar();
      });
      box.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' && ev.target.matches('[data-mk-novo]')) { ev.preventDefault(); adicionar(); }
      });
    }
    desenharEditor(box);
    if (!carregado) carregar().then(() => desenharEditor(box));
  }
  function lerEditor(id) {
    const box = document.getElementById(id);
    if (!box) return [];
    // Texto digitado e não adicionado também conta (o usuário espera que "Salvar" grave o que está na tela).
    const pendente = String((box.querySelector('[data-mk-novo]') || {}).value || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    const lista = JSON.parse(box.dataset.mkValor || '[]');
    if (pendente && !lista.some((n) => chave(n) === chave(pendente))) lista.push((porNome(pendente) || {}).nome || pendente);
    return lista;
  }

  // Depois de gravar um local, a API pode ter trocado apelido pelo nome do catálogo e mudado os grupos.
  let timerGravados = null;
  window.addEventListener('sigp:locais-gravados', () => {
    clearTimeout(timerGravados);
    timerGravados = setTimeout(async () => {
      try { await window.SIGP_API.atualizarMarcadoresLocais(); } catch (e) { /* segue com o que está na tela */ }
      carregar();
    }, 700);
  });

  // ---------------------------------------------------------------- Configurações > Marcadores e grupos
  let box = null;
  let edicao = null; // { id?, tipo, nome, cor, descricao, apelidos, regra }
  let abertos = new Set();
  let timerPrevia = null;

  function sugestoes() {
    const provedores = new Set();
    const cidades = new Set();
    ['ti_agencias_v1', 'ti_rodoviarias_v1', 'ti_garagens_v1'].forEach((k) => {
      try {
        (JSON.parse(localStorage.getItem(k) || '[]') || []).forEach((l) => {
          if (l.cidade) cidades.add(String(l.cidade).trim());
          (l.provedores || []).forEach((p) => { if (p && p.nome) provedores.add(String(p.nome).trim()); });
        });
      } catch (e) { /* lista inválida: sem sugestão */ }
    });
    const ordenar = (s) => [...s].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    return { provedor: ordenar(provedores), cidade: ordenar(cidades), marcador: soMarcadores().map((m) => m.nome) };
  }
  function datalistsRegra() {
    const s = sugestoes();
    return ['provedor', 'cidade', 'marcador'].map((c) => `<datalist id="mkSug_${c}">${s[c].map((v) => `<option value="${esc(v)}">`).join('')}</datalist>`).join('');
  }
  function linhaCondicao(c, i) {
    const campos = CAMPOS.map(([v, t]) => `<option value="${v}"${v === c.campo ? ' selected' : ''}>${t}</option>`).join('');
    let valor = '';
    if (['provedor', 'cidade', 'marcador'].includes(c.campo)) {
      valor = `<input type="text" class="f" data-mk-valores="${i}" list="mkSug_${c.campo}" value="${esc((c.valores || []).join(', '))}"
        placeholder="um ou mais, separados por vírgula (qualquer um serve)">`;
    } else if (c.campo === 'tipo') {
      valor = TIPOS.map(([v, t]) => `<label class="mk-check"><input type="checkbox" data-mk-tipo="${i}" value="${v}"${(c.valores || []).includes(v) ? ' checked' : ''}> ${t}</label>`).join(' ');
    } else if (c.campo === 'reserva') {
      const nao = (c.valores || [])[0] === 'nao';
      valor = `<select class="f" data-mk-reserva="${i}"><option value="sim"${nao ? '' : ' selected'}>tem (2 ou mais links)</option><option value="nao"${nao ? ' selected' : ''}>não tem</option></select>`;
    } else {
      valor = '<span class="hint">nenhum provedor no cadastro</span>';
    }
    return `<div class="mk-cond"><select class="f" data-mk-campo="${i}" aria-label="Condição">${campos}</select><div class="mk-cond-valor">${valor}</div>
      <button type="button" class="ghost small" data-mk-acao="tirar-cond" data-i="${i}" title="Tirar condição">×</button></div>`;
  }
  function formulario() {
    const e = edicao;
    const grupo = e.tipo === 'grupo';
    const conds = (e.regra.condicoes || []);
    return `<div class="mk-form">
      <h4>${e.id ? 'Editar' : 'Criar'} ${grupo ? 'grupo' : 'marcador'}</h4>
      <div class="mk-form-linha">
        <label>Nome<input type="text" class="f" data-mk-campo-form="nome" maxlength="60" value="${esc(e.nome)}" placeholder="${grupo ? 'Ex.: He-Net, Regional Itabuna com reserva' : 'Ex.: Regional Itabuna'}"></label>
        <label>Cor<input type="color" data-mk-campo-form="cor" value="${esc(cor(e.cor || '#7c6bd6'))}"></label>
      </div>
      <label>Descrição<input type="text" class="f" data-mk-campo-form="descricao" maxlength="200" value="${esc(e.descricao)}" placeholder="Opcional"></label>
      ${grupo ? '' : `<label>Apelidos <span class="hint">outros nomes que o assistente e a importação reconhecem (ex.: RT = Rota)</span>
        <input type="text" class="f" data-mk-campo-form="apelidos" value="${esc((e.apelidos || []).join(', '))}" placeholder="separados por vírgula"></label>`}
      ${grupo ? `<div class="section-label">Regra <span class="hint">todas as condições valem juntas (E); dentro de uma condição, qualquer valor serve (OU) · só dados do cadastro</span></div>
        ${datalistsRegra()}
        <div class="mk-conds">${conds.map(linhaCondicao).join('')}</div>
        <button type="button" class="ghost small" data-mk-acao="mais-cond">+ condição</button>
        <div class="mk-previa" data-mk-previa aria-live="polite"></div>` : ''}
      <div class="perm-editor-acoes"><span class="hint cfg-f-esq" data-mk-status></span>
        <button type="button" class="ghost small" data-mk-acao="cancelar">Cancelar</button>
        <button type="button" class="primary small" data-mk-acao="salvar">Salvar</button></div>
    </div>`;
  }
  function cartao(m) {
    const membros = (m.membros || []).map((x) => `<li>${esc(x.nome)} <span class="hint">${esc(ROTULO_TIPO[x.tipo] || x.tipo || '')}${x.cidade ? ` · ${esc(x.cidade)}` : ''}</span></li>`).join('');
    const detalhe = [m.descricao || 'Sem descrição', m.tipo === 'grupo' ? `Regra: ${m.regraTexto}` : '', (m.apelidos || []).length ? `Apelidos: ${m.apelidos.join(', ')}` : '']
      .filter(Boolean).map(esc).join(' · ');
    return `<div class="mk-card" data-mk-id="${esc(m.id)}">
      <div class="mk-card-topo">${pilula(m.nome, m.cor, { grupo: m.tipo === 'grupo' })}
        <button type="button" class="mk-locais" data-mk-acao="membros" data-id="${esc(m.id)}" title="Ver os locais" aria-expanded="${abertos.has(m.id)}">${m.locais} ${m.locais === 1 ? 'local' : 'locais'}</button>
        ${pode() ? `<span class="mk-card-acoes"><button type="button" class="cfg-icon-btn" data-mk-acao="editar" data-id="${esc(m.id)}" title="Editar" aria-label="Editar ${esc(m.nome)}">✎</button>
          <button type="button" class="cfg-icon-btn cfg-perigo" data-mk-acao="excluir" data-id="${esc(m.id)}" title="Excluir" aria-label="Excluir ${esc(m.nome)}">🗑</button></span>` : ''}</div>
      <p class="mk-card-desc">${detalhe}</p>
      ${abertos.has(m.id) ? `<ul class="mk-membros">${membros || '<li class="hint">Nenhum local.</li>'}</ul>` : ''}
    </div>`;
  }
  function desenhar() {
    if (!box) return;
    const botao = (acao, texto, cls) => (pode() ? `<button type="button" class="${cls} small" data-mk-acao="${acao}">${texto}</button>` : '');
    const marcadores = soMarcadores();
    const grupos = soGrupos();
    box.innerHTML = `${edicao ? `<section class="cfg-cartao mk-form-cartao">${formulario()}</section>` : ''}
      <section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Marcadores <span class="hint">${marcadores.length}</span></h2>${botao('novo-marcador', '+ Criar marcador', 'primary')}</div>
        <div class="cfg-cartao-b">
          <p class="cfg-intro">Postos à mão em cada local. Renomear ou excluir vale para todos os locais.${pode() ? '' : ' Só leitura: editar pede a permissão "Criar e editar locais".'}</p>
          <div class="mk-cards">${marcadores.map(cartao).join('') || '<div class="hint">Nenhum marcador.</div>'}</div></div></section>
      <section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Grupos <span class="hint">${grupos.length}</span></h2>${botao('novo-grupo', '+ Criar grupo', 'ghost')}</div>
        <div class="cfg-cartao-b">
          <p class="cfg-intro">Automáticos pela regra do cadastro (provedor, cidade, tipo, link reserva, marcador). Contas vencidas não entram aqui.</p>
          <div class="mk-cards">${grupos.map(cartao).join('') || '<div class="hint">Nenhum grupo. Ex.: "He-Net" = locais com internet da He-Net.</div>'}</div></div></section>`;
    window.SIGP_CONFIG_LAYOUT?.marcar('marcadores', itens.length);
    if (edicao && edicao.tipo === 'grupo') pedirPrevia();
  }
  function lerFormulario() {
    if (!box || !edicao) return;
    const v = (c) => (box.querySelector(`[data-mk-campo-form="${c}"]`) || {}).value;
    edicao.nome = v('nome') ?? edicao.nome;
    edicao.cor = v('cor') ?? edicao.cor;
    edicao.descricao = v('descricao') ?? edicao.descricao;
    if (edicao.tipo === 'marcador') edicao.apelidos = String(v('apelidos') || '').split(',').map((s) => s.trim()).filter(Boolean);
    (edicao.regra.condicoes || []).forEach((c, i) => {
      const campo = box.querySelector(`[data-mk-campo="${i}"]`);
      if (campo && campo.value !== c.campo) { c.campo = campo.value; c.valores = c.campo === 'reserva' ? ['sim'] : []; return; }
      const txt = box.querySelector(`[data-mk-valores="${i}"]`);
      if (txt) c.valores = txt.value.split(',').map((s) => s.trim()).filter(Boolean);
      const tipos = box.querySelectorAll(`[data-mk-tipo="${i}"]`);
      if (tipos.length) c.valores = [...tipos].filter((t) => t.checked).map((t) => t.value);
      const res = box.querySelector(`[data-mk-reserva="${i}"]`);
      if (res) c.valores = [res.value];
    });
  }
  function pedirPrevia() {
    clearTimeout(timerPrevia);
    timerPrevia = setTimeout(async () => {
      const alvo = box && box.querySelector('[data-mk-previa]');
      if (!alvo || !edicao) return;
      try {
        const p = await api('/api/marcadores/previa', 'POST', { regra: edicao.regra });
        const nomes = p.membros.slice(0, 40).map((m) => esc(m.nome)).join(', ');
        alvo.innerHTML = `<b>Prévia: ${p.locais} ${p.locais === 1 ? 'local' : 'locais'}</b> (${esc(p.regraTexto)})${p.locais ? `<br><span class="hint">${nomes}${p.locais > 40 ? '…' : ''}</span>` : ''}`;
      } catch (e) {
        alvo.innerHTML = `<span class="hint">${esc(e.message)}</span>`;
      }
    }, 350);
  }
  async function render(alvo) {
    box = document.getElementById(alvo);
    if (!box) return;
    box.innerHTML = '<div class="dash-empty">Carregando marcadores e grupos…</div>';
    await carregar();
    if (!carregado) { box.innerHTML = '<div class="dash-empty">Não foi possível carregar os marcadores (sem permissão ou API fora).</div>'; return; }
    desenhar();
    if (box.dataset.mkLigado) return;
    box.dataset.mkLigado = '1';
    box.addEventListener('input', (ev) => {
      if (!edicao || edicao.tipo !== 'grupo') return;
      if (ev.target.matches('[data-mk-valores]')) { lerFormulario(); pedirPrevia(); }
    });
    box.addEventListener('change', (ev) => {
      if (!edicao) return;
      if (ev.target.matches('[data-mk-campo]')) { lerFormulario(); desenhar(); }
      else if (ev.target.matches('[data-mk-tipo], [data-mk-reserva]')) { lerFormulario(); pedirPrevia(); }
    });
    box.addEventListener('click', async (ev) => {
      const b = ev.target.closest('[data-mk-acao]');
      if (!b) return;
      const acao = b.dataset.mkAcao;
      const item = itens.find((x) => x.id === b.dataset.id);
      if (acao === 'membros') { abertos.has(item.id) ? abertos.delete(item.id) : abertos.add(item.id); lerFormulario(); desenhar(); return; }
      if (acao === 'novo-marcador' || acao === 'novo-grupo') {
        const tipo = acao === 'novo-grupo' ? 'grupo' : 'marcador';
        edicao = { tipo, nome: '', cor: '', descricao: '', apelidos: [], regra: { condicoes: tipo === 'grupo' ? [{ campo: 'provedor', valores: [] }] : [] } };
        desenhar();
        box.querySelector('[data-mk-campo-form="nome"]').focus();
        return;
      }
      if (acao === 'editar') {
        edicao = JSON.parse(JSON.stringify({ id: item.id, tipo: item.tipo, nome: item.nome, cor: item.cor, descricao: item.descricao,
          apelidos: item.apelidos || [], regra: item.tipo === 'grupo' ? item.regra : { condicoes: [] } }));
        desenhar();
        box.querySelector('[data-mk-campo-form="nome"]').focus();
        return;
      }
      if (acao === 'cancelar') { edicao = null; desenhar(); return; }
      if (acao === 'mais-cond') { lerFormulario(); edicao.regra.condicoes.push({ campo: 'cidade', valores: [] }); desenhar(); return; }
      if (acao === 'tirar-cond') { lerFormulario(); edicao.regra.condicoes.splice(Number(b.dataset.i), 1); desenhar(); return; }
      const status = box.querySelector('[data-mk-status]');
      try {
        b.disabled = true;
        if (acao === 'salvar') {
          lerFormulario();
          const antigo = edicao.id ? itens.find((x) => x.id === edicao.id) : null;
          if (antigo && antigo.tipo === 'marcador' && chave(antigo.nome) !== chave(edicao.nome) && antigo.locais
            && !window.confirm(`Renomear "${antigo.nome}" para "${edicao.nome}" em ${antigo.locais} local(is)?`)) return;
          const corpo = { nome: edicao.nome, tipo: edicao.tipo, cor: edicao.cor, descricao: edicao.descricao, apelidos: edicao.apelidos, regra: edicao.regra };
          await api(edicao.id ? `/api/marcadores/${encodeURIComponent(edicao.id)}` : '/api/marcadores', edicao.id ? 'PUT' : 'POST', corpo);
          const nome = edicao.nome;
          edicao = null;
          await window.SIGP_API.atualizarMarcadoresLocais().catch(() => {});
          await carregar();
          desenhar();
          window.toast?.(`Salvo: ${nome}`);
        } else if (acao === 'excluir') {
          const msg = item.tipo === 'grupo'
            ? `Excluir o grupo "${item.nome}"? Os locais não mudam.`
            : `Excluir o marcador "${item.nome}"? Ele sai de ${item.locais} local(is).`;
          if (!window.confirm(msg)) return;
          await api(`/api/marcadores/${encodeURIComponent(item.id)}`, 'DELETE');
          if (edicao && edicao.id === item.id) edicao = null;
          await window.SIGP_API.atualizarMarcadoresLocais().catch(() => {});
          await carregar();
          desenhar();
          window.toast?.(`Excluído: ${item.nome}`);
        }
      } catch (e) {
        if (status) status.textContent = e.message; else window.toast?.(e.message, 6000);
      } finally {
        b.disabled = false;
      }
    });
  }

  window.SIGP_MARCADORES = { carregar, render, montarEditor, lerEditor, pilulas, opcoesFiltro, passaNoFiltro, textoBusca, itens: () => itens };
})();
