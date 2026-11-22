// Configurações > E-mail das faturas: remetentes que o WF-08 procura no Gmail (domínios dos provedores e e-mails extras,
// como o de teste de um colaborador). Fica no banco (GET/PUT /api/configuracoes/email-faturas); o n8n pede a busca pronta
// antes de cada leitura, então trocar aqui vale na próxima leitura (até 5 min), sem abrir o n8n.
// Precisa da permissão "config.email_faturas" (o administrador tem).
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const ROTULO = '[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?';
  const REMETENTE = new RegExp(`^(?:[a-z0-9._+-]{1,64}@)?(?:${ROTULO}\\.)+[a-z]{2,24}$`);
  const valido = (v) => v.length <= 254 && !v.includes('..') && REMETENTE.test(v);
  const api = async (opcoes = {}) => {
    const r = await fetch(`${window.SIGP_CONFIG.apiUrl()}/api/configuracoes/email-faturas`, {
      ...opcoes, headers: { 'Content-Type': 'application/json', ...(opcoes.headers || {}) },
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || `A API respondeu HTTP ${r.status}.`);
    return j;
  };
  let estado = { remetentes: [], padrao: [], origem: 'padrão', maximo: 60 };
  let lista = [];

  function origemTexto() {
    if (estado.origem === 'tela') {
      const quando = estado.atualizadoEm ? new Date(estado.atualizadoEm).toLocaleString('pt-BR') : '';
      return `Salvo nesta tela${estado.atualizadoPor ? ` por ${esc(estado.atualizadoPor)}` : ''}${quando ? ` em ${quando}` : ''}.`;
    }
    return 'Usando a lista padrão (domínios dos provedores). Ao salvar aqui, esta lista passa a valer.';
  }

  const INSTRUCOES = `
    <details class="cfg-ef-ajuda" data-ef-ajuda>
      <summary><b>Trocou o responsável pelas faturas?</b> Passo a passo para o novo colaborador</summary>
      <ol>
        <li><b>Nesta tela:</b> remova o e-mail de teste de quem saiu (marcado como <i>extra</i>), adicione o seu, se for enviar testes, e clique em <b>Salvar remetentes</b>. Vale na próxima leitura do Gmail, em até 5 minutos.</li>
        <li><b>Alertas por e-mail</b> (menu Geral, ao lado): troque quem recebe o resumo diário e salve.</li>
        <li><b>No e-mail corporativo:</b> crie a regra de encaminhamento das faturas para o Gmail que o sistema lê, igual à do colaborador anterior. Quem saiu deve apagar a regra dele.</li>
        <li><b>Se o Gmail lido pelo sistema também mudar</b> (a caixa era pessoal de quem saiu): a nova conta precisa ser conectada uma vez, com login no Google e o clique em "Permitir". Por enquanto, peça ao administrador do servidor para reconectar a credencial "Gmail account" no n8n. O passo a passo guiado nesta tela está sendo preparado.</li>
      </ol>
      <div class="hint">Nada aqui precisa de senha ou chave: os remetentes ficam no banco do SIGp, nunca no código. Domínio (<i>provedor.com.br</i>) aceita qualquer endereço do provedor; e-mail aceita só aquele endereço.</div>
    </details>`;

  function desenhar(box, mensagem = '') {
    const pode = !window.SIGP_ACESSO || window.SIGP_ACESSO.perfil === 'administrador'
      || (window.SIGP_ACESSO.permissoes || []).includes('config.email_faturas');
    if (!pode) {
      box.innerHTML = '<div class="hint">Seu perfil não pode ver nem alterar os remetentes das faturas. Fale com o administrador.</div>';
      return;
    }
    const padrao = new Set(estado.padrao || []);
    const aberto = box.querySelector('[data-ef-ajuda]')?.open ? ' open' : '';
    box.innerHTML = `
      <div class="hint" style="margin-bottom:6px">O sistema lê no Gmail, a cada 5 minutos, as mensagens destes remetentes e as que têm assunto ou anexo de fatura, boleto ou nota fiscal.</div>
      <ul class="cfg-alertas-lista" aria-label="Remetentes procurados no Gmail">
        ${lista.length ? lista.map((e, i) => `<li><span>${esc(e)}</span>${padrao.has(e) ? '' : ' <span class="hint">extra</span>'} <button type="button" class="ghost small" data-ef-remover="${i}" aria-label="Remover ${esc(e)}">✕</button></li>`).join('')
          : '<li class="hint">Nenhum remetente: só entram mensagens com assunto ou anexo de cobrança.</li>'}
      </ul>
      <div class="task-add-row">
        <label for="cfgEfNovo" class="sr-only">Novo remetente (e-mail ou domínio)</label>
        <input class="f" type="text" id="cfgEfNovo" placeholder="provedor.com.br ou nome@empresa.com.br" autocomplete="off" style="flex:1; max-width:340px">
        <button type="button" class="ghost small" data-ef-adicionar>+ Adicionar</button>
      </div>
      <div class="task-add-row" style="margin-top:6px">
        <button type="button" class="primary small" data-ef-salvar>Salvar remetentes</button>
        <button type="button" class="ghost small" data-ef-padrao title="Volta para os domínios dos provedores (sem os extras). Clique em Salvar para valer.">Voltar ao padrão</button>
        <span class="hint" data-ef-status role="status" aria-live="polite">${esc(mensagem)}</span>
      </div>
      <div class="hint" data-ef-origem>${origemTexto()} Até ${estado.maximo} remetentes.</div>
      ${INSTRUCOES.replace('<details class="cfg-ef-ajuda" data-ef-ajuda>', `<details class="cfg-ef-ajuda" data-ef-ajuda${aberto}>`)}`;
  }

  function adicionar(box) {
    const campo = box.querySelector('#cfgEfNovo');
    const novos = campo.value.split(/[,;\s]+/).map((e) => e.trim().toLowerCase().replace(/^@/, '')).filter(Boolean);
    const ruim = novos.find((e) => !valido(e));
    if (ruim) { box.querySelector('[data-ef-status]').textContent = `Remetente inválido (use um e-mail ou um domínio): ${ruim}`; return; }
    novos.forEach((e) => { if (!lista.includes(e)) lista.push(e); });
    if (lista.length > estado.maximo) {
      lista = lista.slice(0, estado.maximo);
      desenhar(box, `Use no máximo ${estado.maximo} remetentes.`);
      return;
    }
    desenhar(box, novos.length ? 'Adicionado. Clique em "Salvar remetentes" para valer.' : '');
    box.querySelector('#cfgEfNovo').focus();
  }

  async function render(alvo) {
    const box = typeof alvo === 'string' ? document.getElementById(alvo) : alvo;
    if (!box) return;
    try {
      estado = await api();
      lista = [...estado.remetentes];
      desenhar(box);
    } catch (e) {
      box.innerHTML = `<div class="hint">Não foi possível ler os remetentes das faturas: ${esc(e.message)}</div>`;
    }
    if (box.dataset.ligado) return;
    box.dataset.ligado = '1';
    box.addEventListener('click', async (ev) => {
      const remover = ev.target.closest('[data-ef-remover]');
      if (remover) {
        lista.splice(Number(remover.dataset.efRemover), 1);
        desenhar(box, 'Removido. Clique em "Salvar remetentes" para valer.');
        return;
      }
      if (ev.target.closest('[data-ef-adicionar]')) { adicionar(box); return; }
      if (ev.target.closest('[data-ef-padrao]')) {
        lista = [...(estado.padrao || [])];
        desenhar(box, 'Lista padrão carregada. Clique em "Salvar remetentes" para valer.');
        return;
      }
      if (ev.target.closest('[data-ef-salvar]')) {
        const pendente = box.querySelector('#cfgEfNovo').value.trim();
        if (pendente) { adicionar(box); if (box.querySelector('#cfgEfNovo').value.trim()) return; }
        const status = box.querySelector('[data-ef-status]');
        status.textContent = 'Salvando…';
        try {
          estado = await api({ method: 'PUT', body: JSON.stringify({ remetentes: lista }) });
          lista = [...estado.remetentes];
          desenhar(box, `Salvo. A próxima leitura do Gmail (em até 5 minutos) usa ${lista.length} remetente(s).`);
        } catch (e) {
          status.textContent = e.message;
        }
      }
    });
    box.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && ev.target.id === 'cfgEfNovo') { ev.preventDefault(); adicionar(box); }
    });
  }

  window.SIGP_CONFIG_EMAIL_FATURAS = { render };
})();
