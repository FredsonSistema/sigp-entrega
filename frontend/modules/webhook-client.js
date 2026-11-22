const SIGP_WEBHOOK_DEFAULTS = {
  enabled: false,
  url: '',
  token: '',
};

async function enviarEventoWebhook(evento, dados, cfg = SIGP_WEBHOOK_DEFAULTS) {
  const config = { ...SIGP_WEBHOOK_DEFAULTS, ...cfg };
  if (!config.enabled || !config.url) {
    return { ok: false, motivo: 'webhook_desabilitado' };
  }

  const payload = {
    versao: 1,
    evento,
    timestamp: new Date().toISOString(),
    dados,
  };

  try {
    const response = await fetch(config.url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(config.token ? { Authorization: `Bearer ${config.token}` } : {}),
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      return { ok: false, motivo: text || `http_${response.status}` };
    }

    return { ok: true, status: response.status };
  } catch (error) {
    return { ok: false, motivo: error?.message || 'erro_de_rede' };
  }
}

if (typeof window !== 'undefined') {
  window.SIGP_WEBHOOK = {
    SIGP_WEBHOOK_DEFAULTS,
    enviarEventoWebhook,
  };
}
