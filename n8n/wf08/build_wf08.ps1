# Gera n8n_workflow_wf08_gmail_inbox.json a partir dos arquivos desta pasta.
# Uso (na raiz do projeto): pwsh -File n8n\wf08\build_wf08.ps1
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$root = Resolve-Path (Join-Path $dir '..\..')

$prompt = Get-Content (Join-Path $dir 'prompt_classificacao.md') -Raw -Encoding utf8
$schema = Get-Content (Join-Path $dir 'schema_classificacao.json') -Raw -Encoding utf8
# Extrator compartilhado com o WF-03 e o SIGp (B-03) + funções próprias do WF-08.
$libXml = Get-Content (Join-Path $root 'n8n\lib\xml_fiscal.js') -Raw -Encoding utf8
$lib = (Get-Content (Join-Path $root 'n8n\lib\extrator.js') -Raw -Encoding utf8) + "`n" + $libXml + "`n" +
  (Get-Content (Join-Path $dir 'wf08_lib.js') -Raw -Encoding utf8)
$header = "// Gerado por n8n/wf08/build_wf08.ps1 - edite os arquivos de n8n/wf08, não este nó.`n" +
  "const SYSTEM_PROMPT = $($prompt.Trim() | ConvertTo-Json);`n" +
  "const SCHEMA = $(($schema | ConvertFrom-Json) | ConvertTo-Json -Depth 10 -Compress);`n"
$libCode = $header + $lib

# Remetentes e busca do Gmail: vêm do SIGp (Configurações > E-mail das faturas, backend/config_email_faturas.py) a cada
# leitura. Nenhum endereço fica neste arquivo nem no JSON gerado.
$codeJanela = @'
// Leitura automática: busca do SIGp + mensagens recebidas desde a última leitura (5 min de sobreposição;
// as repetidas saem no nó "Retirar mensagens já lidas"). Sem busca válida, nada é lido.
const estado = $getWorkflowStaticData('global');
const agora = Math.floor(Date.now() / 1000);
const desde = Number(estado.ultimaLeitura) || (agora - 600);
const consulta = String($json.consulta || '');
if (!consulta.startsWith('-label:sigp-importado')) {
  throw new Error('O SIGp não devolveu a busca do Gmail. Confira Configurações > E-mail das faturas e a SIGP_API_KEY do n8n.');
}
return [{ json: { q: `${consulta} after:${desde - 300}`, inicio: agora } }];
'@
$codeRetirar = @'
// Guarda a hora desta leitura e as mensagens já entregues (últimas 500), para a sobreposição não repetir nada.
// Só vale nas execuções do workflow ativo (o n8n não grava este estado em execução manual).
const estado = $getWorkflowStaticData('global');
const vistas = new Set(Array.isArray(estado.vistas) ? estado.vistas : []);
const novas = $input.all().filter((item) => item.json && item.json.id && !vistas.has(String(item.json.id)));
novas.forEach((item) => vistas.add(String(item.json.id)));
estado.ultimaLeitura = $('Janela desde a última leitura').first().json.inicio;
estado.vistas = [...vistas].slice(-500);
return novas;
'@
$buscaSigp = {
  param([string]$id, [string]$nome, [int]$x, [int]$y)
  @{
    parameters = @{
      method = 'GET'; url = "={{ `$env.SIGP_API_URL + '/api/configuracoes/email-faturas' }}"
      sendHeaders = $true; headerParameters = $apiHeaders; options = @{ timeout = 15000 }
    }
    id = $id; name = $nome; type = 'n8n-nodes-base.httpRequest'; typeVersion = 4.2; position = @($x, $y)
    retryOnFail = $true; maxTries = 3; waitBetweenTries = 5000
    notes = 'Remetentes e busca do Gmail definidos no SIGp (Configurações > E-mail das faturas). Sem resposta, nada é lido.'
  }
}

$gmailCred = @{ gmailOAuth2 = @{ id = '6w8cHAuUwpPVa6tb'; name = 'Gmail account' } }
$apiHeaders = @{ parameters = @(@{ name = 'X-API-Key'; value = '={{ $env.SIGP_API_KEY }}' }) }

$codePreparar = $libXml + @'

