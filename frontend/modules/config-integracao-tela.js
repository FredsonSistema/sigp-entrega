// Configurações > API e n8n (#cfgIntegracao) e Servidor e serviços (#cfgServidor): cartões com os campos e balões de
// ajuda (o que é, para que serve, como configurar, onde achar). Grava em window.SIGP_CONFIG; o estado do servidor vem de
// GET /api/integracao/estado.
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  let seq = 0;

  function balao(ajuda) {
    const id = `cfg-balao-${++seq}`;
    return `<button type="button" class="cfg-help" aria-expanded="false" aria-controls="${id}" aria-label="Ajuda" data-cfg-help>?</button>
      <div class="cfg-balao" id="${id}" role="note" hidden>
        <div><b>O que é:</b> ${esc(ajuda.oque)}</div>
        <div><b>Para que serve:</b> ${esc(ajuda.para)}</div>
        <div><b>Como configurar:</b> ${esc(ajuda.como)}</div>
        <div><b>Onde achar:</b> ${esc(ajuda.onde)}</div>
      </div>`;
  }

  const ORIGEM = { tela: 'configurado nesta tela', instalacao: 'padrão da instalação (.env)', vazio: 'não configurado' };

  const WORKFLOW = { webhookNotaLancada: 'WF-01', webhookNotaPaga: 'WF-02', webhookEventos: 'WF-05' };

  function campo(nome, classe = '') {
    const c = window.SIGP_CONFIG.CAMPOS[nome];
    const valor = window.SIGP_CONFIG.get(nome);
    const origem = window.SIGP_CONFIG.origem(nome);
    let entrada;
    if (c.tipo === 'opcoes') {
      entrada = `<select class="f" data-cfg="${nome}">${c.opcoes.map(([v, r]) => `<option value="${esc(v)}"${v === valor ? ' selected' : ''}>${esc(r)}</option>`).join('')}</select>`;
    } else {
      const tipo = c.tipo === 'segredo' ? 'password' : 'text';
      entrada = `<div class="cfg-linha"><input class="f mono-in" type="${tipo}" data-cfg="${nome}" value="${esc(valor)}" autocomplete="off" placeholder="${esc(c.padrao() || '')}">
        ${c.tipo === 'segredo' ? '<button type="button" class="ghost small" data-cfg-mostrar title="Mostrar/ocultar">👁</button>' : ''}</div>`;
    }
    const rotulo = c.tipo === 'webhook' ? c.rotulo.replace(/^Webhook:\s*/, '').replace(/^./, (l) => l.toUpperCase()) : c.rotulo;
    return `<div class="cfg-campo${classe ? ` ${classe}` : ''}">
      <div class="cfg-rotulo"><label>${esc(rotulo)}${WORKFLOW[nome] ? ` <span class="hint">${WORKFLOW[nome]}</span>` : ''}</label>${balao(c.ajuda)}</div>
      ${entrada}
      <div class="cfg-dica" data-cfg-origem="${nome}">${esc(ORIGEM[origem])}${c.tipo === 'webhook' && window.SIGP_CONFIG.webhookUrl(nome) ? ` · ${esc(window.SIGP_CONFIG.webhookUrl(nome))}` : ''}</div>
    </div>`;
  }

  // Variáveis do servidor e do n8n: só leitura (ficam no .env; segredos nunca aparecem aqui).
  const SERVIDOR = [
    ['SIGP_API_KEY', 'Chave exigida pela API em toda gravação.', 'Proteger a API: sem ela, qualquer programa da rede grava dados.', 'Gere um texto aleatório longo e coloque em SIGP_API_KEY=. Use o mesmo valor aqui na tela (grupo 1).', 'Arquivo .env na pasta do sistema.'],
    ['SIGP_CORS_ORIGINS', 'Endereços de tela que podem chamar a API.', 'O navegador só deixa esta tela falar com a API se o endereço dela estiver na lista.', 'Endereço desta tela (ex.: http://127.0.0.1:8000); vários, separados por vírgula.', 'Arquivo .env, linha SIGP_CORS_ORIGINS=.'],
    ['SIGP_N8N_EVENTOS_URL', 'Webhook do n8n que recebe os eventos da API (conciliação, decisão do gerente).', 'A API avisa o n8n sozinha; eventos que falham ficam na fila e são reenviados.', 'URL completa do webhook do WF-05, vista pelo container da API: http://n8n:5678/webhook/sigp-eventos.', 'Arquivo .env; no n8n, workflow WF-05, nó Webhook.'],
    ['SIGP_N8N_TOKEN', 'Token que a API envia ao n8n (cabeçalho Authorization: Bearer).', 'Garante que o webhook do n8n só aceite eventos da API.', 'O mesmo texto na credencial "Header Auth" do webhook WF-05 no n8n.', 'Arquivo .env; no n8n, Credentials.'],
    ['SIGP_EXIGIR_FATURA', 'Regra da conciliação: exigir a fatura PDF para fechar o ciclo (MATCH).', 'Com 1, só fecha com nota lançada + nota paga + fatura conferida.', '1 (recomendado) ou 0.', 'Arquivo .env.'],
    ['SIGP_PDF_SENHA_CNPJS', 'Raízes de CNPJ das empresas do grupo, usadas para abrir PDFs com senha (Brisanet, Claro...).', 'O OCR testa o começo do CNPJ como senha; a senha nunca é gravada.', 'Os 8 primeiros dígitos de cada CNPJ, separados por vírgula.', 'Arquivo .env (serviço OCR).'],
    ['SIGP_PUBLIC_API_URL', 'Endereço padrão da API para esta tela (quando o usuário não configurou nada).', 'Uma instalação nova já abre funcionando.', 'Igual ao endereço da API do grupo 1.', 'Arquivo .env (serviço web).'],
    ['SIGP_PUBLIC_N8N_URL', 'Endereço padrão do n8n para esta tela.', 'Uma instalação nova já abre funcionando.', 'Igual ao endereço do n8n do grupo 2.', 'Arquivo .env (serviço web).'],
  ];
  const N8N = [
    ['SIGP_API_URL', 'Endereço da API visto de dentro do n8n.', 'Todos os workflows chamam a API por ele ({{$env.SIGP_API_URL}}).', 'Na rede Docker: http://api:5001. Se o sistema for trocado, aponte para a API do sistema novo.', 'docker-compose.yml, serviço n8n, "environment".'],
    ['SIGP_API_KEY (no n8n)', 'A chave da API usada pelos workflows.', 'Os workflows gravam na API com ela.', 'Mesmo valor de SIGP_API_KEY (vem do .env).', 'docker-compose.yml, serviço n8n.'],
    ['SIGP_OLLAMA_URL / SIGP_OLLAMA_MODEL', 'Endereço e modelo da IA local (Ollama).', 'Classificação dos e-mails, análises e resumos.', 'Padrão: http://ollama:11434 e qwen2.5:3b.', 'docker-compose.yml e .env.'],
    ['Conta do Gmail', 'A caixa de e-mail que o WF-08 lê e etiqueta.', 'É de onde chegam as faturas e avisos dos provedores.', 'No n8n: Credentials > Gmail account (OAuth do Google); depois ative o WF-08.', 'Editor do n8n, menu Credentials.'],
    ['Notificações', 'E-mail do relatório, Telegram e WhatsApp.', 'Enviar alertas e resumos para fora do sistema.', 'SIGP_RELATORIO_EMAIL, SIGP_TELEGRAM_CHAT_ID, SIGP_WHATSAPP_URL/NUMERO/APIKEY; credenciais no n8n.', 'Arquivo .env e Credentials do n8n.'],
  ];

  const CURTO_N8N = { 'SIGP_API_URL': 'docker-compose', 'SIGP_API_KEY (no n8n)': 'vem do .env', 'Conta do Gmail': 'Credentials no n8n', 'Notificações': '.env + n8n' };

  // Linha "nome · para que serve · estado" com o balão de ajuda abrindo por baixo da linha inteira.
  function linhaKv([nome, oque, para, como, onde], direita) {
    return `<div class="cfg-kv-linha"><code>${esc(nome)}</code><span class="cfg-kv-d">${esc(oque)}</span>
      <span class="cfg-kv-e">${direita || ''}${balao({ oque, para, como, onde })}</span></div>`;
  }

  function estadoServidor(nome, s) {
    if (!s) return null;
    const v = (s.variaveis || {})[nome];
    if (!v) return null;
    if (v.segredo) return { ok: v.definida, texto: v.definida ? 'definida' : 'não definida' };
    return { ok: v.definida, texto: v.definida ? (v.valor || 'definida') : 'não definida' };
  }
  const pilula = (e) => (e ? `<span class="cfg-pill ${e.ok ? 'cfg-pill-ok' : 'cfg-pill-bad'}" title="${esc(e.texto)}">${esc(e.texto)}</span>` : '');

  function cartaoStatus(rotulo, ok, texto, detalhe = '', attr = '') {
    const cls = ok === null ? 'cfg-st-espera' : ok ? 'cfg-st-ok' : 'cfg-st-bad';
    return `<div class="cfg-st ${cls}"${attr}><span>${esc(rotulo)}</span><b><i></i>${esc(texto)}${detalhe ? ` <small>${esc(detalhe)}</small>` : ''}</b></div>`;
  }

  function desenharServidor(srv, estado) {
    if (!srv) return;
    const ollama = estado?.ollama?.modeloConfigurado;
    srv.innerHTML = `
      <section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Arquivo .env</h2>
        <span class="hint">${estado ? 'mudou o .env? rode <code>docker compose up -d</code> na pasta do sistema' : 'API sem resposta: estado desconhecido'}</span></div>
        <div class="cfg-cartao-b cfg-kv">${SERVIDOR.map((l) => linhaKv(l, pilula(estadoServidor(l[0], estado)))).join('')}</div></section>
      <section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Variáveis do n8n e e-mail</h2><span class="hint">configuradas no n8n e no docker-compose</span></div>
        <div class="cfg-cartao-b cfg-kv">${N8N.map((l) => linhaKv(l, `<span class="hint">${esc(l[0].startsWith('SIGP_OLLAMA') && ollama ? ollama : (CURTO_N8N[l[0]] || 'docker-compose'))}</span>`)).join('')}</div></section>`;
    ligarAjuda(srv);
  }

  async function render(alvo) {
    const box = typeof alvo === 'string' ? document.getElementById(alvo) : alvo;
    if (!box) return;
    let estado = null;
    try {
      const r = await fetch(`${window.SIGP_CONFIG.apiUrl()}/api/integracao/estado`);
      if (r.ok) estado = await r.json();
    } catch (e) { estado = null; }
    const doGrupo = (g) => Object.keys(window.SIGP_CONFIG.CAMPOS).filter((n) => window.SIGP_CONFIG.CAMPOS[n].grupo === g);
    const webhooks = doGrupo('n8n').filter((n) => window.SIGP_CONFIG.CAMPOS[n].tipo === 'webhook');
    const enderecos = [...doGrupo('api'), ...doGrupo('n8n').filter((n) => !webhooks.includes(n))];
    // O cartão do webhook de contas (campos, fila e log, em agencias.html) é preservado entre um desenho e outro.
    const contas = document.getElementById('cfgContasHolder');
    if (contas) contas.remove();
    const ocr = estado?.ocr;
    const ia = estado?.ollama;
    box.innerHTML = `
      <div class="cfg-status-row" aria-label="Estado dos serviços">
        ${cartaoStatus('API', Boolean(estado), estado ? 'Online' : 'Sem resposta', estado ? '' : 'confira o endereço')}
        ${cartaoStatus('n8n', null, 'Verificando…', '', ' data-cfg-st="n8n"')}
        ${cartaoStatus('IA local', estado ? Boolean(ia?.disponivel) : false, ia?.disponivel ? 'No ar' : 'Sem resposta', ia?.modeloConfigurado || '')}
        ${cartaoStatus('OCR', estado ? Boolean(ocr?.ok) : false, ocr?.ok ? 'No ar' : 'Sem resposta', ocr?.ok ? `${ocr.regrasSenha ?? 0} regra(s) de senha` : '')}
      </div>
      <section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Endereços</h2><span class="hint">onde ficam os dados (API) e o orquestrador (n8n)</span></div>
        <div class="cfg-cartao-b cfg-grid">${enderecos.map((n, i) => campo(n, i >= 2 ? 'full' : '')).join('')}</div>
        <div class="cfg-cartao-f"><span class="hint cfg-f-esq" data-cfg-resultado="api"></span><span class="hint" data-cfg-resultado="n8n"></span>
          <button type="button" class="ghost small" data-cfg-testar="api">🔌 Testar API</button>
          <button type="button" class="ghost small" data-cfg-testar="n8n">🔌 Testar n8n</button></div></section>
      <section class="cfg-cartao"><div class="cfg-cartao-h"><h2>Webhooks do n8n</h2><span class="hint">só o caminho; a tela junta com o endereço do n8n</span></div>
        <div class="cfg-cartao-b cfg-grid">${webhooks.map((n, i) => campo(n, i === webhooks.length - 1 && webhooks.length % 2 ? 'full' : '')).join('')}</div>
        <div class="cfg-cartao-f"><span class="hint cfg-f-esq" data-cfg-status role="status" aria-live="polite">Salvar grava os endereços e os webhooks.</span>
          <button class="ghost small" type="button" data-cfg-restaurar>Usar padrões da instalação</button>
          <button class="primary small" type="button" data-cfg-salvar>Salvar integração</button></div></section>
      <section class="cfg-cartao" id="cfgGrupoContas"></section>
      ${estado?.eventos?.texto ? `<div class="hint">Eventos da API para o n8n: ${esc(estado.eventos.texto)}</div>` : ''}`;
    if (contas) {
      contas.hidden = false;
      box.querySelector('#cfgGrupoContas').appendChild(contas);
    }
    desenharServidor(document.getElementById('cfgServidor'), estado);
    window.SIGP_CONFIG_LAYOUT?.marcar('integracao', '', estado ? 'ok' : 'bad');
    ligar(box);
    verificarN8n(box);
  }

  // O n8n não libera CORS para esta tela: "no-cors" só confirma que o endereço responde.
  async function verificarN8n(box) {
    const alvo = box.querySelector('[data-cfg-st="n8n"]');
    const url = String(window.SIGP_CONFIG.get('n8nUrl') || '').trim().replace(/\/+$/, '');
    if (!alvo) return;
    let ok = false;
    if (url) {
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), 4000);
      try { await fetch(`${url}/healthz`, { mode: 'no-cors', signal: ctl.signal }); ok = true; } catch (e) { ok = false; }
      clearTimeout(t);
    }
    alvo.outerHTML = cartaoStatus('n8n', ok, ok ? 'Online' : 'Sem resposta', url ? '' : 'sem endereço', ' data-cfg-st="n8n"');
  }

  function fecharBaloes(box, exceto) {
    box.querySelectorAll('[data-cfg-help][aria-expanded="true"]').forEach((b) => {
      if (b === exceto) return;
      b.setAttribute('aria-expanded', 'false');
      document.getElementById(b.getAttribute('aria-controls')).hidden = true;
    });
  }

  function ligarAjuda(box) {
    if (box.dataset.ajudaLigada) return;
    box.dataset.ajudaLigada = '1';
    box.addEventListener('click', (ev) => {
      const help = ev.target.closest('[data-cfg-help]');
      if (!help) return;
      const aberto = help.getAttribute('aria-expanded') === 'true';
      fecharBaloes(box, help);
      help.setAttribute('aria-expanded', String(!aberto));
      document.getElementById(help.getAttribute('aria-controls')).hidden = aberto;
    });
    box.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') fecharBaloes(box); });
  }

  function ligar(box) {
    ligarAjuda(box);
    if (box.dataset.ligado) return;
    box.dataset.ligado = '1';
    box.addEventListener('click', async (ev) => {
      if (ev.target.closest('[data-cfg-help]')) return;
      if (ev.target.closest('[data-cfg-mostrar]')) {
        const inp = ev.target.closest('.cfg-linha').querySelector('input');
        inp.type = inp.type === 'password' ? 'text' : 'password';
        return;
      }
      if (ev.target.closest('[data-cfg-salvar]')) {
        const valores = {};
        box.querySelectorAll('[data-cfg]').forEach((el) => { valores[el.dataset.cfg] = el.value; });
        const ruim = ['apiUrl', 'n8nUrl'].find((n) => valores[n] && !/^https?:\/\/[^\s]+$/i.test(valores[n].trim()));
        if (ruim) {
          box.querySelector('[data-cfg-status]').textContent = `Endereço inválido em "${window.SIGP_CONFIG.CAMPOS[ruim].rotulo}": use http://... ou https://...`;
          return;
        }
        window.SIGP_CONFIG.set(valores);
        await render(box);
        box.querySelector('[data-cfg-status]').textContent = 'Integração salva. As próximas chamadas já usam os novos valores.';
        window.dispatchEvent(new CustomEvent('sigp:integracao-atualizada'));
        return;
      }
      if (ev.target.closest('[data-cfg-restaurar]')) {
        window.SIGP_CONFIG.restaurarPadroes();
        await render(box);
        box.querySelector('[data-cfg-status]').textContent = 'Usando os padrões da instalação (.env).';
        window.dispatchEvent(new CustomEvent('sigp:integracao-atualizada'));
        return;
      }
      const testar = ev.target.closest('[data-cfg-testar]');
      if (testar) {
        const saida = box.querySelector(`[data-cfg-resultado="${testar.dataset.cfgTestar}"]`);
        const url = (box.querySelector(`[data-cfg="${testar.dataset.cfgTestar === 'api' ? 'apiUrl' : 'n8nUrl'}"]`)?.value || '').trim().replace(/\/+$/, '');
        saida.textContent = 'Testando…';
        saida.textContent = await (testar.dataset.cfgTestar === 'api' ? testarApi(url) : testarN8n(url));
      }
    });
  }

  async function testarApi(url) {
    if (!url) return 'Informe o endereço da API.';
    try {
      const r = await fetch(`${url}/api/health`);
      return r.ok ? `✅ API respondeu (${url}).` : `❌ A API respondeu HTTP ${r.status}.`;
    } catch (e) {
      return '❌ Sem resposta. Confira o endereço, se o container da API está no ar e se SIGP_CORS_ORIGINS inclui o endereço desta tela.';
    }
  }

  async function testarN8n(url) {
    if (!url) return 'Informe o endereço do n8n.';
    try {
      // O n8n não libera CORS para esta tela: "no-cors" só confirma que o endereço responde.
      await fetch(`${url}/healthz`, { mode: 'no-cors' });
      return `✅ O n8n respondeu (${url}). Confira se os workflows dos webhooks estão ativos.`;
    } catch (e) {
      return '❌ Sem resposta. Confira o endereço e se o container sigp_n8n está no ar.';
    }
  }

  window.SIGP_CONFIG_TELA = { render };
})();
