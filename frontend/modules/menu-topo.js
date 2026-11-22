// Barra do topo: marca · menus agrupados (Cadastros, Financeiro, Conciliação, Operação, Análise) · busca e perfil.
// Reaproveita os botões de aba que já existem (.tab[data-view]): eles passam para dentro dos menus, com o mesmo
// clique (switchTab) e a mesma regra de permissão (perfis-permissoes.js esconde a aba; menu sem aba visível some).
// As barras de ferramentas de cada tela (busca, filtros, "+ Nova") ficam numa segunda linha, abaixo do topo.
(() => {
  const GRUPOS = [
    ['Cadastros', ['agencias', 'rv', 'gr']],
    ['Financeiro', ['notas', 'notas-recebidas', 'faturas']],
    ['Conciliação', ['sig', 'sie']],
    ['Operação', ['os', 'agenda-servicos', 'agenda-pessoal', 'sys']],
    ['Análise', ['geral', 'assistente', 'ia']],
  ];

  function montar() {
    const header = document.querySelector('header');
    const nav = header?.querySelector('nav.tabs');
    const topo = header?.querySelector('.header-top');
    if (!nav || !topo || nav.dataset.menuMontado) return;
    nav.dataset.menuMontado = '1';
    const abas = new Map([...nav.querySelectorAll('.tab[data-view]')].map((t) => [t.dataset.view, t]));
    const soltas = [...abas.values()];
    GRUPOS.forEach(([titulo, views], i) => {
      const menu = document.createElement('div');
      menu.className = 'menu-grupo';
      const id = `menuGrupo${i}`;
      menu.innerHTML = `<button type="button" class="menu-btn" aria-haspopup="true" aria-expanded="false" aria-controls="${id}">${titulo}</button>
        <div class="menu-drop" id="${id}" role="menu"></div>`;
      const drop = menu.querySelector('.menu-drop');
      views.forEach((v) => {
        const aba = abas.get(v);
        if (!aba) return;
        aba.setAttribute('role', 'menuitem');
        drop.appendChild(aba);
        soltas.splice(soltas.indexOf(aba), 1);
      });
      nav.appendChild(menu);
    });

    // Topo em uma linha: marca · menus · busca; as barras de cada tela vão para a segunda linha.
    const linha = document.createElement('div');
    linha.className = 'topo-linha';
    const marca = topo.querySelector('.brand');
    const busca = topo.querySelector('.global-search-wrap');
    if (marca) linha.appendChild(marca);
    linha.appendChild(nav);
    const ferramentas = document.createElement('div');
    ferramentas.className = 'topo-ferramentas';
    if (busca) ferramentas.appendChild(busca);
    // O que não está em grupo (Configurações) vira o botão ⚙ ao lado da busca (mesmo .tab, mesmo clique).
    soltas.forEach((aba) => {
      aba.classList.add('menu-solto');
      aba.title = aba.textContent.trim();
      aba.setAttribute('aria-label', aba.title);
      if (aba.dataset.view === 'config') aba.textContent = '⚙';
      ferramentas.appendChild(aba);
    });
    // Conta e Sair uma vez só, no topo (cada barra de tela tinha os seus ⚙ e "Sair" repetidos).
    const conta = document.createElement('button');
    conta.type = 'button';
    conta.className = 'topo-icone';
    conta.title = 'Minha conta (trocar senha)';
    conta.setAttribute('aria-label', conta.title);
    conta.textContent = '👤';
    conta.addEventListener('click', () => document.getElementById('btnAccount')?.click());
    const sair = document.createElement('button');
    sair.type = 'button';
    sair.className = 'topo-sair';
    sair.textContent = 'Sair';
    sair.addEventListener('click', () => document.getElementById('btnLogout')?.click());
    ferramentas.append(conta, sair);
    linha.appendChild(ferramentas);
    header.insertBefore(linha, topo);
    topo.querySelectorAll('.toolbar button[id]').forEach((b) => {
      if (/(^|_)btn(Account|Logout)/.test(b.id)) b.classList.add('topo-duplicado');
    });
    topo.querySelectorAll('.toolbar').forEach((t) => {
      if (![...t.children].some((c) => !c.classList.contains('topo-duplicado') && c.type !== 'file' && c.style.display !== 'none')) t.classList.add('toolbar-vazia');
    });
    topo.classList.add('topo-subbarra');

    const fechar = (exceto) => nav.querySelectorAll('.menu-grupo.aberto').forEach((m) => {
      if (m === exceto) return;
      m.classList.remove('aberto');
      m.querySelector('.menu-btn').setAttribute('aria-expanded', 'false');
    });
    nav.addEventListener('click', (ev) => {
      const btn = ev.target.closest('.menu-btn');
      if (btn) {
        const menu = btn.parentElement;
        const abrir = !menu.classList.contains('aberto');
        fechar(menu);
        menu.classList.toggle('aberto', abrir);
        btn.setAttribute('aria-expanded', String(abrir));
        if (abrir) menu.querySelector('.tab:not([hidden])')?.focus();
        return;
      }
      if (ev.target.closest('.tab')) fechar();
    });
    document.addEventListener('click', (ev) => { if (!nav.contains(ev.target)) fechar(); });
    nav.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') { const m = ev.target.closest('.menu-grupo'); fechar(); m?.querySelector('.menu-btn')?.focus(); return; }
      if (!['ArrowDown', 'ArrowUp'].includes(ev.key) || !ev.target.closest('.menu-drop')) return;
      const itens = [...ev.target.closest('.menu-drop').querySelectorAll('.tab:not([hidden])')];
      const i = itens.indexOf(ev.target);
      ev.preventDefault();
      itens[(i + (ev.key === 'ArrowDown' ? 1 : -1) + itens.length) % itens.length]?.focus();
    });

    // Grupo ativo (aba ativa dentro dele) e grupo sem nenhuma aba permitida (escondido).
    const atualizar = () => nav.querySelectorAll('.menu-grupo').forEach((m) => {
      const visiveis = [...m.querySelectorAll('.tab')].filter((t) => !t.hidden);
      // Só muda o que mudou: reatribuir o mesmo valor também gera mutação e o observador entraria em laço.
      if (m.hidden !== !visiveis.length) m.hidden = !visiveis.length;
      const ativo = visiveis.some((t) => t.classList.contains('active'));
      if (m.classList.contains('ativo') !== ativo) m.classList.toggle('ativo', ativo);
      const btn = m.querySelector('.menu-btn');
      const ativa = visiveis.find((t) => t.classList.contains('active'));
      const titulo = ativa ? ativa.textContent.trim() : '';
      if (btn.title !== titulo) btn.title = titulo;
    });
    new MutationObserver(atualizar).observe(nav, { subtree: true, attributes: true, attributeFilter: ['class', 'hidden'] });
    // O selo do perfil (perfis-permissoes.js põe na barra de abas) vai para o lado da busca.
    const moverPerfil = () => {
      const chip = nav.querySelector('#perfilAtivo');
      if (chip) ferramentas.appendChild(chip);
    };
    new MutationObserver(moverPerfil).observe(nav, { childList: true });
    moverPerfil();
    atualizar();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', montar);
  else montar();
  window.SIGP_MENU = { montar };
})();
