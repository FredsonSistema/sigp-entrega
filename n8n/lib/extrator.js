// Extrator de campos de fatura/boleto/NFS-e a partir do texto do OCR (fase B-01).
//
// Porte fiel de backend/app.py (_extract_invoice_fields e POST /api/extracao/texto) e de
// backend/campos.py (valor padrão 999999999 para número/chave vazios ou inválidos).
// No destino, a extração roda no n8n; o backend fica como contingência (n8n fora do ar).
// Paridade conferida por tests/n8n/paridade_extrator.py sobre os textos OCR da base de teste.
//
// Uso:
//   - Node (testes):  const X = require('./extrator.js'); X.extrairDoTexto({ texto })
//   - n8n (nó Code):  os scripts de build colam este arquivo no início do nó; use ExtratorSIGp.*
// Tudo fica dentro de ExtratorSIGp para não colidir com outras bibliotecas coladas no mesmo nó.
// Não grava nada e não acessa rede.

const ExtratorSIGp = (() => {
  const VERSAO = 'n8n_lib_extrator_v2';
  // Versão das regras (mesma de backend/app.py, REGRAS_EXTRACAO_VERSAO). Suba as duas juntas.
  const VERSAO_REGRAS = 2;
  const VALOR_PADRAO = '999999999';
  const TAMANHOS_CHAVE = [44, 50]; // NF-e/NFCom: 44 dígitos; NFS-e nacional: 50
  const EMPRESAS_DO_GRUPO = ['ROTA TRANSPORTE', 'VIACAO JEQUIE', 'EXPRESSO BRASILEIRO']; // pagadoras; nunca emissoras

  // ---------- equivalências com o Python ----------
  // \b do Python é Unicode (º, ã, ç contam como letra); o do JS é só ASCII. Emulado com lookarounds.
  const W = '[\\p{L}\\p{N}_]';
  const B = `(?:(?<=${W})(?!${W})|(?<!${W})(?=${W}))`;
  const cache = new Map();
  function re(fonte, flags = '') {
    const chave = `${flags}|${fonte}`;
    if (!cache.has(chave)) cache.set(chave, new RegExp(fonte.replace(/\\b/g, B), `${flags}u`));
    return cache.get(chave);
  }
  // str.splitlines() do Python (inclui \f entre páginas do pdftotext; sem a linha vazia final).
  function splitlines(texto) {
    if (!texto) return [];
    const partes = texto.split(/\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/);
    if (partes[partes.length - 1] === '') partes.pop();
    return partes;
  }
  const PY_ESPACO = ' \t\n\r\v\f\x1c\x1d\x1e\x1f\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000';
  // str.strip([chars]) do Python.
  function strip(valor, chars = PY_ESPACO) {
    const s = String(valor);
    let ini = 0;
    let fim = s.length;
    while (ini < fim && chars.includes(s[ini])) ini += 1;
    while (fim > ini && chars.includes(s[fim - 1])) fim -= 1;
    return s.slice(ini, fim);
  }
  const lstrip = (s) => { let i = 0; while (i < s.length && PY_ESPACO.includes(s[i])) i += 1; return s.slice(i); };
  // float() do Python: recusa texto vazio ou com lixo (Number('') seria 0).
  function pyFloat(valor) {
    if (typeof valor === 'number') return Number.isFinite(valor) ? valor : null;
    const s = strip(String(valor ?? ''));
    if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(s)) return null;
    return Number(s);
  }
  const unicos = (lista) => [...new Set(lista)];
  const soDigitos = (v) => String(v ?? '').replace(/\D/g, '');

  function normalizarNomeEmpresa(valor) {
    return String(valor ?? '').toLowerCase().replace(/ß/g, 'ss').normalize('NFKD')
      .replace(/\p{Mn}/gu, '').replace(/[^a-z0-9]/g, '');
  }
  const semAcentoMaiusculo = (v) => String(v ?? '').normalize('NFKD').replace(/\p{Mn}/gu, '').toUpperCase();

  // ---------- campos.py ----------
  const CNPJ_RE = /^\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}$/;
  const CPF_RE = /^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$/;
  const DATA_RE = /^\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}$/;
  const DINHEIRO_RE = /^(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}$|^R\$/;
  const NUMERO_VALIDO_RE = /^[A-Za-z0-9][A-Za-z0-9./-]{0,29}$/;

  const ehPadrao = (v) => strip(String(v ?? '')) === VALOR_PADRAO;

  function motivoNumeroInvalido(valor) {
    const texto = strip(String(valor || ''));
    if (!texto) return 'vazio';
    if (texto === VALOR_PADRAO) return '';
    if (!/\d/.test(texto)) return 'sem dígitos (provável rótulo)';
    if (/^0+$/.test(soDigitos(texto)) && !/[1-9]/.test(texto)) return 'só zeros';
    const compacto = texto.replace(/ /g, '');
    if (CNPJ_RE.test(compacto) || CPF_RE.test(compacto)) return 'parece CNPJ/CPF';
    if (DATA_RE.test(compacto)) return 'parece uma data';
    if (DINHEIRO_RE.test(compacto)) return 'parece um valor em dinheiro';
    if (!NUMERO_VALIDO_RE.test(compacto)) return 'formato fora do esperado';
    return '';
  }

  function motivoChaveInvalida(valor) {
    const texto = String(valor || '').replace(/\s+/g, '');
    if (!texto) return 'vazia';
    if (texto === VALOR_PADRAO) return '';
    const digitos = soDigitos(texto);
    if (digitos !== texto) return 'contém caracteres que não são dígitos';
    if (!TAMANHOS_CHAVE.includes(digitos.length)) return `tamanho ${digitos.length} (esperado ${TAMANHOS_CHAVE.join(' ou ')})`;
    return '';
  }

  // Número/chave vazios ou inválidos recebem 999999999; o texto rejeitado fica em *Original/*Motivo.
  function aplicarPadraoIdentificacao(campos) {
    const revisar = [...(campos.camposParaRevisar || [])];
    for (const [campo, motivoFn] of [['numero', motivoNumeroInvalido], ['chave', motivoChaveInvalida]]) {
      const atual = strip(String(campos[campo] || ''));
      if (atual === VALOR_PADRAO) {
        campos[`${campo}Padrao`] = true;
        if (campo === 'numero' && !revisar.includes(campo)) revisar.push(campo);
        continue;
      }
      const motivo = motivoFn(atual);
      if (campo === 'chave' && atual && motivo) {
        // A chave lida tem prioridade; o padrão só entra quando não há chave (decisão do usuário, 14/11/2026).
        campos[campo] = atual;
        campos[`${campo}Padrao`] = false;
        campos[`${campo}Motivo`] = motivo;
        continue;
      }
      if (motivo) {
        if (atual) {
          campos[`${campo}Original`] = atual.slice(0, 160);
          campos[`${campo}Motivo`] = motivo;
        }
        campos[campo] = VALOR_PADRAO;
        campos[`${campo}Padrao`] = true;
        // Chave vazia é normal em boleto: só vai para revisão quando algo foi lido e rejeitado.
        if ((atual || campo === 'numero') && !revisar.includes(campo)) revisar.push(campo);
      } else {
        campos[campo] = atual;
        campos[`${campo}Padrao`] = false;
      }
    }
    campos.camposParaRevisar = revisar.filter((item) => item !== 'numero/chave');
    return campos;
  }

  // ---------- datas ----------
  function dataIso(ano, mes, dia) {
    const d = new Date(Date.UTC(ano, mes - 1, dia));
    if (ano < 1 || d.getUTCFullYear() !== ano || d.getUTCMonth() !== mes - 1 || d.getUTCDate() !== dia) return '';
    return `${String(ano).padStart(4, '0')}-${String(mes).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;
  }
  // _parse_ocr_date: dd/mm/aaaa, dd-mm-aaaa, dd.mm.aaaa ou aaaa-mm-dd (ignora o horário depois do espaço).
  const DIA = '(3[01]|[12]\\d|0[1-9]|[1-9])';
  const MES = '(1[0-2]|0[1-9]|[1-9])';
  const FORMATOS_BR = ['/', '-', '.'].map((sep) => new RegExp(`^${DIA}\\${sep}${MES}\\${sep}(\\d{4})$`));
  const FORMATO_ISO = new RegExp(`^(\\d{4})-${MES}-${DIA}$`);
  function parseDataOcr(valor) {
    const primeiro = strip(String(valor ?? '')).split(/\s+/)[0] || '';
    for (const formato of FORMATOS_BR) {
      const m = primeiro.match(formato);
      if (m) { const iso = dataIso(+m[3], +m[2], +m[1]); if (iso) return iso; }
    }
    const m = primeiro.match(FORMATO_ISO);
    return m ? dataIso(+m[1], +m[2], +m[3]) : '';
  }

  // ---------- leitura por coluna (boleto) ----------
  // Rótulo numa linha e valor alinhado na linha seguinte.
  function colunaDe(texto, padraoRotulo) {
    const linhas = texto.split('\n');
    const rotulo = re(padraoRotulo, 'i');
    for (let i = 0; i < linhas.length - 1; i += 1) {
      const m = linhas[i].match(rotulo);
      if (!m) continue;
      const proxima = linhas[i + 1];
      if (!strip(proxima)) continue;
      const ini = m.index;
      const fim = m.index + m[0].length;
      const resto = strip(linhas[i].slice(fim));
      if (resto.length < 5) { // rótulo é o último campo: pega o último token
        const tokens = strip(proxima).split(/\s{2,}/).map((t) => strip(t)).filter(Boolean);
        if (tokens.length) return tokens[tokens.length - 1];
      }
      const janela = proxima.slice(Math.max(0, ini - 5), fim + 50);
      const tokens = lstrip(janela).split(/\s{2,}/).map((t) => strip(t)).filter(Boolean);
      if (tokens.length) return tokens[0];
    }
    return '';
  }
  function colunaData(texto, padraoRotulo) {
    const valor = colunaDe(texto, padraoRotulo);
    const m = valor.match(/\d{2}[/.-]\d{2}[/.-]\d{4}/);
    return m ? m[0] : valor;
  }

  // Linha digitável do boleto (47 dígitos): valor e vencimento. Fator 1000 = 22/02/2025 (Febraban).
  function lerLinhaDigitavel(texto) {
    const m = String(texto || '').match(/(\d{5}[.\s]?\d{5}\s+\d{5}[.\s]?\d{6}\s+\d{5}[.\s]?\d{6}\s+\d\s+\d{14})/);
    if (!m) return { linhaDigitavel: '', valor: null, vencimento: '' };
    const d = soDigitos(m[1]);
    if (d.length !== 47) return { linhaDigitavel: '', valor: null, vencimento: '' };
    const fator = Number(d.slice(33, 37));
    const valor = Number(d.slice(37)) / 100;
    const vencimento = fator >= 1000
      ? new Date(Date.UTC(2025, 1, 22) + (fator - 1000) * 86400000).toISOString().slice(0, 10)
      : '';
    return { linhaDigitavel: d, valor: valor > 0 ? Math.round(valor * 100) / 100 : null, vencimento };
  }

  // ---------- emissor ----------
  const ROTULO = String.raw`^(ag[eê]ncia|c[oó]digo|prestador|fornecedor|benefici[aá]rio|cedente|emitente|danfe\w*|nfs-?e|raz[aã]o social|nome(\s*/\s*nome empresarial)?|cnpj|cpf|endere[cç]o|documento|n[º°o]\.?|s[eé]rie|data|vencimento|valor|tomador|destinat[aá]rio|pagador|sacado|cliente|referente|fatura|nota fiscal|\(\+\)|\(=\)|\(-\))\b`;
  const EMPRESA = String.raw`\b(ltda|ltd|s\s*/\s*a|s\.a\.?|eireli|me|epp|mei)\b\.?`;
  // \w do Python também é Unicode.
  const ROTULO_RE = re(ROTULO.replace('danfe\\w*', `danfe${W}*`), 'i');
  const EMPRESA_RE = re(EMPRESA, 'i');

  function limparPrefixoEmissor(valor) {
    const texto = strip(String(valor || '').replace(re(String.raw`^.*?\braz[aã]o\s+social\s*[:\-]\s*`, 'i'), ''));
    return strip(texto.replace(re(String.raw`^(?:(?:provedor|prestador(?:\s+de\s+servi[cç]os)?|emitente|benefici[aá]rio|cedente|fornecedor)\s*[/|]?\s*)+[:\-]\s*`, 'i'), ''));
  }

  function pareceRotulo(valor) {
    const texto = strip(String(valor || ''));
    if (!texto) return false;
    if (ROTULO_RE.test(texto) && !EMPRESA_RE.test(texto)) return true;
    return /^[\d\s/.,:R$-]+$/u.test(texto); // só números/datas/valores
  }

  // Nome da empresa emissora numa linha solta (DANFECom, NFS-e nacional, boleto com rótulos empilhados).
  function empresaEmissoraPorLinha(texto) {
    const linhas = splitlines(texto).map((ln) => strip(ln));
    const separador = re(String.raw`\s{2,}|\s\|\s|\s/\s(?=CNPJ|CPF|RUA|AV)`);
    const candidato = (linha) => {
      const m = linha.match(separador);
      let primeiro = strip(m ? linha.slice(0, m.index) : linha, ' -:|');
      primeiro = limparPrefixoEmissor(primeiro).replace(/\s+-\s+.*$/u, ''); // "X LTDA - NOME FANTASIA"
      if (!EMPRESA_RE.test(primeiro) || primeiro.length > 120 || pareceRotulo(primeiro)) return '';
      if (EMPRESAS_DO_GRUPO.some((empresa) => semAcentoMaiusculo(primeiro).includes(empresa))) return '';
      return primeiro;
    };
    const pagador = re('tomador|destinat[aá]rio|pagador|sacado|cliente|contratante', 'i');
    const emissor = re('emitente|benefici[aá]rio|cedente|prestador|nome\\s*/\\s*nome empresarial', 'i');
    for (let i = 0; i < linhas.length; i += 1) {
      if (emissor.test(linhas[i]) && !pagador.test(linhas[i])) {
        for (const proxima of linhas.slice(i, i + 5)) {
          if (pagador.test(proxima)) break;
          const nome = candidato(proxima);
          if (nome) return nome;
        }
      }
    }
    let bloqueio = 0;
    for (const linha of linhas) {
      if (pagador.test(linha)) { bloqueio = 3; continue; } // a linha do pagador e as seguintes são do cliente
      if (bloqueio) { bloqueio -= 1; continue; }
      const nome = candidato(linha);
      if (nome) return nome;
    }
    return '';
  }

  // ---------- descrição do serviço ----------
  const ROTULO_ENCARGO_RE = re(String.raw`^(?:mora|multa|juros|outros\s+acr[eé]scimos|outras\s+dedu|desconto|abatimento|valor\s+(?:cobrado|documento))`, 'i');
  // Descrição precisa ter uma palavra (4+ letras) e não ser um campo de data ("Ref. 10/10 até 09/11").
  const descricaoValida = (v) => /[\p{L}\p{Mn}]{4,}/u.test(v) && !/:\s*\d{2}[/.]\d{2}[/.]\d{4}\s*$/u.test(v) && !ROTULO_ENCARGO_RE.test(v);
  const CABECALHO_TABELA = String.raw`descri[cç][aã]o|valor|qtde|quant|contrato|unit[aá]rio|\bitem\b`;

  // "Discriminação do serviço:" sozinho na linha: a descrição é a 1ª célula da linha de baixo (pula o cabeçalho).
  function descricaoAbaixoDoRotulo(texto) {
    const linhas = splitlines(texto).map((ln) => strip(ln));
    const rotulo = re(String.raw`^(?:discrimina[cç][aã]o|descri[cç][aã]o)\s+(?:do|dos|de)\s+servi[cç]os?\s*:?$`, 'i');
    for (let i = 0; i < linhas.length; i += 1) {
      if (!rotulo.test(linhas[i])) continue;
      let seguintes = linhas.slice(i + 1, i + 6).filter(Boolean);
      if (seguintes.length && (seguintes[0].match(re(CABECALHO_TABELA, 'gi')) || []).length >= 2) seguintes = seguintes.slice(1);
      if (!seguintes.length) return '';
      const celula = strip(seguintes[0].split(/\s{2,}/u)[0]);
      return descricaoValida(celula) ? celula.slice(0, 1000) : '';
    }
    return '';
  }

  // Boleto: "(+) Prestação de serviço..." (ignora encargos: mora, multa, juros...) ou "Referente ao ...".
  function descricaoPorMarcador(texto) {
    const linhas = splitlines(texto);
    for (const linha of linhas) {
      for (const m of linha.matchAll(/\(\+\)\s*(.+?)(?=\s{3,}|\s*\([+=-]\)|$)/gu)) {
        const trecho = strip(strip(m[1].replace(/\s*R\$.*$/u, '')), ' -:');
        if (trecho.length >= 3 && descricaoValida(trecho)) return trecho.slice(0, 1000);
      }
    }
    const referente = re(String.raw`^\s*(?:referente\b(?:\s+(?:ao|aos|à|às|a))?|ref\.)\s*(.+?)(?=\s{3,}|$)`, 'i');
    for (const linha of linhas) {
      const m = linha.match(referente);
      if (m && strip(m[1]).length >= 5 && descricaoValida(strip(strip(m[1]), ' -:.'))) return strip(strip(m[1]), ' -:.').slice(0, 1000);
    }
    return '';
  }

  // Dígito verificador da chave de 44 dígitos (NF-e, NFCom): módulo 11, pesos 2 a 9 da direita.
  function dvChaveOk(digitos) {
    if (!/^\d{44}$/.test(digitos)) return false;
    let soma = 0;
    [...digitos.slice(0, 43)].reverse().forEach((d, i) => { soma += Number(d) * (2 + (i % 8)); });
    const dv = 11 - (soma % 11);
    return (dv >= 10 ? 0 : dv) === Number(digitos[43]);
  }

  // ---------- extração principal (= _extract_invoice_fields) ----------
  const ROTULOS_VALOR = [
    'valor total da nota', 'valor l[ií]quido da nota',
    'valor\\s+total\\s+(?:da\\s+)?(?:fatura|conta)', 'total\\s+(?:da\\s+)?(?:fatura|conta)',
    'total a pagar',
    'valor\\s+a\\s+pagar', 'valor total', 'valor do documento', 'valor cobrado',
    '\\(=\\)\\s*valor\\s+cobrado',
  ];

  const ROTULOS_VALOR_COLUNA = [
    String.raw`valor\s+total\s+da\s+nfs-?e`, String.raw`valor\s+l[ií]quido\s+da\s+nfs-?e`, String.raw`valor\s+total\s+da\s+nota`,
    String.raw`total\s+a\s+pagar`, String.raw`valor\s+a\s+pagar`,
  ];

  function extrairCamposFatura(textoBruto) {
    const text = String(textoBruto ?? '');
    const lines = splitlines(text).filter((ln) => strip(ln)).map((ln) => strip(ln.replace(/\s+/g, ' ')));
    const joined = lines.join('\n');
    const rotulado = (padrao) => {
      const m = joined.match(re(padrao, 'im'));
      return m ? strip(m[1], ' \t:;.-') : '';
    };

    // Emissor
    let issuer = rotulado(String.raw`^(?:prestador(?:\s+de\s+servi[cç]os)?|fornecedor|raz[aã]o social(?: do prestador)?|nome do prestador|benefici[aá]rio|cedente|emitente)\s*[:\-]\s*(.+)$`);
    if (!issuer) issuer = colunaDe(text, 'benefici[aá]rio|cedente|emitente');
    issuer = limparPrefixoEmissor(issuer);
    if (pareceRotulo(issuer)) issuer = '';
    if (!issuer) issuer = empresaEmissoraPorLinha(text);

    // Número do documento
    let number = rotulado(String.raw`^(?:n[uú]mero\s+(?:da\s+)?(?:nota(?:\s+fiscal)?|nfs[\s-]?e)|nota(?:\s+fiscal)?(?:\s+de\s+servi[cç]o)?|nfs[\s-]?e|n[º°o]\.?\s*(?:do\s+)?documento|n[uú]mero\s+(?:da\s+)?(?:fatura|conta))\s*(?:n[º°o.]*)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./-]{0,79})$`);
    if (!number) {
      const curto = text.match(re(String.raw`\bn[º°o][.:]+\s*(\d{3,20})\b`, 'i')); // "Nº.: 16713" (DANFECom)
      if (curto) number = curto[1];
    }
    // Também quando a leitura inline pegou o rótulo da coluna vizinha ("Nº documento    Vencimento").
    if (!number || motivoNumeroInvalido(number)) {
      const candidato = colunaDe(text, String.raw`n[º°o]\.?\s*documento`);
      if (candidato && !/^\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}$/.test(candidato)
        && (!number || !motivoNumeroInvalido(candidato))) number = candidato;
    }
    // "Nº Documento: 77001    Vencimento: ..." no meio da linha (exige ":", "#" ou "-").
    if (!number || motivoNumeroInvalido(number)) {
      const meio = text.match(re(String.raw`(?:n[º°o]\.?\s*(?:do\s+)?documento|n[uú]mero\s+(?:da\s+)?(?:nota(?:\s+fiscal)?|nfs-?e))\s*[:#\-]\s*([A-Z0-9][A-Z0-9./-]{2,40})`, 'i'));
      if (meio && !motivoNumeroInvalido(meio[1])) number = meio[1];
    }
    // "NOTA FISCAL Nº 16210 - SÉRIE: 1" no meio da linha (DANFE-COM).
    if (!number || motivoNumeroInvalido(number)) {
      const nf = text.match(re(String.raw`nota\s+fiscal\s+n[º°o]\.?\s*[:#\-]?\s*(\d{1,20})(?!\d)`, 'i'));
      if (nf && !motivoNumeroInvalido(nf[1])) number = nf[1];
    }
    if (!number || motivoNumeroInvalido(number)) {
      const qualquer = text.match(re(String.raw`(?:n[uú]mero|n[uú]m\.?|n[º°o]\.?)\s*(?:da\s+)?(?:fatura|conta)\s*[:#º°\-]?\s*([A-Z0-9][A-Z0-9./-]{0,29})|(?:fatura|conta)\s*(?:n[uú]mero|n[uú]m\.?|n[º°o]\.?)\s*[:#º°\-]?\s*([A-Z0-9][A-Z0-9./-]{0,29})`, 'i'));
      const achado = qualquer ? (qualquer[1] || qualquer[2]) : '';
      if (achado && !motivoNumeroInvalido(achado)) number = achado;
    }

    // Chave de acesso e série
    let accessKey = rotulado(String.raw`^(?:chave\s+de\s+acesso|chave\s+da\s+nota)\s*[:#\-]\s*([A-Z0-9 .-]{20,160})$`).replace(/\s+/g, '');
    // Chave na linha de baixo ("CHAVE DE ACESSO DA NFS-e" + 50 dígitos). Só aceita 44 ou 50 dígitos exatos.
    if (motivoChaveInvalida(accessKey)) {
      const m = text.match(re(String.raw`chave\s+de\s+acesso(?:\s+d[ao]\s+(?:nfs-?e|nf-?e|nfcom|nota(?:\s+fiscal)?))?[^\d\n]{0,40}\n?[ \t]*(\d[\d .]{42,68}\d)`, 'i'));
      const digitos = m ? soDigitos(m[1]) : '';
      if (TAMANHOS_CHAVE.includes(digitos.length)) accessKey = digitos;
    }
    // Chave de 44 dígitos em grupos de 4, em qualquer coluna, se o texto fala em chave de acesso e o DV confere.
    if (motivoChaveInvalida(accessKey) && re(String.raw`chave\s+de\s+acesso`, 'i').test(text)) {
      for (const m of text.matchAll(/(?<!\d)\d{4}(?: \d{4}){10}(?!\d)/gu)) {
        const digitos = m[0].replace(/ /g, '');
        if (dvChaveOk(digitos)) { accessKey = digitos; break; }
      }
    }
    const series = rotulado(String.raw`^(?:s[eé]rie)\s*[:#\-]\s*([A-Z0-9./-]{1,80})$`);

    // Descrição do serviço
    // Só a mesma linha do rótulo ([ \t], não \s): antes o \s atravessava a quebra e pegava a linha seguinte.
    let description = rotulado(String.raw`^(?:discrimina[cç][aã]o|descri[cç][aã]o)[ \t]+(?:do|dos)?[ \t]*servi[cç]os?[ \t]*[:\-][ \t]*(.+)$`).slice(0, 1000);
    if (!description) description = descricaoAbaixoDoRotulo(text);
    if (!description) description = descricaoPorMarcador(text);

    // Data de emissão: emissão, emitido em, data da fatura/nota/conta/documento, data de processamento.
    let issueRaw = rotulado(String.raw`^(?:data\s+de\s+emiss[aã]o(?:\s+d[aeo]\s+(?:fatura|nota|conta|documento))?|emiss[aã]o|emitid[ao]\s+em|data\s+d[aeo]\s+(?:fatura|nota(?:\s+fiscal)?|conta|documento)|data\s+d[eo]\s+processamento)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/.]\d{2}[/.]\d{4})(?:\s.*)?$`);
    if (!issueRaw) {
      issueRaw = colunaData(text, String.raw`data\s+d[aeo]\s+(?:documento|fatura|nota|conta)|data\s+d[eo]\s+processamento|(?:data\s+de\s+)?emiss[aã]o`);
    }
    if (!parseDataOcr(issueRaw)) {
      const m = text.match(re(String.raw`(?:data\s+(?:e\s+hora\s+)?d[ae]\s+)?emiss[aã]o\s*(?::|[ \t]{2,})[ \t]*(\d{2}[/.]\d{2}[/.]\d{4})`, 'i'));
      if (m) issueRaw = m[1];
    }

    // Data de vencimento
    let dueRaw = rotulado(String.raw`^(?:data\s+de\s+)?(?:vencimento|pagar\s+at[eé])\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/.]\d{2}[/.]\d{4})$`);
    if (!dueRaw) dueRaw = colunaDe(text, String.raw`\bvencimento\b`);
    if (!parseDataOcr(dueRaw)) {
      const m = text.match(re(String.raw`vencimento\s*:[ \t]*(\d{2}[/.]\d{2}[/.]\d{4})`, 'i'));
      if (m) dueRaw = m[1];
    }

    // Valor: a linha digitável prevalece; depois os rótulos, na ordem de prioridade.
    const boleto = lerLinhaDigitavel(text);
    let amount = null;
    for (const rotulo of ROTULOS_VALOR) {
      const bruto = rotulado(`^(?:${rotulo})\\s*[:\\-]?\\s*(?:R\\$\\s*)?([\\d.]+,\\d{2}|\\d+\\.\\d{2})$`);
      if (bruto) {
        amount = pyFloat(bruto.includes(',') ? bruto.replace(/\./g, '').replace(',', '.') : bruto);
        break;
      }
    }
    // Rótulo e valor em colunas, em linhas diferentes (NFS-e Nacional: "VALOR TOTAL DA NFS-E" e, na linha de baixo,
    // "R$ 15,00"). Só rótulos específicos: "Valor Total Apurado - IBS" (imposto) não pode virar o valor da conta.
    if (amount === null) {
      for (const rotulo of ROTULOS_VALOR_COLUNA) {
        const m = colunaDe(text, rotulo).match(/^(?:R\$\s*)?([\d.]+,\d{2})$/);
        if (m) { amount = pyFloat(m[1].replace(/\./g, '').replace(',', '.')); break; }
      }
    }
    const finalAmount = boleto.valor !== null ? boleto.valor : amount;

    // CNPJs
    const cnpjNaLinha = (linha) => {
      const m = linha.match(/(?<!\d)(?:\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2})(?!\d)/u);
      return m ? soDigitos(m[0]) : '';
    };
    const linhaDestinatario = lines.find((ln) => re('(?:tomador|destinat[aá]rio|cliente|contratante|pagador)', 'i').test(ln)
      && re(String.raw`\b(?:cnpj|cpf)\b`, 'i').test(ln)) || '';
    const linhaEmissor = lines.find((ln) => re('(?:prestador|fornecedor|emitente|benefici[aá]rio|cedente)', 'i').test(ln)
      && re(String.raw`\bcnpj\b`, 'i').test(ln)) || '';
    const todos = unicos((text.match(/\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}/gu) || []).map(soDigitos));
    const cnpjDest = cnpjNaLinha(linhaDestinatario);
    let cnpjEmis = cnpjNaLinha(linhaEmissor);
    if (!cnpjEmis) {
      const outros = todos.filter((c) => c !== cnpjDest);
      if (outros.length === 1) [cnpjEmis] = outros;
    }
    if (!cnpjEmis && issuer) {
      // CNPJ na linha do nome do emissor ou nas 3 seguintes.
      const nome = normalizarNomeEmpresa(issuer);
      for (let i = 0; i < lines.length && !cnpjEmis; i += 1) {
        if (nome && normalizarNomeEmpresa(lines[i]).includes(nome)) {
          for (const vizinha of lines.slice(i, i + 4)) {
            const achado = cnpjNaLinha(vizinha);
            if (achado && achado !== cnpjDest) { cnpjEmis = achado; break; }
          }
        }
      }
    }

    const fields = {
      emissorNome: issuer.slice(0, 300),
      numero: number.slice(0, 80),
      chave: accessKey.slice(0, 160),
      serie: series.slice(0, 80),
      valorTotal: finalAmount,
      dataEmissao: parseDataOcr(issueRaw),
      dataVencimento: boleto.vencimento || parseDataOcr(dueRaw),
      descricaoServico: description,
      cnpjDestinatario: cnpjDest,
      cnpjEmissor: cnpjEmis,
      versaoRegras: VERSAO_REGRAS,
      // Só no JS (fora da resposta da API): valor e vencimento lidos do texto, sem a linha digitável.
      // O WF-08 usa para apontar divergência "boleto x texto".
      valorTexto: amount,
      vencimentoTexto: parseDataOcr(dueRaw),
    };
    // Obrigatórios: nome, valor e vencimento (a emissão cai para a data de recebimento no SIGp).
    fields.camposParaRevisar = ['emissorNome', 'valorTotal', 'dataVencimento'].filter((k) => !fields[k]);
    return aplicarPadraoIdentificacao(fields);
  }

  // ---------- resposta completa (= POST /api/extracao/texto) ----------
  function extrairDoTexto({ texto = '', ocrUsado = false, provedorEsperado = '', valorEsperado = 0, vencimentoEsperado = '' } = {}) {
    const text = String(texto ?? '');
    const temTexto = Boolean(strip(text));
    const esperado = strip(String(provedorEsperado || ''));
    const fields = temTexto ? extrairCamposFatura(text) : aplicarPadraoIdentificacao({
      emissorNome: '', numero: '', chave: '', valorTotal: null, dataEmissao: '', dataVencimento: '',
      descricaoServico: '', cnpjEmissor: '', cnpjDestinatario: '',
      camposParaRevisar: ['emissorNome', 'valorTotal', 'dataVencimento'],
    });
    const encontrado = Boolean(esperado && normalizarNomeEmpresa(text).includes(normalizarNomeEmpresa(esperado)));
    if (!fields.emissorNome) {
      // Último recurso: o provedor esperado aparece no texto, ou uma linha com "telecom/internet".
      if (encontrado) {
        fields.emissorNome = esperado;
      } else {
        const linha = splitlines(text).map((ln) => strip(ln))
          .find((ln) => re('telecom|telecomunic|provedor|internet|comunica[cç][oõ]es', 'i').test(ln) && ln.length <= 120) || '';
        fields.emissorNome = linha.replace(/\s{2,}.*$/u, '').slice(0, 300);
      }
    }
    const cnpjs = unicos((text.match(/\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}/gu) || []).map(soDigitos));
    const valorEsp = pyFloat(valorEsperado || 0) ?? 0;
    const vencEsp = strip(String(vencimentoEsperado || ''));
    const amount = fields.valorTotal ?? null;
    const revisar = [...(fields.camposParaRevisar || [])];
    if (fields.emissorNome && revisar.includes('emissorNome')) revisar.splice(revisar.indexOf('emissorNome'), 1);
    return {
      ok: true,
      extrator: VERSAO,
      textEncontrado: temTexto,
      ocrUsado: Boolean(ocrUsado),
      emissorNome: fields.emissorNome || '',
      emissorEsperadoEncontrado: encontrado,
      cnpjEmissor: fields.cnpjEmissor || (cnpjs.length === 1 ? cnpjs[0] : ''),
      cnpjCandidatos: cnpjs,
      numeroFatura: fields.numero || '',
      numero: fields.numero || '',
      numeroPadrao: Boolean(fields.numeroPadrao),
      numeroOriginal: fields.numeroOriginal || '',
      chave: fields.chave || '',
      dataEmissao: fields.dataEmissao || '',
      dataVencimento: fields.dataVencimento || '',
      valorTotal: amount,
      descricaoServico: fields.descricaoServico || '',
      linhaDigitavelUsada: Boolean(lerLinhaDigitavel(text).linhaDigitavel),
      versaoRegras: VERSAO_REGRAS,
      comparacao: {
        emissorConfere: encontrado,
        valorConfere: valorEsp > 0 && amount !== null && Math.abs(valorEsp - Number(amount)) < 0.01,
        vencimentoConfere: !vencEsp || vencEsp === fields.dataVencimento,
      },
      camposParaRevisar: revisar,
      aviso: temTexto ? '' : 'Nenhum texto foi reconhecido no PDF, mesmo após o OCR local; confira os campos manualmente.',
    };
  }

  return {
    VERSAO, VERSAO_REGRAS, VALOR_PADRAO, EMPRESAS_DO_GRUPO,
    extrairDoTexto, extrairCamposFatura, lerLinhaDigitavel,
    aplicarPadraoIdentificacao, motivoNumeroInvalido, motivoChaveInvalida, ehPadrao,
    parseDataOcr, normalizarNomeEmpresa, colunaDe, empresaEmissoraPorLinha,
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ExtratorSIGp;
