// H-01 — Importação CSV de localidades (agências, rodoviárias, garagens) e de sistemas de TI.
// Formato: o mesmo do "Exportar CSV" (separador ";", listas com " | ", partes com " - "), aceitando a coluna Marcadores.
// Fluxo: escolher arquivo → prévia (criar / atualizar / igual, com avisos) → importar só as linhas marcadas.
// Atualização nunca apaga: preenche campos vazios e acrescenta responsáveis, provedores e redes que não existem.
// Valor e vencimento da fatura do provedor nunca são alterados (vêm das faturas associadas).
// As funções de leitura não dependem do navegador (testes: tests/n8n/importar_csv.test.js).
const SIGP_IMPORTAR_CSV = (() => {
  const semAcento = (v) => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const limpar = (v) => String(v ?? '').replace(/\s+/g, ' ').trim();

  // CSV com aspas, quebra de linha dentro de aspas, BOM e CRLF.
  function lerCsv(texto, separador = ';') {
    const s = String(texto ?? '').replace(/^\uFEFF/, '');
    const linhas = [];
    let linha = [];
    let campo = '';
    let aspas = false;
    for (let i = 0; i < s.length; i += 1) {
      const c = s[i];
      if (aspas) {
        if (c === '"' && s[i + 1] === '"') { campo += '"'; i += 1; } else if (c === '"') aspas = false; else campo += c;
      } else if (c === '"') aspas = true;
      else if (c === separador) { linha.push(campo); campo = ''; } else if (c === '\n' || c === '\r') {
        if (c === '\r' && s[i + 1] === '\n') i += 1;
        linha.push(campo); campo = '';
        if (linha.some((x) => x.trim() !== '')) linhas.push(linha);
        linha = [];
      } else campo += c;
    }
    linha.push(campo);
    if (linha.some((x) => x.trim() !== '')) linhas.push(linha);
    return linhas;
  }

  const COLUNAS_LOCAL = {
    nome: 'nome', cidade: 'cidade', cep: 'cep', endereco: 'endereco', numero: 'numero', 'vencimento fatura': 'vencimentoFatura',
    'ultima visita': 'ultimaVisita', responsaveis: 'responsaveis', provedores: 'provedores', redes: 'redes',
    marcadores: 'marcadores', observacoes: 'obs', observacao: 'obs',
  };
  const COLUNAS_SISTEMA = { nome: 'nome', tipo: 'tipo', 'url/ip': 'urlIp', url: 'urlIp', ip: 'urlIp', usuario: 'usuario', observacao: 'observacao', observacoes: 'observacao' };

  function comCabecalho(texto, mapa) {
    const linhas = lerCsv(texto);
    if (!linhas.length) return { registros: [], erro: 'Arquivo vazio.' };
    const chaves = linhas[0].map((h) => mapa[semAcento(h)] || null);
    if (!chaves.includes('nome')) return { registros: [], erro: 'Cabeçalho sem a coluna "Nome". Use o mesmo formato do "Exportar CSV".' };
    const registros = linhas.slice(1).map((cols, i) => {
      const r = { linha: i + 2 };
      chaves.forEach((k, j) => { if (k) r[k] = String(cols[j] ?? '').trim(); });
      return r;
    });
    return { registros, colunasIgnoradas: linhas[0].filter((h, j) => !chaves[j]) };
  }

  const dataIso = (v) => {
    const m = String(v || '').trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (m) return `${m[3]}-${m[2]}-${m[1]}`;
    return /^\d{4}-\d{2}-\d{2}$/.test(String(v || '').trim()) ? String(v).trim() : '';
  };
  const lista = (v) => String(v || '').split('|').map((x) => x.trim()).filter(Boolean);
  const partes = (v) => String(v || '').split(/\s+-\s+/).map((x) => x.trim()).filter(Boolean);
  const ehTelefone = (t) => (t.replace(/\D/g, '').length >= 8 && !/[a-z]{3,}/i.test(t.replace(/^(tel|fone|whatsapp)\.?:?/i, '')));
  const ehEmail = (t) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t);
  const ehUrl = (t) => /^(https?:\/\/|www\.)/i.test(t);
  const ehDinheiro = (t) => /^(R\$\s*)?\d{1,3}(\.\d{3})*,\d{2}$/.test(t);
  const ehIp = (t) => /\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b|\.sn\.mynetname\.net/i.test(t);
  const NAO_E_PROVEDOR = /^(consultar|somente ag\.? ?digital|-|n\/a)$/i;

  function responsaveis(texto) {
    const out = [];
    for (const seg of lista(texto)) {
      const r = { nome: '', telefone: '', email: '' };
      for (const t of partes(seg)) {
        if (ehEmail(t) && !r.email) r.email = t;
        else if (ehTelefone(t) && !r.telefone) r.telefone = t;
        else if (!r.nome) r.nome = t;
      }
      if (!r.nome && out.length) r.nome = out[out.length - 1].nome; // "(73) 90000-0000" depois de "SOBRENOME/NOME - ..."
      if (r.nome || r.telefone || r.email) out.push(r);
    }
    return out;
  }

  function provedores(texto, avisos, obsExtra) {
    const out = [];
    for (const seg of lista(texto)) {
      const p = { nome: '', contato: '', email: '' };
      const contatos = [];
      for (const t of partes(seg)) {
        const venc = t.match(/^venc\.?\s*dia\s*(\d{1,2})$/i);
        if (venc) p.diaVencimento = String(Number(venc[1]));
        else if (ehDinheiro(t)) p.valor = t.replace(/^R\$\s*/, '').replace(/\./g, '').replace(',', '.');
        else if (ehEmail(t) && !p.email) p.email = t;
        else if (!p.nome && !ehTelefone(t) && !ehUrl(t)) p.nome = t;
        else if (!(p.nome && semAcento(t) === semAcento(p.nome))) contatos.push(t); // "RAMOS NET - RAMOS NET"
      }
      p.contato = contatos.join(' / ');
      if (!p.nome && p.contato) p.nome = p.contato;
      if (NAO_E_PROVEDOR.test(p.nome)) { obsExtra.push(`Provedor: ${seg}`); avisos.push(`"${seg}" não é nome de provedor: foi para as observações.`); continue; }
      if (p.nome) out.push(p);
    }
    // Mesmo provedor repetido na linha (dois telefones): junta os contatos.
    const unidos = [];
    for (const p of out) {
      const igual = unidos.find((u) => semAcento(u.nome) === semAcento(p.nome));
      if (!igual) { unidos.push(p); continue; }
      for (const k of ['email', 'valor', 'diaVencimento']) if (!igual[k] && p[k]) igual[k] = p[k];
      if (p.contato && !igual.contato.includes(p.contato)) igual.contato = [igual.contato, p.contato].filter(Boolean).join(' / ');
    }
    return unidos;
  }

  function redes(texto, obsExtra) {
    const out = [];
    for (const seg of lista(texto)) {
      const ts = partes(seg);
      const ips = ts.filter(ehIp);
      if (!ips.length) { obsExtra.push(`Rede: ${seg}`); continue; }
      const rotulo = ts.filter((t) => !ehIp(t)).join(' - ');
      out.push({ label: [rotulo, ips.length > 1 ? `também ${ips.slice(1).join(' / ')}` : ''].filter(Boolean).join(' · '), ipWireguard: ips[0] });
    }
    return out;
  }

  // Linha do CSV de localidades -> registro no formato do SIGp.
  function paraLocal(r) {
    const avisos = [];
    const obsExtra = [];
    const reg = {
      nome: limpar(r.nome), cidade: limpar(r.cidade), cep: limpar(r.cep), endereco: limpar(r.endereco), numero: limpar(r.numero),
      vencimentoFatura: dataIso(r.vencimentoFatura),
      responsaveis: responsaveis(r.responsaveis),
      provedores: provedores(r.provedores, avisos, obsExtra),
      redes: redes(r.redes, obsExtra),
      marcadores: lista(r.marcadores).map(limpar),
    };
    if (r.vencimentoFatura && !reg.vencimentoFatura) avisos.push(`Vencimento "${r.vencimentoFatura}" não é data (dd/mm/aaaa): ignorado.`);
    const visita = dataIso(r.ultimaVisita);
    if (visita) { reg.historicoVisitas = [{ data: visita, obs: 'Importado do CSV' }]; reg.ultimaVisita = visita; }
    reg.obs = [String(r.obs || '').trim(), ...obsExtra].filter(Boolean).join('\n');
    if (!reg.nome) avisos.push('Sem nome: linha ignorada.');
    if (!reg.cidade) avisos.push('Sem cidade.');
    return { registro: reg, avisos };
  }

  const chaveLocal = (x) => `${semAcento(x.nome)}|${semAcento(x.cidade)}`;

  // Junta o registro importado num existente sem apagar nada. Devolve a lista de mudanças.
  function mesclarLocal(existente, novo) {
    const mudancas = [];
    for (const k of ['cidade', 'cep', 'endereco', 'numero', 'vencimentoFatura', 'obs']) {
      if (!String(existente[k] || '').trim() && String(novo[k] || '').trim()) { existente[k] = novo[k]; mudancas.push(k); }
    }
    existente.responsaveis = Array.isArray(existente.responsaveis) ? existente.responsaveis : [];
    for (const r of novo.responsaveis) {
      const ja = existente.responsaveis.some((e) => semAcento(e.nome) === semAcento(r.nome)
        && (e.telefone || '').replace(/\D/g, '') === (r.telefone || '').replace(/\D/g, ''));
      if (!ja) { existente.responsaveis.push({ ...r }); mudancas.push(`responsável ${r.nome || r.telefone}`); }
    }
    existente.provedores = Array.isArray(existente.provedores) ? existente.provedores : [];
    for (const p of novo.provedores) {
      const igual = existente.provedores.find((e) => semAcento(e.nome) === semAcento(p.nome));
      if (!igual) { existente.provedores.push({ id: novoId('p'), ...p }); mudancas.push(`provedor ${p.nome}`); continue; }
      for (const k of ['contato', 'email', 'diaVencimento']) {
        if (!String(igual[k] || '').trim() && p[k]) { igual[k] = p[k]; mudancas.push(`${k} de ${p.nome}`); }
      }
      // valor e dataVencimento do provedor não mudam: vêm da fatura associada.
    }
    existente.redes = Array.isArray(existente.redes) ? existente.redes : [];
    for (const n of novo.redes) {
      if (!existente.redes.some((e) => (e.ipWireguard || '') === n.ipWireguard)) { existente.redes.push({ ...n }); mudancas.push(`rede ${n.ipWireguard}`); }
    }
    const marc = new Set([...(existente.marcadores || []), ...novo.marcadores]);
    if (marc.size !== (existente.marcadores || []).length) { existente.marcadores = [...marc]; mudancas.push('marcadores'); }
    if (novo.historicoVisitas && !(existente.historicoVisitas || []).some((v) => v.data === novo.ultimaVisita)) {
      existente.historicoVisitas = [...(existente.historicoVisitas || []), ...novo.historicoVisitas];
      existente.ultimaVisita = [existente.ultimaVisita, novo.ultimaVisita].filter(Boolean).sort().pop();
      mudancas.push('visita');
    }
    return mudancas;
  }

  let contador = 0;
  function novoId(prefixo) { contador += 1; return `${prefixo}_${Date.now().toString(36)}${contador.toString(36)}${Math.random().toString(36).slice(2, 6)}`; }

  // Prévia de localidades: o que acontece com cada linha, sem alterar os existentes.
  function previaLocais(texto, existentes) {
    const { registros, erro, colunasIgnoradas } = comCabecalho(texto, COLUNAS_LOCAL);
    if (erro) return { erro, linhas: [] };
    const porChave = new Map(existentes.map((e) => [chaveLocal(e), e]));
    const vistos = new Map();
    const linhas = registros.map((r) => {
      const { registro, avisos } = paraLocal(r);
      if (!registro.nome) return { linha: r.linha, acao: 'erro', registro, avisos, mudancas: [] };
      const chave = chaveLocal(registro);
      if (vistos.has(chave)) avisos.push(`Repetido no arquivo (linha ${vistos.get(chave)}): será juntado.`);
      else vistos.set(chave, r.linha);
      const alvo = porChave.get(chave);
      if (!alvo) return { linha: r.linha, acao: vistos.get(chave) === r.linha ? 'criar' : 'juntar', registro, avisos, mudancas: [] };
      const copia = JSON.parse(JSON.stringify(alvo));
      const mudancas = mesclarLocal(copia, registro);
      return { linha: r.linha, acao: mudancas.length ? 'atualizar' : 'igual', registro, avisos, mudancas, alvoId: alvo.id };
    });
    return { linhas, colunasIgnoradas };
  }

  // Aplica as linhas escolhidas sobre a lista (alterando-a). Devolve contagens.
  function aplicarLocais(previa, existentes, escolhidas) {
    const porChave = new Map(existentes.map((e) => [chaveLocal(e), e]));
    const cont = { criados: 0, atualizados: 0 };
    for (const l of previa.linhas) {
      if (!escolhidas.has(l.linha) || l.acao === 'erro' || l.acao === 'igual') continue;
      const chave = chaveLocal(l.registro);
      const alvo = porChave.get(chave);
      if (alvo) {
        if (mesclarLocal(alvo, l.registro).length) cont.atualizados += 1;
      } else {
        const novo = { id: novoId('a'), ...JSON.parse(JSON.stringify(l.registro)) };
        novo.provedores = novo.provedores.map((p) => ({ id: novoId('p'), ...p }));
        existentes.push(novo);
        porChave.set(chave, novo);
        cont.criados += 1;
      }
    }
    return cont;
  }

  // Sistemas de TI. Observação com cara de senha não é importada.
  const pareceSenha = (t) => {
    const s = String(t || '').trim();
    return s.length >= 6 && !/\s/.test(s) && /[A-Za-z]/.test(s) && /\d/.test(s) && /[^A-Za-z0-9]/.test(s) && !/^https?:/i.test(s);
  };
  const chaveSistema = (x) => `${semAcento(x.nome)}|${semAcento(x.urlIp)}|${semAcento(x.usuario)}`;
  function previaSistemas(texto, existentes) {
    const { registros, erro, colunasIgnoradas } = comCabecalho(texto, COLUNAS_SISTEMA);
    if (erro) return { erro, linhas: [] };
    const ja = new Set(existentes.map(chaveSistema));
    const vistos = new Set();
    const linhas = registros.map((r) => {
      const avisos = [];
      const registro = { nome: limpar(r.nome), tipo: limpar(r.tipo), urlIp: limpar(r.urlIp), usuario: limpar(r.usuario), observacao: String(r.observacao || '').trim() };
      if (pareceSenha(registro.observacao)) { registro.observacao = ''; avisos.push('A observação parece uma senha: não foi importada. Guarde senhas num cofre (ex.: Passbolt).'); }
      if (!registro.nome) return { linha: r.linha, acao: 'erro', registro, avisos: [...avisos, 'Sem nome: linha ignorada.'], mudancas: [] };
      const chave = chaveSistema(registro);
      const acao = ja.has(chave) || vistos.has(chave) ? 'igual' : 'criar';
      vistos.add(chave);
      return { linha: r.linha, acao, registro, avisos, mudancas: [] };
    });
    return { linhas, colunasIgnoradas };
  }
  function aplicarSistemas(previa, existentes, escolhidas) {
    let criados = 0;
    for (const l of previa.linhas) {
      if (!escolhidas.has(l.linha) || l.acao !== 'criar') continue;
      existentes.push({ id: novoId('s'), ...l.registro });
      criados += 1;
    }
    return { criados, atualizados: 0 };
  }

  // ---------------- tela (só no navegador) ----------------
  const ALVOS = {
    ag: { nome: 'agências', local: true }, rv: { nome: 'rodoviárias', local: true }, gr: { nome: 'garagens', local: true },
    sys: { nome: 'sistemas de TI', local: false },
  };
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ROTULO = { criar: 'Criar', atualizar: 'Atualizar', juntar: 'Juntar', igual: 'Igual (nada muda)', erro: 'Erro' };

  function dados(tipo) {
    // Funções globais do agencias.html.
    if (tipo === 'sys') return sistemas; // eslint-disable-line no-undef
    return getLocationDataset(tipo); // eslint-disable-line no-undef
  }
  function gravar(tipo) {
    /* eslint-disable no-undef */
    if (tipo === 'sys') { saveSistemas(); renderSistemas(); return; }
    saveLocalByTipo(tipo);
    if (tipo === 'ag') render(); else if (tipo === 'rv') locRodoviarias.refresh(); else locGaragens.refresh();
    /* eslint-enable no-undef */
  }

  function abrir(tipo) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv,text/csv';
    input.onchange = () => {
      const arquivo = input.files[0];
      if (!arquivo) return;
      const leitor = new FileReader();
      leitor.onload = () => mostrarPrevia(tipo, String(leitor.result || ''), arquivo.name);
      leitor.readAsText(arquivo, 'utf-8');
    };
    input.click();
  }

  function mostrarPrevia(tipo, texto, nomeArquivo) {
    const alvo = ALVOS[tipo];
    const previa = alvo.local ? previaLocais(texto, dados(tipo)) : previaSistemas(texto, dados(tipo));
    document.getElementById('sigpCsvOverlay')?.remove();
    const overlay = document.createElement('div');
    overlay.id = 'sigpCsvOverlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    const cont = { criar: 0, atualizar: 0, juntar: 0, igual: 0, erro: 0 };
    previa.linhas.forEach((l) => { cont[l.acao] += 1; });
    const linhasHtml = previa.linhas.map((l) => {
      const r = l.registro;
      const marcavel = ['criar', 'atualizar', 'juntar'].includes(l.acao);
      const detalhe = alvo.local
        ? `${r.provedores.length} provedor(es) · ${r.responsaveis.length} responsável(is) · ${r.redes.length} rede(s)${r.marcadores.length ? ` · ${esc(r.marcadores.join(', '))}` : ''}`
        : `${esc(r.tipo)} · ${esc(r.urlIp)}`;
      return `<tr data-linha="${l.linha}">
        <td><input type="checkbox" data-role="csv-linha" value="${l.linha}" ${marcavel ? 'checked' : 'disabled'}></td>
        <td>${l.linha}</td><td><b>${ROTULO[l.acao]}</b></td>
        <td>${esc(r.nome)}${alvo.local ? ` · ${esc(r.cidade)}` : ''}</td><td>${detalhe}</td>
        <td>${[...l.mudancas.map((m) => `+ ${esc(m)}`), ...l.avisos.map((a) => `⚠ ${esc(a)}`)].join('<br>')}</td></tr>`;
    }).join('');
    overlay.innerHTML = `<div class="nfse-card" style="max-width:1100px;width:100%;max-height:90vh;overflow:auto;background:var(--panel,#161b22)">
      <h3>Importar CSV · ${esc(alvo.nome)}</h3>
      <div class="hint">${esc(nomeArquivo)} · ${previa.linhas.length} linha(s): ${cont.criar} criar, ${cont.atualizar + cont.juntar} atualizar, ${cont.igual} iguais, ${cont.erro} com erro.
        Atualizar só preenche o que está vazio e acrescenta o que falta; nada é apagado. Valor e vencimento da fatura dos provedores não mudam.
        ${previa.colunasIgnoradas?.length ? `Colunas ignoradas: ${esc(previa.colunasIgnoradas.join(', '))}.` : ''}</div>
      ${previa.erro ? `<div class="hint" role="alert">${esc(previa.erro)}</div>` : `
      <table style="width:100%;font-size:13px;margin-top:10px"><thead><tr><th></th><th>Linha</th><th>Ação</th><th>Nome</th><th>Conteúdo</th><th>Mudanças e avisos</th></tr></thead>
      <tbody>${linhasHtml}</tbody></table>`}
      <div class="task-add-row" style="margin-top:12px">
        ${previa.erro ? '' : '<button class="primary small" type="button" data-role="csv-importar">Importar linhas marcadas</button>'}
        <button class="ghost small" type="button" data-role="csv-cancelar">Cancelar</button>
      </div></div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('[data-role="csv-cancelar"]').onclick = () => overlay.remove();
    const botao = overlay.querySelector('[data-role="csv-importar"]');
    if (botao) {
      botao.onclick = () => {
        const escolhidas = new Set([...overlay.querySelectorAll('[data-role="csv-linha"]:checked')].map((c) => Number(c.value)));
        const lista = dados(tipo);
        const r = alvo.local ? aplicarLocais(previa, lista, escolhidas) : aplicarSistemas(previa, lista, escolhidas);
        gravar(tipo);
        overlay.remove();
        // eslint-disable-next-line no-undef
        if (typeof toast === 'function') toast(`CSV importado: ${r.criados} criado(s), ${r.atualizados} atualizado(s).`, 5000);
      };
    }
  }

  return { lerCsv, previaLocais, aplicarLocais, previaSistemas, aplicarSistemas, paraLocal, mesclarLocal, abrir };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = SIGP_IMPORTAR_CSV;
if (typeof window !== 'undefined') window.SIGP_IMPORTAR_CSV = SIGP_IMPORTAR_CSV;
