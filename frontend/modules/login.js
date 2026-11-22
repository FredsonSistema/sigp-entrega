// Login no servidor (backend/sessoes.py). A tela não guarda usuário, senha nem chave da API:
//  - primeiro acesso: cria o administrador (pede a chave do .env uma vez, para provar que é o dono);
//  - entrar: usuário e senha; a API devolve um token de sessão, guardado só nesta aba (sessionStorage);
//  - senha temporária: a pessoa é obrigada a trocar antes de qualquer outra coisa (a API também bloqueia);
//  - links de PDF e XML da API abrem com a sessão (a leitura também exige login).
(() => {
  const TOKEN = 'sigp_sessao';
  // Restos do login antigo (só no navegador): apagados para ninguém entrar com a chave guardada aqui.
  ['sigp_api_key', 'sigp_auth'].forEach((k) => { try { localStorage.removeItem(k); } catch (e) { /* sem acesso */ } });
  try {
    const store = JSON.parse(localStorage.getItem('sigp_integracao_v1') || '{}');
    if (store && store.apiKey) { delete store.apiKey; localStorage.setItem('sigp_integracao_v1', JSON.stringify(store)); }
    sessionStorage.removeItem('sigp_session');
  } catch (e) { /* sem acesso */ }

  const token = () => { try { return sessionStorage.getItem(TOKEN) || ''; } catch (e) { return ''; } };
  const guardar = (t) => { try { if (t) sessionStorage.setItem(TOKEN, t); else sessionStorage.removeItem(TOKEN); } catch (e) { /* sem acesso */ } };
  const base = () => window.SIGP_CONFIG.apiUrl();
  let eu = null;

  async function chamar(caminho, corpo) {
    const r = await fetch(`${base()}${caminho}`, {
      method: corpo === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) { const e = new Error(j.error || `A API respondeu HTTP ${r.status}.`); e.status = r.status; throw e; }
    return j;
  }

  const $ = (id) => document.getElementById(id);
  function mostrar(qual) {
    ['primeiroAdminForm', 'loginForm', 'trocaSenhaForm'].forEach((id) => { const f = $(id); if (f) f.style.display = id === qual ? 'flex' : 'none'; });
    $('authScreen').style.display = qual ? '' : 'none';
    const foco = { primeiroAdminForm: 'pa_chave', loginForm: 'li_user', trocaSenhaForm: 'ts_atual' }[qual];
    if (foco) setTimeout(() => $(foco)?.focus(), 0);
  }
  const erro = (id, texto) => { const el = $(id); if (el) el.textContent = texto || ''; };
  function ocupado(form, sim) { form.querySelectorAll('button, input').forEach((el) => { el.disabled = sim; }); }

  async function iniciar(aoEntrar) {
    ligarFormularios(aoEntrar);
    let estado = { precisaPrimeiroAdmin: false, loginObrigatorio: true };
    try { estado = await chamar('/api/auth/estado'); } catch (e) {
      erro('li_err', 'A API não respondeu. Confira se o sistema está no ar (Configurações > Integração).');
      mostrar('loginForm');
      return;
    }
    if (!estado.loginObrigatorio) { eu = { perfil: 'administrador', nome: 'Administrador', usuario: '' }; mostrar(null); aoEntrar(eu); return; }
    if (estado.precisaPrimeiroAdmin) { mostrar('primeiroAdminForm'); return; }
    if (token()) {
      try {
        eu = await chamar('/api/acesso/eu');
        if (eu.perfil !== 'anonimo') { if (eu.trocarSenha) { trocaObrigatoria(); return; } mostrar(null); aoEntrar(eu); return; }
      } catch (e) { /* sessão vencida: pede login */ }
      guardar('');
    }
    mostrar('loginForm');
  }

  function trocaObrigatoria() {
    $('ts_titulo').textContent = 'Defina a sua senha';
    $('ts_ajuda').textContent = 'Você entrou com a senha temporária. Escolha a sua senha para continuar (pelo menos 8 caracteres, sem o nome de usuário).';
    $('ts_cancelar').hidden = true;
    mostrar('trocaSenhaForm');
  }

  function ligarFormularios(aoEntrar) {
    const pa = $('primeiroAdminForm');
    if (pa && !pa.dataset.ligado) {
      pa.dataset.ligado = '1';
      pa.onsubmit = async (ev) => {
        ev.preventDefault();
        erro('pa_err');
        if ($('pa_user').value.trim().toLowerCase() !== $('pa_user2').value.trim().toLowerCase()) { erro('pa_err', 'Os nomes de usuário não coincidem: confira a digitação (é com ele que você vai entrar).'); return; }
        if ($('pa_senha').value !== $('pa_senha2').value) { erro('pa_err', 'As senhas não coincidem.'); return; }
        ocupado(pa, true);
        try {
          await chamar('/api/auth/primeiro-admin', { chave: $('pa_chave').value.trim(), usuario: $('pa_user').value.trim(),
            nome: $('pa_nome').value.trim(), senha: $('pa_senha').value });
          const r = await chamar('/api/auth/login', { usuario: $('pa_user').value.trim(), senha: $('pa_senha').value });
          guardar(r.token);
          pa.reset();
          eu = await chamar('/api/acesso/eu');
          mostrar(null);
          aoEntrar(eu);
        } catch (e) { erro('pa_err', e.message); } finally { ocupado(pa, false); }
      };
    }
    const li = $('loginForm');
    if (li && !li.dataset.ligado) {
      li.dataset.ligado = '1';
      li.onsubmit = async (ev) => {
        ev.preventDefault();
        erro('li_err');
        ocupado(li, true);
        try {
          const r = await chamar('/api/auth/login', { usuario: $('li_user').value.trim(), senha: $('li_pass').value });
          guardar(r.token);
          $('li_pass').value = '';
          if (r.trocarSenha) { $('ts_atual').value = ''; trocaObrigatoria(); return; }
          eu = await chamar('/api/acesso/eu');
          mostrar(null);
          aoEntrar(eu);
        } catch (e) { erro('li_err', e.message); $('li_pass').select(); } finally { ocupado(li, false); }
      };
    }
    const ts = $('trocaSenhaForm');
    if (ts && !ts.dataset.ligado) {
      ts.dataset.ligado = '1';
      ts.onsubmit = async (ev) => {
        ev.preventDefault();
        erro('ts_err');
        if ($('ts_nova').value !== $('ts_nova2').value) { erro('ts_err', 'As senhas novas não coincidem.'); return; }
        ocupado(ts, true);
        try {
          await chamar('/api/auth/trocar-senha', { senhaAtual: $('ts_atual').value, novaSenha: $('ts_nova').value });
          ts.reset();
          const voluntaria = !$('ts_cancelar').hidden;
          eu = await chamar('/api/acesso/eu');
          mostrar(null);
          if (voluntaria) window.toast?.('Senha alterada.');
          else aoEntrar(eu);
        } catch (e) { erro('ts_err', e.message); } finally { ocupado(ts, false); }
      };
      $('ts_cancelar').onclick = () => { ts.reset(); erro('ts_err'); mostrar(null); };
    }
  }

  // Troca de senha a pedido (botão ⚙): mesma tela, com "Cancelar".
  function trocarSenha() {
    if (!token()) { window.toast?.('Este acesso não usa senha (modo sem login).'); return; }
    $('ts_titulo').textContent = 'Trocar a minha senha';
    $('ts_ajuda').textContent = 'Informe a senha atual e a nova (pelo menos 8 caracteres, sem o nome de usuário). As suas outras sessões são encerradas.';
    $('ts_cancelar').hidden = false;
    mostrar('trocaSenhaForm');
  }

  async function sair() {
    try { if (token()) await chamar('/api/auth/sair', {}); } catch (e) { /* a sessão já pode ter vencido */ }
    guardar('');
    location.reload();
  }

  // Links de arquivo da API (PDF, XML): abre com a sessão, sem expor o token na URL.
  document.addEventListener('click', async (ev) => {
    const a = ev.target.closest && ev.target.closest('a[href]');
    if (!a || !token() || !base() || !a.href.startsWith(`${base()}/api/`)) return;
    ev.preventDefault();
    const baixar = a.hasAttribute('download');
    const janela = baixar ? null : window.open('', '_blank');
    try {
      const r = await fetch(a.href);
      if (!r.ok) throw new Error(`A API respondeu HTTP ${r.status}.`);
      const url = URL.createObjectURL(await r.blob());
      if (baixar) {
        const tmp = document.createElement('a');
        tmp.href = url; tmp.download = a.getAttribute('download') || '';
        document.body.appendChild(tmp); tmp.click(); tmp.remove();
      } else if (janela) janela.location = url; else window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      if (janela) janela.close();
      window.toast?.(`Não foi possível abrir o arquivo: ${e.message}`);
    }
  }, true);

  const usuarioAtual = () => (eu && (eu.usuario || eu.nome)) || '';
  window.SIGP_LOGIN = { iniciar, token, sair, trocarSenha, eu: () => eu, usuarioAtual, limpar: () => guardar('') };
})();
