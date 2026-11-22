// Integração do navegador com a API SIGp, SQLite e n8n.
(() => {
  const KEYS = {
    backendUrl: 'sigp_nfse_backend_url',
    n8nBase: 'sigp_n8n_base_url',
    entrada: 'sigp_modo_entrada',
  };
  const LOCAL_KEYS = { ti_agencias_v1: 'agencia', ti_rodoviarias_v1: 'rodoviaria', ti_garagens_v1: 'garagem' };
  const APP_STATE_KEYS = [
    'sigp_activity_log_v1',
    'sigp_notes_v1',
    'sigp_os_v1',
    'sigp_os_contador_v1',
    'sigp_os_empresa_v1',
    'sigp_eventos_v1',
    'sigp_eventos_pessoal_v1',
    'ti_sistemas_v1',
    'ti_rederef_v1',
    'sigp_backup_history_v1',
  ];
  const PENDING_KEY = 'sigp_sqlite_pending_v1';
  const MIGRATION_KEY = 'sigp_sqlite_migration_v1';
  const read = (key, fallback = '') => {
    try { return localStorage.getItem(key) || fallback; } catch (error) { return fallback; }
  };
  const readRaw = (key) => {
    try { return localStorage.getItem(key); } catch (error) { return null; }
  };
  // Endereços, chave e modo vêm da configuração de integração (frontend/modules/config-integracao.js).
  const backendUrl = () => window.SIGP_CONFIG.apiUrl();
  const n8nBase = () => window.SIGP_CONFIG.n8nUrl();
  const modoEntrada = () => window.SIGP_CONFIG.get('modoEntrada') || 'n8n';
  const originalSetItem = Storage.prototype.setItem;
  const originalRemoveItem = Storage.prototype.removeItem;

  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url || '';
    const method = String(init.method || (typeof input === 'object' && input?.method) || 'GET').toUpperCase();
    // A sessão do login (frontend/modules/login.js) vai em toda chamada à API: é ela que diz quem está usando.
    // A tela não envia chave de API: chaves são só para integrações (n8n, outro sistema).
    let sessao = '';
    try { sessao = sessionStorage.getItem('sigp_sessao') || ''; } catch (error) { sessao = ''; }
    if (sessao && backendUrl() && url.startsWith(backendUrl())) {
      const headers = new Headers(init.headers || (typeof input === 'object' ? input.headers : undefined) || {});
      if (!headers.has('Authorization')) headers.set('Authorization', `Bearer ${sessao}`);
      return originalFetch(input, { ...init, headers }).then((resposta) => {
        // Sessão vencida, encerrada ou usuário desativado: volta para o login (os dados do navegador ficam).
        if (resposta.status === 401 && !url.includes('/api/auth/')) {
          resposta.clone().json().then((j) => {
            if (j && j.sessao === 'expirada') { sessionStorage.removeItem('sigp_sessao'); window.location.reload(); }
          }).catch(() => {});
        }
        return resposta;
      });
    }
    return originalFetch(input, init);
  };

  const WEBHOOK_PATHS = { '/api/notas/lancadas': 'webhookNotaLancada', '/api/notas/pagas': 'webhookNotaPaga' };

  async function enviarDocumento(path, body) {
    const webhook = WEBHOOK_PATHS[path];
    const webhookUrl = webhook ? window.SIGP_CONFIG.webhookUrl(webhook) : '';
    if (modoEntrada() === 'n8n' && webhookUrl) {
      try {
        const response = await originalFetch(webhookUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...body, canal: 'interface' }),
        });
        const result = await response.json().catch(() => ({}));
        if (response.status !== 404 && response.status < 500) {
          if (!response.ok || result.ok === false) throw Object.assign(new Error(result.error || `http_${response.status}`), { definitivo: true, status: response.status });
          return { ...result, via: 'n8n' };
        }
        console.warn(`SIGp: webhook n8n ${webhook} indisponível (HTTP ${response.status}); gravando direto na API.`);
      } catch (error) {
        if (error.definitivo) throw error;
        console.warn(`SIGp: n8n inacessível (${error.message}); gravando direto na API.`);
      }
    }
    const response = await window.fetch(`${backendUrl()}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, origem: body.origem || 'manual' }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw Object.assign(new Error(result.error || `http_${response.status}`), { status: response.status });
    return { ...result, via: 'api' };
  }

  async function enviarAnaliseManual(dados) {
    const response = await originalFetch(window.SIGP_CONFIG.webhookUrl('webhookEventos'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        evento: 'analise_manual',
        timestamp: new Date().toISOString(),
        dados,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.ok === false) {
      throw new Error(result.error || `Webhook de análise respondeu HTTP ${response.status}`);
    }
    return result;
  }

  function readPending() {
    try {
      const pending = JSON.parse(read(PENDING_KEY, '[]'));
      return new Set(Array.isArray(pending) ? pending : []);
    } catch (error) {
      throw new Error('A fila local de sincronização SQLite está inválida; os dados locais foram preservados.');
    }
  }

  function setPending(storageKey, isPending) {
    const pending = readPending();
    if (isPending) pending.add(storageKey);
    else pending.delete(storageKey);
    originalSetItem.call(localStorage, PENDING_KEY, JSON.stringify([...pending]));
  }

  function reportPersistenceError(label, error) {
    console.error(`SIGp: falha ao persistir ${label} no SQLite:`, error);
    if (error && error.status === 403 && typeof window.toast === 'function') {
      // Perfil sem permissão: a mudança não foi gravada; na próxima abertura vale o que está no servidor.
      window.toast(`${error.message} A alteração não foi salva.`, 6000);
      return;
    }
    if (typeof window.toast === 'function') {
      window.toast(`Não foi possível salvar ${label} no SQLite. Os dados continuam neste navegador; verifique a API e tente novamente.`);
    }
  }

  async function putLocationItems(storageKey, items) {
    const response = await window.fetch(`${backendUrl()}/api/locais/${LOCAL_KEYS[storageKey]}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.ok === false) {
      throw Object.assign(new Error(result.error || `http_${response.status}`), { status: response.status });
    }
  }

  async function syncLocation(storageKey) {
    const raw = readRaw(storageKey);
    const items = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(items)) throw new Error(`O conteúdo local de ${storageKey} não é uma lista.`);
    await putLocationItems(storageKey, items);
    setPending(storageKey, false);
    window.dispatchEvent(new CustomEvent('sigp:locais-gravados', { detail: { storageKey } }));
  }

  // Marcadores: a API grava com a grafia do catálogo (apelido "Rota" vira "RT") e renomear/excluir no catálogo
  // muda todos os locais. Traz os marcadores da API para este navegador (sem gravar de volta); cadastro com
  // alteração ainda não enviada fica como está.
  async function atualizarMarcadoresLocais() {
    const response = await window.fetch(`${backendUrl()}/api/locais?inativos=1`);
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !Array.isArray(result.items)) return false;
    const daApi = new Map(result.items.map((item) => [String(item.id), item.marcadores || []]));
    const pending = readPending();
    let mudou = false;
    for (const storageKey of Object.keys(LOCAL_KEYS)) {
      if (pending.has(storageKey)) continue;
      const records = JSON.parse(read(storageKey, '[]'));
      if (!Array.isArray(records)) continue;
      let alterado = false;
      records.forEach((record) => {
        const novos = daApi.get(String(record.id));
        if (novos && JSON.stringify(novos) !== JSON.stringify(record.marcadores || [])) {
          record.marcadores = novos;
          alterado = true;
        }
      });
      if (alterado) {
        originalSetItem.call(localStorage, storageKey, JSON.stringify(records));
        mudou = true;
      }
    }
    if (mudou) window.dispatchEvent(new CustomEvent('sigp:locais-atualizados', { detail: { marcadores: true } }));
    return mudou;
  }

  async function loadAndMigrateLocations() {
    const response = await window.fetch(`${backendUrl()}/api/locais?inativos=1`);
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !Array.isArray(result.items)) {
      throw new Error(result.error || `Não foi possível carregar os cadastros do SQLite (HTTP ${response.status}).`);
    }

    const pending = readPending();
    const isLegacyBrowser = readRaw(MIGRATION_KEY) !== '1';
    const fromDatabase = { agencia: [], rodoviaria: [], garagem: [] };
    result.items.forEach((item) => {
      if (fromDatabase[item.tipo]) fromDatabase[item.tipo].push(item);
    });

    for (const [storageKey, tipo] of Object.entries(LOCAL_KEYS)) {
      const raw = read(storageKey);
      let localItems = [];
      if (raw) {
        localItems = JSON.parse(raw);
        if (!Array.isArray(localItems)) throw new Error(`O cadastro local ${storageKey} não é uma lista; os dados não foram alterados.`);
      }
      const dbItems = fromDatabase[tipo];
      const activeDbItems = dbItems.filter((item) => item.ativo);
      const localHasPendingChanges = pending.has(storageKey);
      let selected = activeDbItems;

      if ((!dbItems.length || localHasPendingChanges || isLegacyBrowser) && raw !== null) {
        const merged = new Map(activeDbItems.map((item) => [String(item.id), item]));
        localItems.forEach((item) => {
          const key = String(item.id || '');
          if (!key) return;
          merged.set(key, { ...(merged.get(key) || {}), ...item });
        });
        selected = [...merged.values()];
        try {
          await putLocationItems(storageKey, selected);
        } catch (error) {
          // Perfil sem permissão de editar locais: fica com o que está no servidor (nada se perde lá).
          if (error.status !== 403) throw error;
          selected = activeDbItems;
        }
        setPending(storageKey, false);
      }
      originalSetItem.call(localStorage, storageKey, JSON.stringify(selected));
    }
  }

  function parseStoredValue(raw) {
    try { return JSON.parse(raw); } catch (error) { return raw; }
  }

  async function putAppState(key, value) {
    const response = await window.fetch(`${backendUrl()}/api/app-state/${encodeURIComponent(key)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.ok === false) {
      throw Object.assign(new Error(result.error || `http_${response.status}`), { status: response.status });
    }
  }

  async function syncAppState(key) {
    const raw = localStorage.getItem(key);
    if (raw === null) {
      const response = await window.fetch(`${backendUrl()}/api/app-state/${encodeURIComponent(key)}`, { method: 'DELETE' });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.ok === false) {
        throw Object.assign(new Error(result.error || `http_${response.status}`), { status: response.status });
      }
    } else {
      await putAppState(key, parseStoredValue(raw));
    }
    setPending(key, false);
  }

  async function loadAndMigrateAppState() {
    const keys = APP_STATE_KEYS.join(',');
    const response = await window.fetch(`${backendUrl()}/api/app-state?keys=${encodeURIComponent(keys)}`);
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.items || typeof result.items !== 'object') {
      throw new Error(result.error || `Não foi possível carregar os dados do SQLite (HTTP ${response.status}).`);
    }
    const pending = readPending();
    for (const key of APP_STATE_KEYS) {
      const raw = localStorage.getItem(key);
      if (pending.has(key) || !Object.prototype.hasOwnProperty.call(result.items, key)) {
        try {
          if (raw !== null) {
            await putAppState(key, parseStoredValue(raw));
            setPending(key, false);
          } else if (pending.has(key)) {
            await syncAppState(key);
          }
        } catch (error) {
          // Perfil sem permissão para estes dados da tela: usa o valor do servidor e segue.
          if (error.status !== 403) throw error;
          setPending(key, false);
          if (Object.prototype.hasOwnProperty.call(result.items, key)) originalSetItem.call(localStorage, key, JSON.stringify(result.items[key]));
        }
      } else {
        originalSetItem.call(localStorage, key, JSON.stringify(result.items[key]));
      }
    }
  }

  async function initializePersistentData() {
    await loadAndMigrateLocations();
    await loadAndMigrateAppState();
    originalSetItem.call(localStorage, MIGRATION_KEY, '1');
  }

  const pendingLocations = new Set();
  const pendingState = new Set();
  let locationsTimer = null;
  let stateTimer = null;

  function scheduleLocationSync(storageKey) {
    setPending(storageKey, true);
    pendingLocations.add(storageKey);
    clearTimeout(locationsTimer);
    locationsTimer = setTimeout(async () => {
      const keys = [...pendingLocations];
      pendingLocations.clear();
      for (const key of keys) {
        try { await syncLocation(key); }
        catch (error) { reportPersistenceError(`cadastro (${key})`, error); }
      }
    }, 500);
  }

  function scheduleStateSync(storageKey) {
    setPending(storageKey, true);
    pendingState.add(storageKey);
    clearTimeout(stateTimer);
    stateTimer = setTimeout(async () => {
      const keys = [...pendingState];
      pendingState.clear();
      for (const key of keys) {
        try { await syncAppState(key); }
        catch (error) { reportPersistenceError(`dados (${key})`, error); }
      }
    }, 300);
  }

  const appStateKeySet = new Set(APP_STATE_KEYS);
  Storage.prototype.setItem = function setItem(key, value) {
    originalSetItem.call(this, key, value);
    if (this !== window.localStorage) return;
    if (LOCAL_KEYS[key]) scheduleLocationSync(key);
    else if (appStateKeySet.has(key)) scheduleStateSync(key);
  };

  Storage.prototype.removeItem = function removeItem(key) {
    originalRemoveItem.call(this, key);
    if (this !== window.localStorage) return;
    if (LOCAL_KEYS[key]) scheduleLocationSync(key);
    else if (appStateKeySet.has(key)) scheduleStateSync(key);
  };

  async function sincronizarLocais() {
    for (const key of Object.keys(LOCAL_KEYS)) {
      if (read(key) !== null) await syncLocation(key);
    }
  }

  const PROVIDER_FIELDS = ['nome', 'valor', 'dataVencimento', 'diaVencimento', 'faturaAtualId'];
  const normalizeName = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]/g, '');

  // Regra única dos provedores: toda nota/fatura associada a um local atualiza o provedor NA API.
  // Esta função traz esse resultado para o cadastro deste navegador (sem gravar de volta), para que a
  // próxima gravação do local a partir da tela não desfaça a atualização.
  async function refreshLocationProviders(tipo, localId, opcoes = {}) {
    const storageKey = Object.keys(LOCAL_KEYS).find((key) => LOCAL_KEYS[key] === tipo);
    if (!storageKey || !localId) return false;
    const response = await window.fetch(`${backendUrl()}/api/locais/item/${encodeURIComponent(localId)}`);
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.item) return false;
    const records = JSON.parse(read(storageKey, '[]'));
    const record = Array.isArray(records) ? records.find((item) => String(item.id) === String(localId)) : null;
    if (!record) return false;
    const providers = Array.isArray(record.provedores) ? record.provedores : [];
    let changed = false;
    (result.item.provedores || []).forEach((apiProvider) => {
      if (!apiProvider || typeof apiProvider !== 'object') return;
      const local = providers.find((item) => item && apiProvider.id && String(item.id) === String(apiProvider.id))
        || providers.find((item) => item && normalizeName(item.nome) && normalizeName(item.nome) === normalizeName(apiProvider.nome));
      if (!local) {
        providers.push({ ...apiProvider });
        changed = true;
        return;
      }
      PROVIDER_FIELDS.forEach((field) => {
        if (apiProvider[field] !== undefined && apiProvider[field] !== '' && local[field] !== apiProvider[field]) {
          if (field === 'nome' && local.nome && !opcoes.trocarNome) return; // um nome digitado não é trocado (salvo correção do cadastro)
          local[field] = apiProvider[field];
          changed = true;
        }
      });
    });
    if (!changed) return false;
    record.provedores = providers;
    originalSetItem.call(localStorage, storageKey, JSON.stringify(records));
    window.dispatchEvent(new CustomEvent('sigp:locais-atualizados', { detail: { tipo, id: localId } }));
    return true;
  }

  window.SIGP_API = {
    KEYS,
    backendUrl,
    n8nBase,
    modoEntrada,
    enviarDocumento,
    enviarAnaliseManual,
    sincronizarLocais,
    initializePersistentData,
    persistLocation: syncLocation,
    persistAppState: syncAppState,
    refreshLocationProviders,
    atualizarMarcadoresLocais,
  };
})();
