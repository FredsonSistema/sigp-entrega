// Configurações > Acesso. Três páginas desenhadas por este módulo:
//   #cfgUsuarios   Usuários e integrações (pessoas com senha e integrações com chave de API)
//   #cfgPermissoes Grupos de permissão (grupos e a visão "quem pode o quê")
//   #cfgAuditoria  Auditoria de acesso (gravações, recusas e entradas)
// O administrador (chave do .env) cria grupos, usuários e ajustes individuais; os demais veem o próprio perfil.
// A regra vale na API (backend/acesso.py); aqui a tela só esconde as abas sem permissão.
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const api = async (caminho, opcoes = {}) => {
    const r = await fetch(`${window.SIGP_CONFIG.apiUrl()}${caminho}`, {
      ...opcoes, headers: { 'Content-Type': 'application/json', ...(opcoes.headers || {}) },
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || `A API respondeu HTTP ${r.status}.`);
    return j;
  };
  const dataHora = (v) => (v ? new Date(v).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—');
  let dados = { catalogo: [], grupos: [], usuarios: [], auditoria: [] };
  const abertos = new Set();
  const filtroAud = { quem: '', resultado: '' };
  let ehAdmin = false;
  let paineis = null;

  // ---------------------------------------------------------------- perfil ativo na tela
  async function aplicar() {
    let eu;
    try { eu = await api('/api/acesso/eu'); } catch (e) { return null; }
    window.SIGP_ACESSO = eu;
    document.querySelectorAll('.tab[data-view]').forEach((tab) => {
      tab.hidden = Array.isArray(eu.abas) && !eu.abas.includes(tab.dataset.view);
    });
    const ativa = document.querySelector('.tab.active');
    if (ativa && ativa.hidden) document.querySelector('.tab[data-view]:not([hidden])')?.click();
    let chip = document.getElementById('perfilAtivo');
    const barra = document.querySelector('header .tabs');
    if (!chip && barra) {
      chip = document.createElement('span');
      chip.id = 'perfilAtivo';
      chip.className = 'perfil-chip';
      barra.appendChild(chip);
    }
    if (chip) {
      chip.textContent = eu.perfil === 'administrador' ? (eu.usuario ? `${eu.usuario} · Administrador` : 'Administrador') : eu.perfil === 'usuario' ? `${eu.usuario || eu.nome} · ${eu.grupo}` : '';
      chip.hidden = !chip.textContent;
    }
    return eu;
  }

  // ---------------------------------------------------------------- partes comuns
  const nomeFunc = () => Object.fromEntries(dados.catalogo.flatMap((a) => a.funcionalidades.map((f) => [f.id, f])));
  const pill = (texto, tipo = '') => `<span class="cfg-pill${tipo ? ` cfg-pill-${tipo}` : ''}">${esc(texto)}</span>`;
  const acc = (chave) => (abertos.has(chave) ? ' open' : '');
  const opcoesGrupo = (sel) => dados.grupos.map((g) => `<option value="${esc(g.id)}"${g.id === sel ? ' selected' : ''}>${esc(g.nome)}</option>`).join('');
  // Perfis de uma pessoa: Administrador (tudo) ou um dos grupos.
  const opcoesPerfil = (sel) => `<option value="admin"${sel === 'admin' ? ' selected' : ''}>Administrador (todas as permissões)</option>${opcoesGrupo(sel)}`;
  const pessoas = () => dados.usuarios.filter((u) => u.tipo === 'pessoa');
  const integracoes = () => dados.usuarios.filter((u) => u.tipo !== 'pessoa');
  const rodape = (conteudo) => `<div class="cfg-cartao-f">${conteudo}</div>`;

  function situacao(u) {
    if (!u.ativo) return pill('desativado', 'bad');
    if (u.bloqueadoAte && u.bloqueadoAte > new Date().toISOString()) return pill('bloqueado por tentativas', 'bad');
    if (u.trocarSenha) return pill('aguardando a troca da senha temporária', 'warn');
    return pill('ativo', 'ok');
  }

  // Permissões de um grupo: uma seção por área, caixas em duas colunas.
  function caixasPermissoes(selecionadas) {
    return dados.catalogo.map((a) => `<div class="perm-sec"><h5>${esc(a.area)} · ${a.funcionalidades.filter((f) => selecionadas.includes(f.id)).length}/${a.funcionalidades.length}</h5>
      <div class="perm-list">${a.funcionalidades.map((f) => `<label title="${esc(f.id)}"><input type="checkbox" data-perm="${esc(f.id)}"${selecionadas.includes(f.id) ? ' checked' : ''}><span>${esc(f.nome)}</span></label>`).join('')}</div></div>`).join('');
  }

  function ajustesUsuario(u) {
    const grupo = dados.grupos.find((g) => g.id === u.grupoId) || { permissoes: [] };
    return dados.catalogo.map((a) => `<details class="nr-disc"${acc(`aj:${u.id}:${a.area}`)} data-abre="${esc(`aj:${u.id}:${a.area}`)}">
      <summary>${esc(a.area)}</summary>
      <div class="nr-disc-body perm-lista">${a.funcionalidades.map((f) => {
        const herda = grupo.permissoes.includes(f.id);
        const atual = u.ajustes[f.id] === true ? 'permitir' : u.ajustes[f.id] === false ? 'negar' : '';
        const efetiva = u.permissoes.includes(f.id);
        return `<div class="perm-ajuste"><span class="${efetiva ? 'perm-sim' : 'perm-nao'}" aria-label="${efetiva ? 'permitido' : 'negado'}">${efetiva ? '✓' : '✗'}</span>
          <span>${esc(f.nome)}</span>
          <select class="f" data-ajuste="${esc(f.id)}" aria-label="Ajuste de ${esc(f.nome)}">
            <option value=""${atual === '' ? ' selected' : ''}>Herdar do grupo (${herda ? 'permitido' : 'negado'})</option>
            <option value="permitir"${atual === 'permitir' ? ' selected' : ''}>Permitir só para este usuário</option>
            <option value="negar"${atual === 'negar' ? ' selected' : ''}>Negar só para este usuário</option>
          </select></div>`;
      }).join('')}</div></details>`).join('');
  }

  // ---------------------------------------------------------------- Usuários e integrações
  function editorPessoa(u) {
    return `<div class="perm-editor-corpo">
      <div class="cfg-grid">
        <label>Nome<input class="f" data-campo="nome" maxlength="80" value="${esc(u.nome)}"></label>
        <label>Nome de usuário (para entrar)<input class="f" data-campo="usuario" maxlength="40" autocomplete="off" value="${esc(u.usuario)}"></label>
        <label>Perfil<select class="f" data-campo="grupoId">${opcoesPerfil(u.grupoId)}</select></label>
        <label class="cfg-toggle cfg-alinha-base"><input type="checkbox" data-campo="ativo"${u.ativo ? ' checked' : ''}> Usuário ativo</label>
      </div>
      ${u.grupoId === 'admin' ? '' : `<details class="nr-disc" data-abre="ajs:${esc(u.id)}"${acc(`ajs:${u.id}`)}><summary>Ajustes individuais (opcional)</summary><div class="nr-disc-body">
        <div class="hint" style="margin:4px 0 8px">Valem só para esta pessoa, por cima do perfil.</div>${ajustesUsuario(u)}</div></details>`}
      <div class="perm-editor-acoes">
        <button class="ghost small" type="button" data-acao="alternar" data-alterna="usr:${esc(u.id)}">Cancelar</button>
        <button class="primary small" type="button" data-acao="salvar-usuario">Salvar</button>
      </div></div>`;
  }

  function editorIntegracao(u) {
    return `<div class="perm-editor-corpo">
      <div class="cfg-grid">
        <label>Nome<input class="f" data-campo="nome" maxlength="80" value="${esc(u.nome)}"></label>
        <label>Grupo de permissões<select class="f" data-campo="grupoId">${opcoesGrupo(u.grupoId)}</select></label>
        <label class="cfg-toggle"><input type="checkbox" data-campo="ativo"${u.ativo ? ' checked' : ''}> Integração ativa</label>
      </div>
      <details class="nr-disc" data-abre="ajs:${esc(u.id)}"${acc(`ajs:${u.id}`)}><summary>Ajustes individuais (opcional)</summary><div class="nr-disc-body">${ajustesUsuario(u)}</div></details>
      <div class="perm-editor-acoes">
        <button class="ghost small" type="button" data-acao="alternar" data-alterna="usr:${esc(u.id)}">Cancelar</button>
        <button class="primary small" type="button" data-acao="salvar-usuario">Salvar</button>
      </div></div>`;
  }

  function paginaUsuarios() {
    const linha = (u) => {
      const aberto = abertos.has(`usr:${u.id}`);
      return `<tr data-usuario="${esc(u.id)}"${aberto ? ' class="perm-linha-aberta"' : ''}><td><b>${esc(u.nome)}</b></td><td class="cfg-mono">${esc(u.usuario)}</td>
        <td>${esc(u.grupoNome)}</td><td>${situacao(u)}</td><td class="hint">${esc(dataHora(u.ultimoUso))}</td>
        <td class="cfg-td-acoes"><button class="ghost small" type="button" data-acao="alternar" data-alterna="usr:${esc(u.id)}">${aberto ? 'Fechar' : 'Editar'}</button>
          <button class="ghost small" type="button" data-acao="redefinir-senha">Redefinir senha</button></td></tr>
        ${aberto ? `<tr class="perm-editor" data-usuario="${esc(u.id)}"><td colspan="6">${editorPessoa(u)}</td></tr>` : ''}`;
    };
    const linhaIntegracao = (u) => {
      const aberto = abertos.has(`usr:${u.id}`);
      return `<div class="cfg-row" data-usuario="${esc(u.id)}"><div class="cfg-grow"><b>${esc(u.nome)}</b>
          <small>${esc(u.grupoNome)} · chave ${esc(u.chavePrefixo)}… · último uso ${esc(dataHora(u.ultimoUso))}</small></div>
        ${u.ativo ? pill('ativa', 'ok') : pill('desativada', 'bad')}
        <button class="ghost small" type="button" data-acao="alternar" data-alterna="usr:${esc(u.id)}">${aberto ? 'Fechar' : 'Editar'}</button>
        <button class="ghost small" type="button" data-acao="nova-chave">Gerar nova chave</button></div>
        ${aberto ? `<div class="cfg-row perm-editor" data-usuario="${esc(u.id)}">${editorIntegracao(u)}</div>` : ''}`;
    };
    const novoUsuario = abertos.has('novo:usuario') ? `<div class="cfg-cartao-b perm-novo">
        <div class="cfg-grid cfg-g3">
          <label>Nome<input class="f" id="permNovoNome" maxlength="80" placeholder="ex.: Maciel Lopes"></label>
          <label>Nome de usuário<input class="f" id="permNovoUsuario" maxlength="40" placeholder="ex.: maciel.lopes" autocomplete="off"></label>
          <label>Perfil<select class="f" id="permNovoGrupo">${opcoesPerfil('grp-operador')}</select></label>
        </div>
        <div class="perm-editor-acoes"><span class="hint">No primeiro acesso a pessoa é obrigada a trocar a senha.</span>
          <button class="ghost small" type="button" data-acao="alternar" data-alterna="novo:usuario">Cancelar</button>
          <button class="primary small" type="button" data-acao="criar-usuario">Adicionar e gerar senha temporária</button></div></div>` : '';
    const novaIntegracao = abertos.has('novo:integracao') ? `<div class="cfg-cartao-b perm-novo">
        <div class="cfg-grid">
          <label>Nome<input class="f" id="permNovaIntNome" maxlength="80" placeholder="ex.: Sistema financeiro"></label>
          <label>Grupo de permissões<select class="f" id="permNovaIntGrupo">${opcoesGrupo('grp-integracao')}</select></label>
        </div>
        <div class="perm-editor-acoes"><span class="hint">A chave aparece uma vez só, logo depois de criar.</span>
          <button class="ghost small" type="button" data-acao="alternar" data-alterna="novo:integracao">Cancelar</button>
          <button class="primary small" type="button" data-acao="criar-integracao">Criar integração e gerar chave</button></div></div>` : '';
    return `<div id="permChaveNova" role="alert"></div>
      <section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Usuários <span class="hint">${pessoas().length}</span></h2>
          <button class="primary small" type="button" data-acao="alternar" data-alterna="novo:usuario">+ Adicionar usuário</button></div>
        ${novoUsuario}
        ${pessoas().length ? `<div class="cfg-tw"><table class="cfg-tabela"><thead><tr><th>Nome</th><th>Usuário</th><th>Perfil</th><th>Status</th><th>Último acesso</th><th></th></tr></thead>
          <tbody>${pessoas().map(linha).join('')}</tbody></table></div>` : '<div class="cfg-cartao-b hint">Nenhuma pessoa ainda.</div>'}
        ${rodape(`<span class="hint cfg-f-esq" data-perm-status role="status" aria-live="polite">Novos usuários recebem senha temporária e trocam no primeiro acesso.</span>
          <button class="ghost small" type="button" data-trocar-senha>Trocar minha senha</button>`)}</section>
      <section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Integrações com chave de API <span class="hint">${integracoes().length}</span></h2>
          <button class="ghost small" type="button" data-acao="alternar" data-alterna="novo:integracao">+ Nova integração</button></div>
        ${novaIntegracao}
        <div class="cfg-list">
          <div class="cfg-row"><div class="cfg-grow"><b>Chave do servidor</b><small>Administrador · fixa · SIGP_API_KEY do .env, usada pelo n8n e no primeiro acesso; não vai para o navegador</small></div>${pill('ativa', 'ok')}</div>
          ${integracoes().map(linhaIntegracao).join('')}
        </div>
        <div class="cfg-cartao-f"><span class="hint cfg-f-esq">Para outro sistema ou automação. Pessoas entram com usuário e senha, não com chave.</span></div></section>`;
  }

  // ---------------------------------------------------------------- Grupos de permissão
  function paginaGrupos() {
    const grupo = (g) => `<details class="cfg-acc" data-grupo="${esc(g.id)}" data-abre="grp:${esc(g.id)}"${acc(`grp:${g.id}`)}>
      <summary><b>${esc(g.nome)}</b>${g.padrao ? pill('padrão') : ''}<span class="cfg-acc-sub">${g.permissoes.length} permissão(ões) · ${g.usuarios} usuário(s)</span></summary>
      <div class="cfg-acc-body">
        <div class="cfg-grid">
          <label>Nome<input class="f" data-campo="nome" maxlength="80" value="${esc(g.nome)}"></label>
          <label>Descrição<input class="f" data-campo="descricao" maxlength="300" value="${esc(g.descricao)}"></label>
        </div>
        ${caixasPermissoes(g.permissoes)}
        <div class="perm-editor-acoes">
          ${g.padrao ? '' : '<button class="ghost small cfg-perigo" type="button" data-acao="excluir-grupo">Excluir grupo</button>'}
          <button class="primary small" type="button" data-acao="salvar-grupo">Salvar grupo</button>
        </div>
      </div></details>`;
    const novo = abertos.has('novo:grupo') ? `<section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Novo grupo</h2></div><div class="cfg-cartao-b">
        <div class="cfg-grid">
          <label>Nome<input class="f" id="permGrupoNome" maxlength="80" placeholder="ex.: Financeiro"></label>
          <label>Começar com as permissões de<select class="f" id="permGrupoBase"><option value="">nenhuma</option>${opcoesGrupo('')}</select></label>
        </div></div>
        ${rodape(`<button class="ghost small" type="button" data-acao="alternar" data-alterna="novo:grupo">Cancelar</button>
          <button class="primary small" type="button" data-acao="criar-grupo">Criar grupo</button>`)}</section>` : '';
    const colunas = dados.grupos.length + 2;
    const matriz = dados.catalogo.map((a) => `<tr class="cfg-tr-area"><td colspan="${colunas}">${esc(a.area)}</td></tr>
      ${a.funcionalidades.map((f) => `<tr><td title="${esc(f.id)} · ${esc(f.rotas.join(' · '))}">${esc(f.nome)}${f.abas.length ? `<div class="hint">aba ${esc(f.abas.join(', '))}</div>` : ''}</td>
        <td class="c perm-sim">✓</td>${dados.grupos.map((g) => (g.permissoes.includes(f.id) ? '<td class="c perm-sim">✓</td>' : '<td class="c perm-nao-v">—</td>')).join('')}</tr>`).join('')}`).join('');
    return `<div class="cfg-acoes-topo"><span class="hint" data-perm-status role="status" aria-live="polite"></span>
        <button class="primary small" type="button" data-acao="alternar" data-alterna="novo:grupo">+ Novo grupo</button></div>
      ${novo}
      ${dados.grupos.map(grupo).join('')}
      <section class="cfg-cartao perm-matriz"><div class="cfg-cartao-h"><h2>Quem pode o quê</h2><span class="hint">${dados.catalogo.reduce((n, a) => n + a.funcionalidades.length, 0)} funcionalidades · passe o mouse para ver as rotas</span></div>
        <div class="cfg-tw cfg-tw-alto"><table class="cfg-tabela perm-tabela"><thead><tr><th>Funcionalidade</th><th class="c">Admin</th>${dados.grupos.map((g) => `<th class="c">${esc(g.nome)}</th>`).join('')}</tr></thead>
          <tbody>${matriz}</tbody></table></div></section>`;
  }

  // ---------------------------------------------------------------- Auditoria de acesso
  function linhasAuditoria() {
    const nomes = nomeFunc();
    const lista = dados.auditoria.filter((i) => (!filtroAud.quem || i.usuario === filtroAud.quem) && (!filtroAud.resultado || i.resultado === filtroAud.resultado));
    if (!lista.length) return `<tr><td colspan="5" class="hint">${dados.auditoria.length ? 'Nada com esse filtro.' : 'Nada registrado ainda.'}</td></tr>`;
    return lista.map((i) => {
      const tipo = i.resultado === 'permitido' ? 'ok' : /negado|recusado|bloque/.test(i.resultado) ? 'bad' : '';
      return `<tr><td class="hint">${esc(dataHora(i.em))}</td><td>${esc(i.usuario)}</td><td class="cfg-mono">${esc(i.metodo)} ${esc(i.rota)}</td>
        <td>${esc(nomes[i.funcionalidade]?.nome || i.funcionalidade || '—')}</td><td>${pill(`${i.resultado} (${i.status})`, tipo)}</td></tr>`;
    }).join('');
  }
  function paginaAuditoria() {
    const quem = [...new Set(dados.auditoria.map((i) => i.usuario).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    const resultados = [...new Set(dados.auditoria.map((i) => i.resultado).filter(Boolean))].sort();
    const op = (v, t, sel) => `<option value="${esc(v)}"${v === sel ? ' selected' : ''}>${esc(t)}</option>`;
    return `<section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Registro <span class="hint">últimos ${dados.auditoria.length}</span></h2>
        <div class="cfg-filtros">
          <select class="f" data-aud-filtro="quem" aria-label="Filtrar por usuário">${op('', 'Todos os usuários', filtroAud.quem)}${quem.map((q) => op(q, q, filtroAud.quem)).join('')}</select>
          <select class="f" data-aud-filtro="resultado" aria-label="Filtrar por resultado">${op('', 'Todos os resultados', filtroAud.resultado)}${resultados.map((r) => op(r, r, filtroAud.resultado)).join('')}</select>
        </div></div>
      <div class="cfg-tw cfg-tw-alto"><table class="cfg-tabela"><thead><tr><th>Quando</th><th>Quem</th><th>Ação</th><th>Funcionalidade</th><th>Resultado</th></tr></thead>
        <tbody data-aud-linhas>${linhasAuditoria()}</tbody></table></div></section>`;
  }

  // ---------------------------------------------------------------- quem não é administrador
  async function desenharNaoAdmin(eu) {
    let catalogo = [];
    try { catalogo = (await api('/api/acesso/catalogo')).areas; } catch (e) { catalogo = []; }
    const minhas = new Set(eu?.permissoes || []);
    paineis.usuarios.innerHTML = `<section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Seu acesso</h2>
        <button class="ghost small" type="button" data-trocar-senha>Trocar minha senha</button></div>
      <div class="cfg-cartao-b"><div class="hint">Você entrou como <b>${esc(eu?.nome || 'visitante')}</b>${eu?.usuario ? ` (<code>${esc(eu.usuario)}</code>)` : ''}${eu?.grupo ? `, perfil ${esc(eu.grupo)}` : ''}. Só o administrador altera perfis e permissões.</div>
        ${catalogo.length ? catalogo.map((a) => `<div class="perm-sec"><h5>${esc(a.area)}</h5><div class="perm-list">
          ${a.funcionalidades.map((f) => `<div><span class="${minhas.has(f.id) ? 'perm-sim' : 'perm-nao'}">${minhas.has(f.id) ? '✓' : '✗'}</span> ${esc(f.nome)}</div>`).join('')}</div></div>`).join('')
          : '<div class="hint">Peça ao administrador a lista das suas permissões.</div>'}</div></section>`;
    const aviso = '<section class="cfg-cartao"><div class="cfg-cartao-b hint">Só o administrador vê esta página. Suas permissões estão em Usuários e integrações.</div></section>';
    paineis.grupos.innerHTML = aviso;
    paineis.auditoria.innerHTML = aviso;
  }

  // ---------------------------------------------------------------- desenho e ações
  function desenhar() {
    if (!paineis || !ehAdmin) return;
    paineis.usuarios.innerHTML = paginaUsuarios();
    paineis.grupos.innerHTML = paginaGrupos();
    paineis.auditoria.innerHTML = paginaAuditoria();
    const layout = window.SIGP_CONFIG_LAYOUT;
    layout?.marcar('usuarios', pessoas().length);
    layout?.marcar('grupos', dados.grupos.length);
  }

  async function render() {
    const grupos = document.getElementById('cfgPermissoes');
    if (!grupos) return;
    paineis = {
      usuarios: document.getElementById('cfgUsuarios') || grupos,
      grupos,
      auditoria: document.getElementById('cfgAuditoria') || grupos,
    };
    const eu = await aplicar();
    Object.values(paineis).forEach(ligar);
    ehAdmin = Boolean(eu && eu.perfil === 'administrador');
    if (!ehAdmin) { await desenharNaoAdmin(eu); return; }
    try {
      const [catalogo, gruposR, usuarios, auditoria] = await Promise.all([
        api('/api/acesso/catalogo'), api('/api/acesso/grupos'), api('/api/acesso/usuarios'), api('/api/acesso/auditoria?limite=100'),
      ]);
      dados = { catalogo: catalogo.areas, grupos: gruposR.items, usuarios: usuarios.items, auditoria: auditoria.items };
    } catch (erro) {
      const msg = `<div class="backup-warn" role="alert">Não foi possível carregar perfis e permissões: ${esc(erro.message)}</div>`;
      Object.values(paineis).forEach((p) => { p.innerHTML = msg; });
      return;
    }
    desenhar();
  }

  // Mensagem no rodapé da página onde o botão estava (ou na primeira página com espaço para isso).
  const status = (texto, perto) => {
    const s = perto?.closest('#cfgUsuarios, #cfgPermissoes, #cfgAuditoria')?.querySelector('[data-perm-status]')
      || document.querySelector('#view_config [data-perm-status]');
    if (s) s.textContent = texto;
  };

  function mostrarChave(nome, chave) {
    const alvo = document.getElementById('permChaveNova');
    alvo.innerHTML = `<div class="perm-chave"><b>Chave de ${esc(nome)}</b> (aparece só agora; o sistema guarda apenas um resumo dela):
      <code data-chave>${esc(chave)}</code> <button class="ghost small" type="button" data-acao="copiar-chave">Copiar</button>
      <div class="hint">Configure no outro sistema (cabeçalho X-API-Key). Não use em navegador.</div></div>`;
  }
  function mostrarSenha(u, senha) {
    const alvo = document.getElementById('permChaveNova');
    alvo.innerHTML = `<div class="perm-chave"><b>Acesso de ${esc(u.nome)}</b> (a senha aparece só agora):
      usuário <code>${esc(u.usuario)}</code> · senha temporária <code data-chave>${esc(senha)}</code>
      <button class="ghost small" type="button" data-acao="copiar-chave">Copiar senha</button>
      <div class="hint">Entregue à pessoa por um canal seguro. No primeiro acesso ela é obrigada a trocar a senha.</div></div>`;
  }
  const valor = (id) => (document.getElementById(id)?.value || '').trim();

  function ligar(box) {
    if (box.dataset.ligado) return;
    box.dataset.ligado = '1';
    box.addEventListener('toggle', (ev) => {
      const k = ev.target.dataset?.abre;
      if (!k) return;
      if (ev.target.open) abertos.add(k); else abertos.delete(k);
    }, true);
    box.addEventListener('change', (ev) => {
      const f = ev.target.closest('[data-aud-filtro]');
      if (!f) return;
      filtroAud[f.dataset.audFiltro] = f.value;
      const corpo = box.querySelector('[data-aud-linhas]');
      if (corpo) corpo.innerHTML = linhasAuditoria();
    });
    box.addEventListener('click', async (ev) => {
      if (ev.target.closest('[data-trocar-senha]')) { window.SIGP_LOGIN?.trocarSenha(); return; }
      const botao = ev.target.closest('[data-acao]');
      if (!botao) return;
      const acao = botao.dataset.acao;
      if (acao === 'alternar') {
        const k = botao.dataset.alterna;
        if (abertos.has(k)) abertos.delete(k); else abertos.add(k);
        desenhar();
        const foco = { 'novo:usuario': 'permNovoNome', 'novo:integracao': 'permNovaIntNome', 'novo:grupo': 'permGrupoNome' }[k];
        if (foco && abertos.has(k)) document.getElementById(foco)?.focus();
        return;
      }
      try {
        if (acao === 'copiar-chave') {
          await navigator.clipboard.writeText(document.querySelector('#permChaveNova [data-chave]').textContent);
          status('Copiado.', botao);
          return;
        }
        botao.disabled = true;
        if (acao === 'criar-usuario') {
          const r = await api('/api/acesso/usuarios', { method: 'POST', body: JSON.stringify({
            tipo: 'pessoa', nome: valor('permNovoNome'), usuario: valor('permNovoUsuario'), grupoId: valor('permNovoGrupo') }) });
          abertos.delete('novo:usuario');
          await render();
          mostrarSenha(r.item, r.senhaTemporaria);
          status(`Usuário ${r.item.usuario} adicionado.`, paineis.usuarios);
          return;
        }
        if (acao === 'criar-integracao') {
          const r = await api('/api/acesso/usuarios', { method: 'POST', body: JSON.stringify({
            tipo: 'integracao', nome: valor('permNovaIntNome'), grupoId: valor('permNovaIntGrupo') }) });
          abertos.delete('novo:integracao');
          await render();
          mostrarChave(r.item.nome, r.chave);
          status(`Integração ${r.item.nome} criada.`, paineis.usuarios);
          return;
        }
        if (acao === 'redefinir-senha') {
          const id = botao.closest('[data-usuario]').dataset.usuario;
          if (!window.confirm('Gerar uma senha temporária? A senha atual deixa de valer e as sessões abertas desta pessoa são encerradas.')) return;
          const r = await api(`/api/acesso/usuarios/${encodeURIComponent(id)}/redefinir-senha`, { method: 'POST' });
          await render();
          mostrarSenha(r.item, r.senhaTemporaria);
          return;
        }
        if (acao === 'nova-chave') {
          const id = botao.closest('[data-usuario]').dataset.usuario;
          if (!window.confirm('Gerar uma nova chave? A chave atual deixa de funcionar na hora.')) return;
          const r = await api(`/api/acesso/usuarios/${encodeURIComponent(id)}/nova-chave`, { method: 'POST' });
          await render();
          mostrarChave(r.item.nome, r.chave);
          return;
        }
        if (acao === 'salvar-usuario') {
          const el = botao.closest('.perm-editor');
          const id = el.dataset.usuario;
          const ajustes = {};
          el.querySelectorAll('[data-ajuste]').forEach((s) => { if (s.value) ajustes[s.dataset.ajuste] = s.value === 'permitir'; });
          const campoUsuario = el.querySelector('[data-campo="usuario"]');
          const antes = dados.usuarios.find((u) => u.id === id)?.usuario;
          const r = await api(`/api/acesso/usuarios/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({
            nome: el.querySelector('[data-campo="nome"]').value, grupoId: el.querySelector('[data-campo="grupoId"]').value,
            ativo: el.querySelector('[data-campo="ativo"]').checked, ajustes, ...(campoUsuario ? { usuario: campoUsuario.value } : {}) }) });
          abertos.delete(`usr:${id}`);
          await render();
          const mudouLogin = campoUsuario && antes && r.item.usuario !== antes;
          status(mudouLogin ? `Usuário salvo. Agora ele entra como "${r.item.usuario}" (a senha não mudou).`
            : 'Usuário salvo. As permissões valem a partir da próxima ação dele.', paineis.usuarios);
          if (mudouLogin && window.SIGP_ACESSO?.usuario === antes) aplicar();
          return;
        }
        if (acao === 'salvar-grupo' || acao === 'excluir-grupo') {
          const el = botao.closest('[data-grupo]');
          const id = el.dataset.grupo;
          if (acao === 'excluir-grupo') {
            if (!window.confirm('Excluir este grupo?')) return;
            await api(`/api/acesso/grupos/${encodeURIComponent(id)}`, { method: 'DELETE' });
          } else {
            const permissoes = [...el.querySelectorAll('[data-perm]:checked')].map((c) => c.dataset.perm);
            await api(`/api/acesso/grupos/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({
              nome: el.querySelector('[data-campo="nome"]').value, descricao: el.querySelector('[data-campo="descricao"]').value, permissoes }) });
          }
          await render();
          status(acao === 'excluir-grupo' ? 'Grupo excluído.' : 'Grupo salvo. Vale na hora para todos os usuários dele.', paineis.grupos);
          return;
        }
        if (acao === 'criar-grupo') {
          const base = dados.grupos.find((g) => g.id === valor('permGrupoBase'));
          const r = await api('/api/acesso/grupos', { method: 'POST', body: JSON.stringify({
            nome: valor('permGrupoNome'), descricao: base ? `Baseado em ${base.nome}` : '', permissoes: base ? base.permissoes : [] }) });
          abertos.delete('novo:grupo');
          if (r?.item?.id) abertos.add(`grp:${r.item.id}`);
          await render();
          status('Grupo criado. Escolha as permissões e clique em "Salvar grupo".', paineis.grupos);
        }
      } catch (erro) {
        status(erro.message, botao);
      } finally {
        botao.disabled = false;
      }
    });
  }

  window.SIGP_PERMISSOES = { render, aplicar };
})();
