// Configurações > Alertas por e-mail: quem recebe o resumo diário do WF-06 (um ou mais e-mails).
// Fica no banco (GET/PUT /api/configuracoes/alertas); o n8n lê a lista antes de enviar. Sem lista salva, vale
// SIGP_RELATORIO_EMAIL do .env. Precisa da permissão "config.alertas" (o administrador tem).
(() => {
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const EMAIL = /^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;
  const api = async (opcoes = {}) => {
    const r = await fetch(`${window.SIGP_CONFIG.apiUrl()}/api/configuracoes/alertas`, {
      ...opcoes, headers: { 'Content-Type': 'application/json', ...(opcoes.headers || {}) },
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || `A API respondeu HTTP ${r.status}.`);
    return j;
  };
  let estado = { emails: [], origem: 'nenhum', maximo: 10 };
  let lista = [];

  function origemTexto() {
    if (estado.origem === 'tela') {
      const quando = estado.atualizadoEm ? new Date(estado.atualizadoEm).toLocaleString('pt-BR') : '';
      return `Salvo nesta tela${estado.atualizadoPor ? ` por ${esc(estado.atualizadoPor)}` : ''}${quando ? ` em ${quando}` : ''}.`;
    }
    if (estado.origem === '.env') return 'Usando o padrão da instalação (SIGP_RELATORIO_EMAIL no .env). Ao salvar aqui, esta lista passa a valer.';
    return 'Nenhum e-mail configurado: o resumo é gravado no SIG, mas não é enviado.';
  }

  function desenhar(box, mensagem = '') {
    const pode = !window.SIGP_ACESSO || window.SIGP_ACESSO.perfil === 'administrador'
      || (window.SIGP_ACESSO.permissoes || []).includes('config.alertas');
    if (!pode) {
      box.innerHTML = '<div class="hint">Seu perfil não pode ver nem alterar os e-mails dos alertas. Fale com o administrador.</div>';
      return;
    }
    box.innerHTML = `
      <div class="hint" style="margin-bottom:6px">Recebem o resumo diário das contas (vencidas, que vencem hoje e nos próximos 5 dias), às 08:00, com o texto escrito pela IA local e conferido pelo sistema.</div>
      <ul class="cfg-alertas-lista" aria-label="E-mails que recebem os alertas">
        ${lista.length ? lista.map((e, i) => `<li><span>${esc(e)}</span> <button type="button" class="ghost small" data-alerta-remover="${i}" aria-label="Remover ${esc(e)}">✕</button></li>`).join('')
          : '<li class="hint">Nenhum e-mail na lista.</li>'}
      </ul>
      <div class="task-add-row">
        <label for="cfgAlertaNovo" class="sr-only">Novo e-mail</label>
        <input class="f" type="email" id="cfgAlertaNovo" placeholder="nome@empresa.com.br" autocomplete="off" style="flex:1; max-width:340px">
        <button type="button" class="ghost small" data-alerta-adicionar>+ Adicionar</button>
      </div>
      <div class="task-add-row" style="margin-top:6px">
        <button type="button" class="primary small" data-alerta-salvar>Salvar e-mails dos alertas</button>
        <span class="hint" data-alerta-status role="status" aria-live="polite">${esc(mensagem)}</span>
      </div>
      <div class="hint" data-alerta-origem>${origemTexto()} Até ${estado.maximo} e-mails.</div>`;
  }

  function adicionar(box) {
    const campo = box.querySelector('#cfgAlertaNovo');
    const novos = campo.value.split(/[,;\s]+/).map((e) => e.trim().toLowerCase()).filter(Boolean);
    const ruim = novos.find((e) => !EMAIL.test(e));
    if (ruim) { box.querySelector('[data-alerta-status]').textContent = `E-mail inválido: ${ruim}`; return; }
    novos.forEach((e) => { if (!lista.includes(e)) lista.push(e); });
    if (lista.length > estado.maximo) {
      lista = lista.slice(0, estado.maximo);
      desenhar(box, `Use no máximo ${estado.maximo} e-mails.`);
      return;
    }
    desenhar(box, novos.length ? 'Adicionado. Clique em "Salvar" para valer.' : '');
    box.querySelector('#cfgAlertaNovo').focus();
  }

  async function render(alvo) {
    const box = typeof alvo === 'string' ? document.getElementById(alvo) : alvo;
    if (!box) return;
    try {
      estado = await api();
      lista = [...estado.emails];
      desenhar(box);
    } catch (e) {
      box.innerHTML = `<div class="hint">Não foi possível ler os e-mails dos alertas: ${esc(e.message)}</div>`;
    }
    if (box.dataset.ligado) return;
    box.dataset.ligado = '1';
    box.addEventListener('click', async (ev) => {
      const remover = ev.target.closest('[data-alerta-remover]');
      if (remover) {
        lista.splice(Number(remover.dataset.alertaRemover), 1);
        desenhar(box, 'Removido. Clique em "Salvar" para valer.');
        return;
      }
      if (ev.target.closest('[data-alerta-adicionar]')) { adicionar(box); return; }
      if (ev.target.closest('[data-alerta-salvar]')) {
        const pendente = box.querySelector('#cfgAlertaNovo').value.trim();
        if (pendente) { adicionar(box); if (box.querySelector('#cfgAlertaNovo').value.trim()) return; }
        const status = box.querySelector('[data-alerta-status]');
        status.textContent = 'Salvando…';
        try {
          estado = await api({ method: 'PUT', body: JSON.stringify({ emails: lista }) });
          lista = [...estado.emails];
          desenhar(box, lista.length ? `Salvo. ${lista.length} e-mail(s) recebem o próximo resumo.` : 'Salvo. Nenhum e-mail: o resumo não será enviado.');
        } catch (e) {
          status.textContent = e.message;
        }
      }
    });
    box.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && ev.target.id === 'cfgAlertaNovo') { ev.preventDefault(); adicionar(box); }
    });
  }

  window.SIGP_CONFIG_ALERTAS = { render };
})();