// ---- nó: Preparar anexos PDF ----
// Um item por fatura PDF, levando junto o XML da nota fiscal da mesma mensagem (os dois são obrigatórios e
// guardados no SIGp; os campos fiscais do XML têm prioridade). XML sem PDF vira item próprio (entra em Revisão).
// Mensagem sem PDF nem XML vira item "semAnexo" para receber etiqueta e sair da busca.
const textoEndereco = (v) => {
  if (!v) return '';
  if (typeof v === 'string') return v;
  if (typeof v.text === 'string') return v.text;
  if (Array.isArray(v.value)) return v.value.map((a) => (a.name ? `${a.name} <${a.address}>` : a.address)).join(', ');
  return '';
};
const cabecalho = (json, nome) => String((json.headers || {})[nome] || '').replace(new RegExp(`^${nome}:\\s*`, 'i'), '');
const ehPdf = (nome, anexo) => nome.toLowerCase().endsWith('.pdf') || anexo.mimeType === 'application/pdf';
const ehXml = (nome, anexo) => nome.toLowerCase().endsWith('.xml') || /(^|\/)xml$/.test(String(anexo.mimeType || ''));
const saida = [];
const itens = $input.all();
for (let indice = 0; indice < itens.length; indice += 1) {
  const item = itens[indice];
  const j = item.json || {};
  const gmailMessageId = String(j.id || '').trim();
  // Item vazio (execução manual do gatilho sem mensagens): nada a processar.
  if (!gmailMessageId && !Object.keys(j).length && !item.binary) continue;
  if (!gmailMessageId) throw new Error('O Gmail não retornou o ID da mensagem; nenhum anexo será importado.');
  const base = {
    gmailMessageId,
    gmailThreadId: String(j.threadId || ''),
    assunto: String(j.subject || cabecalho(j, 'subject') || '').slice(0, 500),
    remetente: (textoEndereco(j.from) || cabecalho(j, 'from')).slice(0, 500),
    recebidaEm: String(j.date || cabecalho(j, 'date') || ''),
    corpo: String(j.text || '').replace(/\s+/g, ' ').trim().slice(0, 1500),
    origemBusca: String(j.origemBusca || 'nova'),
  };
  const pdfs = [];
  const xmls = [];
  for (const [propriedade, anexo] of Object.entries(item.binary || {})) {
    const nomeArquivo = String(anexo.fileName || `${propriedade}`);
    if (ehPdf(nomeArquivo, anexo)) {
      pdfs.push({ propriedade, anexo, nomeArquivo });
    } else if (ehXml(nomeArquivo, anexo)) {
      let texto = '';
      try { texto = (await this.helpers.getBinaryDataBuffer(indice, propriedade)).toString('utf8'); } catch (e) { texto = ''; }
      xmls.push({ propriedade, anexo, nomeArquivo, texto, lido: XmlFiscalSIGp.lerXmlFiscal(texto) });
    }
  }
  // XML de cada PDF: um XML só vale para todos os PDFs da mensagem; com vários, o número da nota no nome
  // do PDF decide e, sem pista, a ordem dos anexos. XML que sobrar entra sozinho (nada se perde).
  const validos = xmls.filter((x) => x.lido.ok);
  const usados = new Set();
  const xmlDoPdf = (pdf) => {
    if (validos.length === 1) { usados.add(validos[0]); return validos[0]; }
    const porNumero = validos.find((x) => x.lido.numero && pdf.nomeArquivo.includes(x.lido.numero));
    const escolhido = porNumero || validos.find((x) => !usados.has(x)) || null;
    if (escolhido) usados.add(escolhido);
    return escolhido;
  };
  const invalidos = xmls.filter((x) => !x.lido.ok).map((x) => `${x.nomeArquivo}: ${x.lido.erro}`);
  for (const pdf of pdfs) {
    const xml = xmlDoPdf(pdf);
    // Chave estável por mensagem + nome do anexo: reenvios são deduplicados pela API.
    saida.push({
      json: {
        ...base, semAnexo: false, soXml: false, gmailAttachmentId: `${pdf.propriedade}:${pdf.nomeArquivo}`, nomeArquivo: pdf.nomeArquivo,
        xmlTexto: xml ? xml.texto : '', xmlNomeArquivo: xml ? xml.nomeArquivo : '', xmlFiscal: xml ? xml.lido : null, xmlInvalidos: invalidos,
      },
      binary: { data: pdf.anexo },
      pairedItem: { item: indice },
    });
  }
  // XML sem PDF correspondente (ou mensagem só com XML): entra sozinho, em Revisão. XML inválido só entra
  // sozinho quando não há PDF (com PDF, ele aparece como aviso no item do PDF).
  for (const xml of xmls.filter((x) => !usados.has(x) && (x.lido.ok || !pdfs.length))) {
    saida.push({
      json: {
        ...base, semAnexo: false, soXml: true, gmailAttachmentId: `${xml.propriedade}:${xml.nomeArquivo}`, nomeArquivo: xml.nomeArquivo,
        xmlTexto: xml.texto, xmlNomeArquivo: xml.nomeArquivo, xmlFiscal: xml.lido, xmlInvalidos: [],
      },
      binary: { data: xml.anexo },
      pairedItem: { item: indice },
    });
  }
  if (!pdfs.length && !xmls.length) {
    saida.push({ json: { ...base, semAnexo: true, soXml: false, gmailAttachmentId: '', nomeArquivo: '' }, pairedItem: { item: indice } });
  }
}
return saida;
'@

