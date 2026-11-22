// Configurações em páginas com menu lateral (Geral · Cadastros · Acesso · Integrações · Sistema).
// Reorganiza o que renderConfigTab desenha: cada "section-divider" vira um cartão e os cartões vão para a página
// do seu assunto. Nada é recriado: os mesmos elementos (ids, botões, módulos) só mudam de lugar. Páginas que não
// estão abertas ficam escondidas, mas continuam no DOM (os módulos desenham nelas normalmente).
(() => {
  const PAGINAS = [
    { id: 'preferencias', grupo: 'Geral', titulo: 'Preferências', desc: 'Alertas, arquivamento e caminhos usados pelo sistema.', secoes: ['Preferências'] },
    { id: 'empresa', grupo: 'Geral', titulo: 'Empresa prestadora', desc: 'Aparecem no PDF das Ordens de Serviço.', secoes: ['Dados da Empresa Prestadora'] },
    { id: 'alertas', grupo: 'Geral', titulo: 'Alertas por e-mail', secoes: ['Alertas por e-mail'] },
    { id: 'email-faturas', grupo: 'Geral', titulo: 'E-mail das faturas', desc: 'Remetentes que o sistema procura no Gmail. Muda aqui, vale no n8n em até 5 minutos.', secoes: ['E-mail das faturas'] },
    // nu: o módulo desenha os próprios cartões (o layout não embrulha a seção num cartão).
    { id: 'marcadores', grupo: 'Cadastros', titulo: 'Marcadores e grupos', nu: true,
      desc: 'Marcadores são postos à mão em cada local. Grupos são automáticos pela regra do cadastro.', secoes: ['Marcadores e grupos'] },
    { id: 'qualidade', grupo: 'Cadastros', titulo: 'Qualidade do cadastro', nu: true,
      desc: 'O que falta ou está inconsistente. Correções com prévia e backup do banco.', secoes: ['Qualidade do cadastro'] },
    { id: 'usuarios', grupo: 'Acesso', titulo: 'Usuários e integrações', nu: true,
      desc: 'Quem entra no sistema e quais automações usam chave de API.', secoes: ['Usuários e integrações'] },
    { id: 'grupos', grupo: 'Acesso', titulo: 'Grupos de permissão', nu: true,
      desc: 'Conjuntos de permissões. Ajustes individuais ficam no cadastro de cada usuário. A regra vale na API.', secoes: ['Grupos de permissão'] },
    { id: 'auditoria', grupo: 'Acesso', titulo: 'Auditoria de acesso', nu: true, desc: 'Últimas gravações, recusas e entradas no sistema.', secoes: ['Auditoria de acesso'] },
    { id: 'integracao', grupo: 'Integrações', titulo: 'API e n8n', nu: true,
      desc: 'Endereços, webhooks e envio de contas de provedores. Nada fica no código.', secoes: ['Integração'] },
    { id: 'servidor', grupo: 'Integrações', titulo: 'Servidor e serviços', nu: true,
      desc: 'Valores do arquivo .env e do n8n. Somente leitura.', secoes: ['Servidor e serviços'] },
    { id: 'ferramentas', grupo: 'Integrações', titulo: 'Winbox', desc: 'Abrir o Winbox direto pelo IP das unidades.', secoes: ['Integração Winbox', 'NFS-e', 'NFSe'] },
    { id: 'sistema', grupo: 'Sistema', titulo: 'Sobre, log e backup', desc: 'Informações do sistema e histórico local.',
      secoes: ['Sobre', 'Possíveis cadastros duplicados', 'Log de atividades', 'Versões de backup', 'Vínculos quebrados'] },
  ];
  const CHAVE = 'sigp_config_pagina';
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const titulo = (el) => [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(' ').trim();
  // A seção vai para a página com o nome mais longo que casa ("Integração Winbox" vai para Winbox, não para "Integração").
  const paginaDaSecao = (t) => {
    const alvo = t.toLowerCase();
    let melhor = null;
    PAGINAS.forEach((p) => p.secoes.forEach((s) => {
      if (alvo.startsWith(s.toLowerCase()) && (!melhor || s.length > melhor.n)) melhor = { p, n: s.length };
    }));
    return melhor ? melhor.p : PAGINAS.find((p) => p.id === 'sistema');
  };

  function montar(box) {
    if (!box || box.querySelector(':scope > .cfg-layout')) return;
    const marca = box.querySelector(':scope > .vg-brand');
    // Cortes: o rótulo inicial "Preferências" e cada section-divider abrem uma seção nova.
    const secoes = [];
    let atual = null;
    [...box.children].forEach((el) => {
      if (el === marca) return;
      const abre = el.classList.contains('section-divider') || (!secoes.length && el.classList.contains('section-label'));
      if (abre) {
        atual = { titulo: titulo(el), hint: el.querySelector('.hint')?.textContent.trim() || '', nos: [] };
        secoes.push(atual);
        el.remove();
        return;
      }
      if (!atual) { atual = { titulo: 'Preferências', hint: '', nos: [] }; secoes.push(atual); }
      atual.nos.push(el);
    });
    const porPagina = new Map(PAGINAS.map((p) => [p.id, []]));
    secoes.forEach((s) => porPagina.get(paginaDaSecao(s.titulo).id).push(s));

    const layout = document.createElement('div');
    layout.className = 'cfg-layout';
    const grupos = [...new Set(PAGINAS.map((p) => p.grupo))];
    layout.innerHTML = `<aside class="cfg-nav" aria-label="Seções das configurações">
        <input type="search" class="cfg-nav-busca" placeholder="Buscar configuração…" aria-label="Buscar configuração">
        ${grupos.map((g) => `<div class="cfg-nav-grupo"><h4>${esc(g)}</h4>${PAGINAS.filter((p) => p.grupo === g && porPagina.get(p.id).length)
          .map((p) => `<button type="button" class="cfg-nav-item" data-cfg-pagina="${p.id}"><span>${esc(p.titulo)}</span><span class="cfg-nav-n" data-cfg-n="${p.id}" hidden></span></button>`).join('')}</div>`).join('')}
      </aside><div class="cfg-conteudo"></div>`;
    const conteudo = layout.querySelector('.cfg-conteudo');
    PAGINAS.forEach((p) => {
      const lista = porPagina.get(p.id);
      if (!lista.length) return;
      const pagina = document.createElement('section');
      pagina.className = 'cfg-pagina';
      pagina.dataset.cfgPagina = p.id;
      pagina.hidden = true;
      const desc = p.desc || (lista.length === 1 ? lista[0].hint : '');
      pagina.innerHTML = `<div class="cfg-pagina-h"><h1>${esc(p.titulo)}</h1>${desc ? `<p>${esc(desc)}</p>` : ''}</div>`;
      lista.forEach((s) => {
        const cartao = document.createElement('section');
        cartao.className = p.nu ? 'cfg-cartao cfg-cartao-nu' : 'cfg-cartao';
        const mostrarCabecalho = !p.nu && (lista.length > 1 || s.titulo !== p.titulo && !/^Dados da Empresa/.test(s.titulo));
        if (mostrarCabecalho) {
          cartao.innerHTML = `<div class="cfg-cartao-h"><h2>${esc(s.titulo)}</h2>${s.hint && lista.length > 1 ? `<span class="hint">${esc(s.hint)}</span>` : ''}</div>`;
        }
        const corpo = document.createElement('div');
        corpo.className = 'cfg-cartao-b';
        s.nos.forEach((n) => corpo.appendChild(n));
        cartao.appendChild(corpo);
        pagina.appendChild(cartao);
      });
      conteudo.appendChild(pagina);
    });
    box.appendChild(layout);
    if (marca) marca.querySelector('h2') && (marca.querySelector('h2').textContent = 'Configurações');

    layout.addEventListener('click', (ev) => {
      const item = ev.target.closest('.cfg-nav-item');
      if (item) ir(item.dataset.cfgPagina);
    });
    layout.querySelector('.cfg-nav-busca').addEventListener('input', (ev) => {
      const q = ev.target.value.trim().toLowerCase();
      layout.querySelectorAll('.cfg-nav-item').forEach((b) => {
        const pagina = layout.querySelector(`.cfg-pagina[data-cfg-pagina="${b.dataset.cfgPagina}"]`);
        b.hidden = Boolean(q) && !`${b.textContent} ${pagina?.textContent || ''}`.toLowerCase().includes(q);
      });
      layout.querySelectorAll('.cfg-nav-grupo').forEach((g) => { g.hidden = ![...g.querySelectorAll('.cfg-nav-item')].some((b) => !b.hidden); });
    });
    const salva = sessionStorage.getItem(CHAVE);
    ir(porPagina.get(salva)?.length ? salva : 'preferencias');
  }

  function ir(id) {
    const layout = document.querySelector('#view_config .cfg-layout');
    if (!layout || !layout.querySelector(`.cfg-pagina[data-cfg-pagina="${id}"]`)) return false;
    layout.querySelectorAll('.cfg-pagina').forEach((p) => { p.hidden = p.dataset.cfgPagina !== id; });
    layout.querySelectorAll('.cfg-nav-item').forEach((b) => {
      const ativo = b.dataset.cfgPagina === id;
      b.classList.toggle('active', ativo);
      if (ativo) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    sessionStorage.setItem(CHAVE, id);
    layout.querySelector('.cfg-conteudo').scrollTop = 0;
    return true;
  }

  // Abre a página que contém o elemento (atalhos e testes: irPara('#cfgQualidade')).
  function irPara(seletor) {
    const el = document.querySelector(`#view_config ${seletor}`) || document.querySelector(seletor);
    const pagina = el?.closest('.cfg-pagina');
    return pagina ? ir(pagina.dataset.cfgPagina) : false;
  }

  // Contagem ou sinal ao lado do item do menu: marcar('qualidade', 126, 'warn'); marcar('integracao', '', 'ok') = ponto verde.
  function marcar(id, texto, tipo = '') {
    const el = document.querySelector(`#view_config [data-cfg-n="${id}"]`);
    if (!el) return;
    const vazio = texto === '' || texto === null || texto === undefined;
    el.textContent = vazio ? '' : String(texto);
    el.className = `cfg-nav-n${tipo ? ` cfg-nav-n-${tipo}` : ''}${vazio ? ' cfg-nav-ponto' : ''}`;
    el.hidden = vazio && !tipo;
  }

  window.SIGP_CONFIG_LAYOUT = { montar, ir, irPara, marcar };
})();
