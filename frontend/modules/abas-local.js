// Formulário do local (agência, rodoviária, garagem) em abas: Geral · Responsáveis · Rede e links · Notas fiscais.
// Só muda a apresentação: os campos, os ids e a gravação (botão Salvar) continuam os mesmos. Campo obrigatório
// vazio numa aba escondida abre essa aba antes do aviso do navegador.
(() => {
  const ligados = new WeakSet();

  function mostrar(overlay, aba) {
    if (!overlay) return;
    overlay.querySelectorAll('[data-loc-tab]').forEach((t) => {
      const ativa = t.dataset.locTab === aba;
      t.classList.toggle('active', ativa);
      t.setAttribute('aria-selected', String(ativa));
      t.tabIndex = ativa ? 0 : -1;
    });
    overlay.querySelectorAll('[data-loc-painel]').forEach((p) => {
      const ativa = p.dataset.locPainel === aba;
      p.classList.toggle('active', ativa);
      p.hidden = !ativa;
    });
    const conteudo = overlay.querySelector('.loc-conteudo');
    if (conteudo) conteudo.scrollTop = 0;
  }

  // Quantidade em cada aba: responsáveis e provedores preenchidos, notas fiscais do local.
  function contar(overlay) {
    if (!overlay) return;
    const preenchidas = (lista) => [...(lista?.querySelectorAll(':scope > .dyn-row') || [])]
      .filter((linha) => [...linha.querySelectorAll('input.f')].some((i) => i.value.trim())).length;
    overlay.querySelectorAll('[data-loc-count]').forEach((selo) => {
      const alvo = overlay.querySelector(`[id$="${selo.dataset.locCount}"]`);
      const n = selo.dataset.locCount.endsWith('notasFiscaisList')
        ? (alvo?.querySelectorAll('.nf-local-row').length || 0)
        : preenchidas(alvo);
      selo.textContent = String(n);
      selo.classList.toggle('alerta', n === 0 && selo.dataset.locAlerta === '1');
    });
    const nome = overlay.querySelector('input[id$="f_nome"]')?.value.trim() || '';
    const titulo = overlay.querySelector('[data-loc-nome]');
    if (titulo) titulo.textContent = nome;
  }

  function ligar(overlay) {
    if (!overlay || ligados.has(overlay)) return;
    ligados.add(overlay);
    overlay.addEventListener('click', (ev) => {
      const aba = ev.target.closest('[data-loc-tab]');
      if (aba) { mostrar(overlay, aba.dataset.locTab); return; }
      if (ev.target.closest('[data-loc-fechar]')) overlay.querySelector('[id$="btnCancel"]')?.click();
    });
    overlay.addEventListener('keydown', (ev) => {
      const aba = ev.target.closest?.('[data-loc-tab]');
      if (!aba || !['ArrowLeft', 'ArrowRight'].includes(ev.key)) return;
      const todas = [...overlay.querySelectorAll('[data-loc-tab]')];
      const prox = todas[(todas.indexOf(aba) + (ev.key === 'ArrowRight' ? 1 : -1) + todas.length) % todas.length];
      mostrar(overlay, prox.dataset.locTab);
      prox.focus();
    });
    // Campo obrigatório numa aba escondida: abre a aba dele (senão o navegador não consegue mostrar o aviso).
    overlay.addEventListener('invalid', (ev) => {
      const painel = ev.target.closest?.('[data-loc-painel]');
      if (painel && !painel.classList.contains('active')) mostrar(overlay, painel.dataset.locPainel);
    }, true);
    let timer = null;
    const recontar = () => { clearTimeout(timer); timer = setTimeout(() => contar(overlay), 150); };
    overlay.addEventListener('input', recontar);
    overlay.addEventListener('click', recontar);
  }

  // Chamado ao abrir o formulário: começa em "Geral" (ou na aba pedida) e atualiza as quantidades.
  function abrir(overlay, aba = 'geral') {
    if (!overlay) return;
    ligar(overlay);
    mostrar(overlay, aba);
    contar(overlay);
    setTimeout(() => contar(overlay), 300); // listas preenchidas depois (notas fiscais)
  }

  window.SIGP_ABAS_LOCAL = { abrir, mostrar, contar };
})();