$codeFaltando = @'
// Uma saída por etiqueta de controle que ainda não existe no Gmail; nenhuma faltando => item { completo: true }.
const desejadas = ['SIGp/Importado', 'SIGp/Ignorado', 'SIGp/Sem-anexo'];
const existentes = new Set($input.all().map((i) => i.json.name));
const faltando = desejadas.filter((nome) => !existentes.has(nome));
return faltando.length
  ? faltando.map((nome) => ({ json: { completo: false, nome }, pairedItem: { item: 0 } }))
  : [{ json: { completo: true }, pairedItem: { item: 0 } }];
'@

$codeRecuperar = @'
// Resolve os IDs das etiquetas de controle (existentes + criadas agora) e devolve os itens preparados.
let criadas = [];
try { criadas = $('Criar etiqueta Gmail').all().map((i) => i.json); } catch (e) { /* nada foi criado nesta execução */ }
const etiquetas = [...$('Listar etiquetas Gmail').all().map((i) => i.json), ...criadas];
const desejadas = { importado: 'SIGp/Importado', ignorado: 'SIGp/Ignorado', semAnexo: 'SIGp/Sem-anexo' };
const ids = {};
const faltando = [];
for (const [chave, nome] of Object.entries(desejadas)) {
  const encontrada = etiquetas.find((e) => e.name === nome);
  if (encontrada) ids[chave] = encontrada.id; else faltando.push(nome);
}
if (faltando.length) {
  throw new Error(`Não foi possível criar no Gmail as etiquetas ${faltando.join(', ')}. Crie-as manualmente na conta conectada ao n8n.`);
}
return $('Preparar anexos PDF').all().map((i) => ({ json: { ...i.json, etiquetas: ids }, binary: i.binary, pairedItem: { item: 0 } }));
'@

$codeExtrair = $libCode + @'

// ---- nó: Extrair campos e montar pedido à IA ----
const origem = $('Recuperar itens e etiquetas').item;
const ocr = $('OCR local').item.json || {};
const texto = String(ocr.text || '');
let modelo = 'qwen2.5:3b';
try { modelo = $env.SIGP_OLLAMA_MODEL || modelo; } catch (e) { /* acesso a $env bloqueado: usa o padrão */ }
// Memória de exemplos (etapa 4); falha na busca = segue sem exemplos.
const exemplos = Array.isArray($json.exemplos) ? $json.exemplos.slice(0, 8) : [];
return {
  json: {
    ...origem.json,
    ocrUsado: Boolean(ocr.ocrUsado),
    caracteresTexto: texto.trim().length,
    ocrErro: ocr.error ? String(ocr.error.message || ocr.error).slice(0, 300) : '',
    regras: $('Classificar com regras do SIGp').item.json.classificacao || {},
    extracao: extrairCampos(texto),
    exemplosUsados: exemplos.map((e) => e.id),
    modelo,
    ollamaBody: {
      model: modelo,
      stream: false,
      format: SCHEMA,
      // num_predict: proteção contra resposta sem fim (o 3B chegou a escrever o motivo por 700 tokens). O schema também limita
      // cada texto (maxLength): medido em tests/n8n/comparar_modelos_triagem.js, variante corrigido.
      options: { temperature: 0, num_ctx: 4096, num_predict: 400 },
      messages: montarMensagensIA(origem.json, texto, exemplos),
    },
  },
  binary: origem.binary,
};
'@

$codeConsolidar = $libCode + @'

// ---- nó: Consolidar decisão ----
const origem = $('Extrair campos e montar pedido à IA').item;
const { ia, erro } = lerRespostaIA($json);
const r = consolidar({
  ia, iaErro: erro, regras: origem.json.regras, ext: origem.json.extracao,
  meta: origem.json, modelo: origem.json.modelo, ocrUsado: origem.json.ocrUsado,
  caracteresTexto: origem.json.soXml ? undefined : origem.json.caracteresTexto,
  texto: origem.json.soXml ? undefined : String($('OCR local').item.json.text || ''),
});
if (origem.json.ocrErro && !origem.json.soXml) {
  r.decisao = 'importar';
  r.dadosExtracao.revisaoManual = true;
  r.dadosExtracao.camposParaRevisar.push('ocr');
  r.dadosExtracao.classificacao.ocrErro = origem.json.ocrErro;
}
// XML da nota fiscal: tem prioridade nos campos fiscais; documento com XML nunca é ignorado.
const xml = origem.json.xmlFiscal;
if (xml && xml.ok) {
  r.decisao = 'importar';
  const classificacao = r.dadosExtracao.classificacao;
  r.dadosExtracao = { ...XmlFiscalSIGp.aplicarPrioridadeXml(r.dadosExtracao, xml), classificacao, xmlFiscal: xml };
}
if (origem.json.soXml) {
  r.decisao = 'importar';
  r.dadosExtracao.camposParaRevisar = r.dadosExtracao.camposParaRevisar
    .filter((c) => !['ocr', 'classificacaoIA', 'tipoDocumento', 'confianca'].includes(c));
}
if ((origem.json.xmlInvalidos || []).length) {
  r.dadosExtracao.classificacao.xmlInvalidos = origem.json.xmlInvalidos;
  if (!r.dadosExtracao.camposParaRevisar.includes('xml')) r.dadosExtracao.camposParaRevisar.push('xml');
}
r.dadosExtracao.revisaoManual = r.dadosExtracao.camposParaRevisar.length > 0;
// Triagem (etapa 2): todo documento vai para o SIGp com o veredito da IA. Ignorados ficam na fila própria
// "Ignorados pela IA"; o resumo por execução usa execucaoId.
let execucaoId = '';
try { execucaoId = String($execution.id || ''); } catch (e) { /* execução de teste */ }
const prob = probabilidadeFinal(r.dadosExtracao, r.probabilidade, r.motivoProbabilidade,
  { ocrErro: Boolean(origem.json.ocrErro && !origem.json.soXml), xml: Boolean(xml && xml.ok) });
