// Configuração de integração da tela (fonte única). Nenhum endereço fica no código:
//   1) o que o usuário salvou em Configurações > Integração (este navegador);
//   2) os padrões da instalação (arquivo .env -> nginx -> /sigp-env.js -> window.SIGP_ENV);
//   3) vazio: a tela avisa que falta configurar.
// As chaves antigas do navegador (sigp_nfse_backend_url...) continuam sendo lidas e são migradas
// ao salvar. Segredos do servidor (chave da API, token do n8n) ficam só no .env: a tela entra com usuário e senha.
(() => {
  const STORE = 'sigp_integracao_v1';
  const env = () => window.SIGP_ENV || {};
  const LEGADO = {
    apiUrl: 'sigp_nfse_backend_url', n8nUrl: 'sigp_n8n_base_url', modoEntrada: 'sigp_modo_entrada',
    webhookNotas: 'sigp_nfse_webhook_url', webhookFaturaPdf: 'sigp_fatura_pdf_webhook_url',
  };
  const LEGADO_CONTAS = 'sigp_webhook_config_v1';

  // Catálogo: cada variável com o texto dos balões (o que é, para que serve, como configurar, onde achar).
  const CAMPOS = {
    apiUrl: {
      grupo: 'api', rotulo: 'Endereço da API do sistema', tipo: 'url', padrao: () => env().apiUrl || '',
      ajuda: {
        oque: 'O endereço da API do sistema (hoje, o SIGp): onde ficam notas, locais, provedores e as regras.',
        para: 'Esta tela lê e grava tudo por ele. O n8n usa outro endereço, interno da rede Docker (SIGP_API_URL).',
        como: 'http://IP-do-servidor:PORTA, sem barra no fim. No mesmo computador: http://127.0.0.1:5001.',
        onde: 'docker-compose.yml, serviço "api", linha "ports" (ou `docker ps`, container sigp_api). Teste abrindo ENDEREÇO/api/health: deve mostrar "ok".',
      },
    },
    n8nUrl: {
      grupo: 'n8n', rotulo: 'Endereço do n8n', tipo: 'url', padrao: () => env().n8nUrl || '',
      ajuda: {
        oque: 'O endereço do n8n, o orquestrador que lê o Gmail, chama a IA local e envia os alertas.',
        para: 'A tela manda notas e eventos para os webhooks do n8n a partir deste endereço.',
        como: 'O mesmo endereço que você abre para editar os workflows, sem barra no fim. No mesmo computador: http://127.0.0.1:5678.',
        onde: 'docker-compose.yml, serviço "n8n" (linha "ports" ou N8N_EDITOR_BASE_URL).',
      },
    },
    modoEntrada: {
      grupo: 'n8n', rotulo: 'Entrada de notas', tipo: 'opcoes', padrao: () => (['n8n', 'api'].includes(env().modoEntrada) ? env().modoEntrada : 'n8n'),  // SIGP_PUBLIC_MODO_ENTRADA; sem ela, n8n
      opcoes: [['n8n', 'Pelo n8n (igual à produção)'], ['api', 'Direto na API (contingência)']],
      ajuda: {
        oque: 'Por onde a nota lançada e a nota paga digitadas na tela entram.',
        para: 'Pelo n8n, a nota passa pelos mesmos workflows do Gmail (WF-01, WF-02). Direto na API serve quando o n8n está parado.',
        como: 'Deixe "Pelo n8n". Se o n8n não responder, a tela grava direto na API e avisa.',
        onde: 'Os workflows WF-01 e WF-02 precisam estar ativos no n8n.',
      },
    },
    webhookNotaLancada: webhook('sigp-nota-lancada', 'Webhook: nota lançada', 'WF-01 Receber nota lançada', 'recebe a nota lançada digitada na tela'),
    webhookNotaPaga: webhook('sigp-nota-paga', 'Webhook: nota paga', 'WF-02 Receber nota paga', 'recebe a nota paga digitada na tela'),
    webhookEventos: webhook('sigp-eventos', 'Webhook: eventos e análises', 'WF-05 Eventos', 'recebe pedidos de análise manual feitos na tela'),
    webhookNotas: webhook('sigp-notas', 'Webhook: notas conciliadas', 'Notas API + SIE Webhook', 'recebe a nota paga conciliada (MATCH) para alertas e SIE'),
    webhookFaturaPdf: webhook('sigp-faturas-pdf', 'Webhook: extração de fatura PDF', 'Extrair fatura PDF de provedor', 'lê a fatura PDF anexada na aba Faturas'),
  };

  function webhook(caminho, rotulo, workflow, funcao) {
    return {
      grupo: 'n8n', rotulo, tipo: 'webhook', padrao: () => caminho,
      ajuda: {
        oque: `O caminho do webhook do workflow "${workflow}" no n8n.`,
        para: `Esse workflow ${funcao}.`,
        como: `Só o caminho (padrão: ${caminho}); a tela junta com o endereço do n8n. Também aceita a URL completa.`,
        onde: `No n8n, abra "${workflow}", nó Webhook, campo "Path" (a "Production URL" mostra o endereço completo). O workflow precisa estar ativo.`,
      },
    };
  }

  const lerStore = () => {
    try { return JSON.parse(localStorage.getItem(STORE) || '{}') || {}; } catch (e) { return {}; }
  };
  const gravarStore = (obj) => localStorage.setItem(STORE, JSON.stringify(obj));
  const semBarra = (v) => String(v || '').trim().replace(/\/+$/, '');

  function get(nome) {
    const salvo = lerStore()[nome];
    if (salvo !== undefined && salvo !== '') return salvo;
    const antigo = LEGADO[nome] ? localStorage.getItem(LEGADO[nome]) : null;
    if (antigo) return antigo;
    return CAMPOS[nome] ? CAMPOS[nome].padrao() : '';
  }

  function origem(nome) {
    if (lerStore()[nome]) return 'tela';
    if (LEGADO[nome] && localStorage.getItem(LEGADO[nome])) return 'tela';
    return CAMPOS[nome]?.padrao() ? 'instalacao' : 'vazio';
  }

  function set(valores) {
    const store = lerStore();
    Object.entries(valores).forEach(([nome, valor]) => {
      const v = CAMPOS[nome]?.tipo === 'url' ? semBarra(valor) : String(valor ?? '').trim();
      if (v) store[nome] = v; else delete store[nome];
      if (LEGADO[nome]) localStorage.removeItem(LEGADO[nome]);
    });
    gravarStore(store);
  }

  const apiUrl = () => semBarra(get('apiUrl'));
  const n8nUrl = () => semBarra(get('n8nUrl'));
  // URL completa de um webhook: o valor salvo pode ser só o caminho ou a URL inteira.
  function webhookUrl(nome) {
    const v = String(get(nome) || '').trim();
    if (!v) return '';
    if (/^https?:\/\//i.test(v)) return v;
    return n8nUrl() ? `${n8nUrl()}/webhook/${v.replace(/^\/+|^webhook\//g, '')}` : '';
  }

  // Webhook de contas de provedores (fila e log próprios da tela): URL completa, token e ligado/desligado.
  function contasProvedores() {
    const store = lerStore().contasProvedores;
    if (store) return { url: '', token: '', habilitado: false, ...store };
    try { return { url: '', token: '', habilitado: false, ...(JSON.parse(localStorage.getItem(LEGADO_CONTAS)) || {}) }; } catch (e) {
      return { url: '', token: '', habilitado: false };
    }
  }
  function setContasProvedores(cfg) {
    const store = lerStore();
    store.contasProvedores = { url: String(cfg.url || '').trim(), token: String(cfg.token || '').trim(), habilitado: Boolean(cfg.habilitado) };
    gravarStore(store);
    localStorage.removeItem(LEGADO_CONTAS);
  }

  function restaurarPadroes() {
    const contas = lerStore().contasProvedores;
    gravarStore(contas ? { contasProvedores: contas } : {});
    Object.values(LEGADO).forEach((k) => localStorage.removeItem(k));
  }

  window.SIGP_CONFIG = { CAMPOS, get, set, origem, apiUrl, n8nUrl, webhookUrl, contasProvedores, setContasProvedores, restaurarPadroes };
})();