if (r.decisao !== 'ignorar') r.autoDescarte = false;
r.dadosExtracao.decisaoIA = r.decisao;
r.dadosExtracao.classificacao.ia.exemplosUsados = origem.json.exemplosUsados || [];
// Painel da IA: tempo e tokens da chamada (o Ollama devolve em nanossegundos).
r.dadosExtracao.classificacao.ia.duracaoMs = Math.round(Number($json.total_duration || 0) / 1e6) || null;
r.dadosExtracao.classificacao.ia.tokens = Number($json.eval_count || 0) + Number($json.prompt_eval_count || 0) || null;
r.dadosExtracao.triagem = {
  decisao: r.decisao,
  execucaoId,
  origemBusca: origem.json.origemBusca || '',
  em: new Date().toISOString(),
  tipoDocumento: r.dadosExtracao.tipoDocumento,
  confianca: r.dadosExtracao.classificacao?.ia?.confianca ?? null,
  motivo: r.dadosExtracao.classificacao?.ia?.motivo || '',
  // Três níveis: alta (internet), baixa (não é cobrança: revisão ou descarte automático), inconclusivo.
  probabilidade: prob.probabilidade,
  motivoProbabilidade: prob.motivo,
  autoDescarte: Boolean(r.autoDescarte),
};
const { ollamaBody, extracao, regras, ...meta } = origem.json;
return { json: { ...meta, decisao: r.decisao, dadosExtracao: r.dadosExtracao }, binary: origem.binary };
'@

function Add-Label($id, $name, $x, $y, $msgExpr, $labelExpr, $notes) {
  @{
    parameters = @{ resource = 'message'; operation = 'addLabels'; messageId = $msgExpr; labelIds = @($labelExpr) }
    id = $id; name = $name; type = 'n8n-nodes-base.gmail'; typeVersion = 2.2; position = @($x, $y)
    credentials = $gmailCred; onError = 'continueRegularOutput'; notes = $notes
  }
}

$nodes = @(
  @{
    parameters = @{ rule = @{ interval = @(@{ field = 'minutes'; minutesInterval = 5 }) } }
    id = 'wf08_schedule'; name = 'A cada 5 minutos'; type = 'n8n-nodes-base.scheduleTrigger'; typeVersion = 1.2
    position = @(-440, 300)
    notes = 'Substitui o gatilho do Gmail, que só aceita busca fixa: assim os remetentes mudam pelo SIGp. Gerado por n8n/wf08/build_wf08.ps1.'
  },
  (& $buscaSigp 'wf08_busca_sigp' 'Busca do SIGp' -220 300),
  @{
    parameters = @{ mode = 'runOnceForAllItems'; jsCode = $codeJanela }
    id = 'wf08_janela'; name = 'Janela desde a última leitura'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(0, 300)
  },
  @{
    parameters = @{
      resource = 'message'; operation = 'getAll'; returnAll = $false; limit = 50; simple = $false
      filters = @{ q = '={{ $json.q }}'; readStatus = 'both' }
      options = @{ downloadAttachments = $true; dataPropertyAttachmentsPrefixName = 'attachment_' }
    }
    id = 'wf08_gmail_novas'; name = 'Gmail - novas faturas'; type = 'n8n-nodes-base.gmail'; typeVersion = 2.2
    position = @(220, 300); credentials = $gmailCred; alwaysOutputData = $true
    notes = 'Lidas e não lidas, sem as etiquetas SIGp/Importado, SIGp/Ignorado e SIGp/Sem-anexo. Até 50 por leitura; o excedente entra pela busca histórica.'
  },
  @{
    parameters = @{ mode = 'runOnceForAllItems'; jsCode = $codeRetirar }
    id = 'wf08_retirar_lidas'; name = 'Retirar mensagens já lidas'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(440, 300)
  },
  @{
    parameters = @{}; id = 'wf08_manual_backfill'; name = 'Executar busca histórica manual'
    type = 'n8n-nodes-base.manualTrigger'; typeVersion = 1; position = @(-220, 520)
    notes = 'Processa 20 mensagens por execução. Como cada mensagem recebe etiqueta, a próxima execução avança no histórico.'
  },
  (& $buscaSigp 'wf08_busca_sigp_historico' 'Busca do SIGp (histórico)' 0 520),
  @{
    parameters = @{
      resource = 'message'; operation = 'getAll'; returnAll = $false; limit = 20; simple = $false
      filters = @{ q = '={{ $json.consulta }}'; readStatus = 'both' }
      options = @{ downloadAttachments = $true; dataPropertyAttachmentsPrefixName = 'attachment_' }
    }
    id = 'wf08_gmail_search_history'; name = 'Gmail - buscar histórico'; type = 'n8n-nodes-base.gmail'; typeVersion = 2.2
    position = @(220, 520); credentials = $gmailCred
  },
  @{
    parameters = @{ mode = 'runOnceForAllItems'; jsCode = "return `$input.all().map(item => ({ json: { ...item.json, origemBusca: 'retroativa' }, binary: item.binary }));" }
    id = 'wf08_mark_historical'; name = 'Identificar busca retroativa'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(440, 520)
  },
  @{
    parameters = @{ inputSource = 'passthrough' }
    id = 'wf08_reprocess_trigger'; name = 'Reprocessamento (chamado pelo utilitário)'; type = 'n8n-nodes-base.executeWorkflowTrigger'; typeVersion = 1.1
    position = @(220, 720)
    notes = 'Recebe mensagens do utilitário "Reprocessar mensagens": nenhuma etiqueta é removida. A API só atualiza notas ainda não associadas.'
  },
  @{
    parameters = @{ mode = 'runOnceForAllItems'; jsCode = "return `$input.all().map(item => ({ json: { ...item.json, origemBusca: 'reprocessamento' }, binary: item.binary }));" }
    id = 'wf08_mark_reprocess'; name = 'Identificar reprocessamento'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(440, 720)
  },
  @{
    parameters = @{ mode = 'runOnceForAllItems'; jsCode = $codePreparar }
    id = 'wf08_prepare_attachments'; name = 'Preparar anexos PDF'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(660, 300)
  },
  @{
    parameters = @{ resource = 'label'; operation = 'getAll'; returnAll = $true }
    id = 'wf08_list_labels'; name = 'Listar etiquetas Gmail'; type = 'n8n-nodes-base.gmail'; typeVersion = 2.2
    position = @(880, 300); credentials = $gmailCred; executeOnce = $true
  },
  @{
    parameters = @{ mode = 'runOnceForAllItems'; jsCode = $codeFaltando }
    id = 'wf08_missing_labels'; name = 'Etiquetas faltando'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(1000, 440)
  },
  @{
    parameters = @{
      conditions = @{
        options = @{ caseSensitive = $true; leftValue = ''; typeValidation = 'strict'; version = 2 }
        conditions = @(@{ id = 'wf08_cond_labels'; leftValue = '={{ $json.completo }}'; rightValue = $false; operator = @{ type = 'boolean'; operation = 'equals' } })
        combinator = 'and'
      }
      options = @{}
    }
    id = 'wf08_need_labels'; name = 'Precisa criar etiqueta?'; type = 'n8n-nodes-base.if'; typeVersion = 2.2; position = @(1120, 440)
  },
  @{
    parameters = @{
      resource = 'label'; operation = 'create'; name = '={{ $json.nome }}'
      options = @{ labelListVisibility = 'labelShow'; messageListVisibility = 'show' }
    }
    id = 'wf08_create_label'; name = 'Criar etiqueta Gmail'; type = 'n8n-nodes-base.gmail'; typeVersion = 2.2
    position = @(1240, 560); credentials = $gmailCred; onError = 'continueRegularOutput'
    notes = 'Cria SIGp/Importado, SIGp/Ignorado e SIGp/Sem-anexo na primeira execução, se não existirem.'
  },
  @{
    parameters = @{ mode = 'runOnceForAllItems'; jsCode = $codeRecuperar }
    id = 'wf08_restore_items'; name = 'Recuperar itens e etiquetas'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(1260, 300)
  },
  @{
    parameters = @{
      conditions = @{
        options = @{ caseSensitive = $true; leftValue = ''; typeValidation = 'strict'; version = 2 }
        conditions = @(@{ id = 'wf08_cond_pdf'; leftValue = '={{ $json.semAnexo }}'; rightValue = $false; operator = @{ type = 'boolean'; operation = 'equals' } })
        combinator = 'and'
      }
      options = @{}
    }
    id = 'wf08_has_pdf'; name = 'Tem PDF?'; type = 'n8n-nodes-base.if'; typeVersion = 2.2; position = @(1320, 300)
  },
  @{
    parameters = @{ batchSize = 1; options = @{} }
    id = 'wf08_loop'; name = 'Um PDF por vez'; type = 'n8n-nodes-base.splitInBatches'; typeVersion = 3; position = @(1420, 120)
    notes = 'O OCR local e o Ollama em CPU atendem um pedido por vez. Em paralelo, o OCR devolve 503 e o Ollama estoura o tempo.'
  },
  @{
    parameters = @{
      method = 'POST'; url = 'http://ocr:5002/extract'; sendBody = $true; contentType = 'binaryData'; inputDataFieldName = 'data'
      options = @{ timeout = 420000 }
    }
    id = 'wf08_ocr_pdf'; name = 'OCR local'; type = 'n8n-nodes-base.httpRequest'; typeVersion = 4.2; position = @(1540, 200)
    onError = 'continueRegularOutput'; retryOnFail = $true; maxTries = 3; waitBetweenTries = 5000
  },
  @{
    parameters = @{
      method = 'POST'; url = "={{ `$env.SIGP_API_URL + '/api/notas-recebidas/classificar' }}"
      sendHeaders = $true; headerParameters = $apiHeaders; sendBody = $true; contentType = 'json'; specifyBody = 'json'
      jsonBody = "={{ JSON.stringify({ texto: String(`$('OCR local').item.json.text || ''), assunto: `$('Recuperar itens e etiquetas').item.json.assunto, remetente: `$('Recuperar itens e etiquetas').item.json.remetente, nomeArquivo: `$('Recuperar itens e etiquetas').item.json.nomeArquivo, corpo: `$('Recuperar itens e etiquetas').item.json.corpo || '' }) }}"
      options = @{ timeout = 30000 }
    }
    id = 'wf08_classify_rules'; name = 'Classificar com regras do SIGp'; type = 'n8n-nodes-base.httpRequest'; typeVersion = 4.2
    position = @(1760, 200); onError = 'continueRegularOutput'
    notes = 'Termos fiscais/internet, nomes de provedores e e-mail do remetente cadastrado no provedor.'
  },
  @{
    parameters = @{
      method = 'GET'; url = "={{ `$env.SIGP_API_URL + '/api/llm/exemplos' }}"
      sendHeaders = $true; headerParameters = $apiHeaders
      sendQuery = $true
      queryParameters = @{ parameters = @(
        @{ name = 'remetente'; value = "={{ `$('Recuperar itens e etiquetas').item.json.remetente }}" },
        @{ name = 'assunto'; value = "={{ `$('Recuperar itens e etiquetas').item.json.assunto }}" },
        @{ name = 'limite'; value = '4' }
      ) }
      options = @{ timeout = 15000 }
    }
    id = 'wf08_examples'; name = 'Buscar exemplos no SIGp'; type = 'n8n-nodes-base.httpRequest'; typeVersion = 4.2
    position = @(1870, 360); onError = 'continueRegularOutput'
    notes = 'Memória de exemplos: decisões do operador em documentos parecidos. Falha = segue sem exemplos.'
  },
  @{
    parameters = @{ mode = 'runOnceForEachItem'; jsCode = $codeExtrair }
    id = 'wf08_extract'; name = 'Extrair campos e montar pedido à IA'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(1980, 200)
    notes = 'Linha digitável, CNPJs, datas e valores por regras; monta o pedido ao Qwen com o JSON Schema.'
  },
  @{
    parameters = @{
      method = 'POST'; url = "={{ (`$env.SIGP_OLLAMA_URL || 'http://ollama:11434') + '/api/chat' }}"
      sendBody = $true; contentType = 'json'; specifyBody = 'json'; jsonBody = '={{ JSON.stringify($json.ollamaBody) }}'
      options = @{ timeout = 300000 }
    }
    id = 'wf08_ollama'; name = 'Classificar com Qwen (Ollama local)'; type = 'n8n-nodes-base.httpRequest'; typeVersion = 4.2
    position = @(2200, 200); onError = 'continueRegularOutput'
    notes = 'Modelo local (padrão qwen2.5:3b). O texto não sai da rede Docker. Falha ou timeout => item vai para Revisão.'
  },
  @{
    parameters = @{ mode = 'runOnceForEachItem'; jsCode = $codeConsolidar }
    id = 'wf08_consolidate'; name = 'Consolidar decisão'; type = 'n8n-nodes-base.code'; typeVersion = 2; position = @(2420, 200)
    notes = 'IA sugere; valor/vencimento do boleto prevalecem. Ignora só com IA segura + regras sem evidência + sem boleto.'
  },
  @{
    parameters = @{
      conditions = @{
        options = @{ caseSensitive = $true; leftValue = ''; typeValidation = 'strict'; version = 2 }
        conditions = @(@{ id = 'wf08_cond_ignore'; leftValue = "={{ `$('Consolidar decisão').item.json.decisao }}"; rightValue = 'ignorar'; operator = @{ type = 'string'; operation = 'equals' } })
        combinator = 'and'
      }
      options = @{}
    }
    id = 'wf08_should_ignore'; name = 'Ignorar documento?'; type = 'n8n-nodes-base.if'; typeVersion = 2.2; position = @(2640, 200)
  },
  @{
    parameters = @{
      method = 'POST'; url = "={{ `$env.SIGP_API_URL + '/api/notas-recebidas' }}"
      sendHeaders = $true; headerParameters = $apiHeaders; sendBody = $true; contentType = 'multipart-form-data'
      bodyParameters = @{ parameters = @(
        @{ parameterType = 'formData'; name = 'gmailMessageId'; value = '={{ $json.gmailMessageId }}' },
        @{ parameterType = 'formData'; name = 'gmailAttachmentId'; value = '={{ $json.gmailAttachmentId }}' },
        @{ parameterType = 'formData'; name = 'gmailThreadId'; value = '={{ $json.gmailThreadId }}' },
        @{ parameterType = 'formData'; name = 'assunto'; value = '={{ $json.assunto }}' },
        @{ parameterType = 'formData'; name = 'remetente'; value = '={{ $json.remetente }}' },
        @{ parameterType = 'formData'; name = 'recebidaEm'; value = '={{ $json.recebidaEm }}' },
        @{ parameterType = 'formData'; name = 'corpo'; value = '={{ $json.corpo || "" }}' },
        @{ parameterType = 'formData'; name = 'dadosExtracao'; value = '={{ JSON.stringify($json.dadosExtracao) }}' },
        @{ parameterType = 'formData'; name = 'xmlConteudo'; value = "={{ `$json.soXml ? '' : (`$json.xmlTexto || '') }}" },
        @{ parameterType = 'formData'; name = 'xmlNomeArquivo'; value = '={{ $json.xmlNomeArquivo || "" }}' },
        @{ parameterType = 'formBinaryData'; name = 'arquivo'; inputDataFieldName = 'data' }
      ) }
      options = @{ timeout = 60000 }
    }
    id = 'wf08_save_api'; name = 'Salvar na caixa SIGp'; type = 'n8n-nodes-base.httpRequest'; typeVersion = 4.2
    position = @(2860, 300); onError = 'continueErrorOutput'
    notes = 'Sempre grava (Revisão ou Aguardando associação). Em erro, a mensagem fica sem etiqueta e volta na próxima busca histórica.'
  },
  (Add-Label 'wf08_label_imported' 'Etiquetar SIGp/Importado' 3080 260 "={{ `$('Consolidar decisão').item.json.gmailMessageId }}" "={{ `$('Consolidar decisão').item.json.etiquetas.importado }}" 'Só após a API confirmar a gravação. A mensagem continua na caixa de entrada.'),
  (Add-Label 'wf08_label_ignored' 'Etiquetar SIGp/Ignorado' 3080 100 "={{ `$('Consolidar decisão').item.json.gmailMessageId }}" "={{ `$('Consolidar decisão').item.json.etiquetas.ignorado }}" 'O documento já está no SIGp, na fila "Ignorados pela IA", para revisão. Nada é apagado.'),
  @{
    parameters = @{
      method = 'POST'; url = "={{ `$env.SIGP_API_URL + '/api/notas-recebidas/aviso' }}"
      sendHeaders = $true; headerParameters = $apiHeaders; sendBody = $true; contentType = 'json'; specifyBody = 'json'
      jsonBody = '={{ JSON.stringify({ gmailMessageId: $json.gmailMessageId, gmailThreadId: $json.gmailThreadId, assunto: $json.assunto, remetente: $json.remetente, recebidaEm: $json.recebidaEm, corpo: $json.corpo }) }}'
      options = @{ timeout = 60000 }
    }
    id = 'wf08_aviso_sem_anexo'; name = 'Registrar aviso sem anexo'; type = 'n8n-nodes-base.httpRequest'; typeVersion = 4.2
    position = @(1540, 420); onError = 'continueRegularOutput'
    notes = 'Situação 1: pagamento confirmado, atraso ou lembrete sem PDF. O SIGp vincula à cobrança (e registra o pagamento). Fatura nova sem PDF não entra.'
  },
  (Add-Label 'wf08_label_no_pdf' 'Etiquetar SIGp/Sem-anexo' 1760 420 "={{ `$('Recuperar itens e etiquetas').item.json.gmailMessageId }}" "={{ `$('Recuperar itens e etiquetas').item.json.etiquetas.semAnexo }}" 'Sem PDF: avisos já foram ao SIGp; fatura por link ou aplicativo fica visível no Gmail para tratamento manual.')
)

$conn = {
  param($targets)
  @{ main = @(, @($targets | ForEach-Object { @{ node = $_; type = 'main'; index = 0 } })) }
}
$connections = [ordered]@{
  'A cada 5 minutos' = (& $conn 'Busca do SIGp')
  'Busca do SIGp' = (& $conn 'Janela desde a última leitura')
  'Janela desde a última leitura' = (& $conn 'Gmail - novas faturas')
  'Gmail - novas faturas' = (& $conn 'Retirar mensagens já lidas')
  'Retirar mensagens já lidas' = (& $conn 'Preparar anexos PDF')
  'Executar busca histórica manual' = (& $conn 'Busca do SIGp (histórico)')
  'Busca do SIGp (histórico)' = (& $conn 'Gmail - buscar histórico')
  'Gmail - buscar histórico' = (& $conn 'Identificar busca retroativa')
  'Identificar busca retroativa' = (& $conn 'Preparar anexos PDF')
  'Reprocessamento (chamado pelo utilitário)' = (& $conn 'Identificar reprocessamento')
  'Identificar reprocessamento' = (& $conn 'Preparar anexos PDF')
  'Preparar anexos PDF' = (& $conn 'Listar etiquetas Gmail')
  'Listar etiquetas Gmail' = (& $conn 'Etiquetas faltando')
  'Etiquetas faltando' = (& $conn 'Precisa criar etiqueta?')
  'Precisa criar etiqueta?' = @{ main = @(
    @(@{ node = 'Criar etiqueta Gmail'; type = 'main'; index = 0 }),
    @(@{ node = 'Recuperar itens e etiquetas'; type = 'main'; index = 0 })
  ) }
  'Criar etiqueta Gmail' = (& $conn 'Recuperar itens e etiquetas')
  'Recuperar itens e etiquetas' = (& $conn 'Tem PDF?')
  'Tem PDF?' = @{ main = @(
    @(@{ node = 'Um PDF por vez'; type = 'main'; index = 0 }),
    @(@{ node = 'Registrar aviso sem anexo'; type = 'main'; index = 0 })
  ) }
  'Registrar aviso sem anexo' = (& $conn 'Etiquetar SIGp/Sem-anexo')
  # Saída 0 = concluído (fim); saída 1 = próximo PDF.
  'Um PDF por vez' = @{ main = @(
    @(),
    @(@{ node = 'OCR local'; type = 'main'; index = 0 })
  ) }
  'OCR local' = (& $conn 'Classificar com regras do SIGp')
  'Classificar com regras do SIGp' = (& $conn 'Buscar exemplos no SIGp')
  'Buscar exemplos no SIGp' = (& $conn 'Extrair campos e montar pedido à IA')
  'Extrair campos e montar pedido à IA' = (& $conn 'Classificar com Qwen (Ollama local)')
  'Classificar com Qwen (Ollama local)' = (& $conn 'Consolidar decisão')
  # Etapa 2 (triagem): todo documento é gravado no SIGp; a decisão da IA só escolhe a etiqueta e a fila.
  'Consolidar decisão' = (& $conn 'Salvar na caixa SIGp')
  'Salvar na caixa SIGp' = @{ main = @(
    @(@{ node = 'Ignorar documento?'; type = 'main'; index = 0 }),
    @(@{ node = 'Um PDF por vez'; type = 'main'; index = 0 })
  ) }
  'Ignorar documento?' = @{ main = @(
    @(@{ node = 'Etiquetar SIGp/Ignorado'; type = 'main'; index = 0 }),
    @(@{ node = 'Etiquetar SIGp/Importado'; type = 'main'; index = 0 })
  ) }
  # Fim de cada PDF volta ao laço.
  'Etiquetar SIGp/Importado' = (& $conn 'Um PDF por vez')
  'Etiquetar SIGp/Ignorado' = (& $conn 'Um PDF por vez')
}

# Conferência: toda conexão aponta para um nó existente.
$names = $nodes | ForEach-Object { $_.name }
foreach ($src in $connections.Keys) {
  if ($names -notcontains $src) { throw "Conexão sai de nó inexistente: $src" }
  foreach ($out in $connections[$src].main) { foreach ($t in $out) { if ($t -and $names -notcontains $t.node) { throw "Conexão aponta para nó inexistente: $($t.node)" } } }
}

$workflow = [ordered]@{
  id = '5sQcHD7eYRgHxqgK'
  name = 'WF-08 - Receber notas fiscais do Gmail'
  nodes = $nodes
  connections = $connections
  active = $false
  settings = @{ executionOrder = 'v1'; saveManualExecutions = $true; callerPolicy = 'workflowsFromSameOwner'; errorWorkflow = 'sigpWF99Erros000' }
  versionId = 'wf08-v2-ia-local'
  meta = @{ templateCredsSetupCompleted = $true }
  tags = @()
}
$out = Join-Path $root 'n8n_workflow_wf08_gmail_inbox.json'
$workflow | ConvertTo-Json -Depth 30 | Set-Content -Path $out -Encoding utf8NoBOM
Write-Host "Gerado: $out ($($nodes.Count) nós)"




