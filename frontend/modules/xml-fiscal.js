// Leitura do XML da nota fiscal que chega junto da fatura PDF (NFS-e ABRASF, NFS-e nacional, NF-e, NFCom).
//
// O XML é o documento fiscal oficial: número, série, chave, emitente, valor e datas lidos aqui têm prioridade
// sobre a leitura do PDF (decisão do usuário, 13/11/2026). O PDF continua obrigatório e é guardado junto.
// Leitor por expressões regulares, sem DOM e sem resolver entidades (o nó Code do n8n não tem DOMParser,
// e assim não há risco de XXE). Ignora prefixos de namespace. Ignora o bloco <CamposTreinamento> dos
// arquivos de teste: ele é o gabarito dos testes, não existe em XML real.
//
// Uso: Node (testes) const XF = require('./xml_fiscal.js'); XF.lerXmlFiscal(texto)
//      n8n: os builds colam este arquivo no nó; use XmlFiscalSIGp.lerXmlFiscal(texto)

const XmlFiscalSIGp = (() => {
  const VERSAO = 'n8n_lib_xml_fiscal_v1';
  const LIMITE = 2 * 1024 * 1024;

  const ENTIDADES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };
  const decodificar = (v) => String(v ?? '')
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (m, e) => {
      if (e[0] === '#') {
        const n = e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        return Number.isFinite(n) && n > 0 && n < 0x110000 ? String.fromCodePoint(n) : '';
      }
      return ENTIDADES[e.toLowerCase()];
    })
    .replace(/\s+/g, ' ').trim();

  // Primeiro bloco <nome ...>...</nome> (qualquer prefixo). Devolve { inner, attrs } ou null.
  function bloco(xml, nome) {
    if (!xml) return null;
    const m = xml.match(new RegExp(`<(?:[\\w.-]+:)?${nome}(\\s[^>]*)?>([\\s\\S]*?)</(?:[\\w.-]+:)?${nome}\\s*>`));
    return m ? { attrs: m[1] || '', inner: m[2] } : null;
  }
  function blocos(xml, nome) {
    if (!xml) return [];
    const re = new RegExp(`<(?:[\\w.-]+:)?${nome}(\\s[^>]*)?>([\\s\\S]*?)</(?:[\\w.-]+:)?${nome}\\s*>`, 'g');
    return [...xml.matchAll(re)].map((m) => ({ attrs: m[1] || '', inner: m[2] }));
  }
  // Texto do primeiro elemento folha com um dos nomes, dentro de xml.
  function valor(xml, ...nomes) {
    for (const nome of nomes) {
      const b = bloco(xml, nome);
      if (b && !/<[A-Za-z]/.test(b.inner)) {
        const v = decodificar(b.inner);
        if (v) return v;
      }
    }
    return '';
  }
  const atributo = (attrs, nome) => decodificar((String(attrs || '').match(new RegExp(`\\b${nome}\\s*=\\s*"([^"]*)"`, 'i')) || [])[1] || '');
  const dentro = (xml, ...caminho) => caminho.reduce((acc, nome) => (acc ? (bloco(acc, nome)?.inner ?? '') : ''), xml);
  const soDigitos = (v) => String(v ?? '').replace(/\D/g, '');

  function numero(v) {
    const s = String(v ?? '').trim();
    if (!s) return null;
    const n = Number(s.includes(',') && !s.includes('.') ? s.replace(',', '.') : s.replace(/,(?=\d{3})/g, ''));
    return Number.isFinite(n) ? Math.round(n * 100) / 100 : null;
  }
  // AAAA-MM-DD a partir de "2026-11-10T09:30:00-03:00", "2026-11-10" ou "10/11/2026".
  function data(v) {
    const s = String(v ?? '').trim();
    let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) { const br = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/); if (br) m = [br[0], br[3], br[2], br[1]]; }
    if (!m) return '';
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3] ? `${m[1]}-${m[2]}-${m[3]}` : '';
  }
  // "Venc 20/11/2026", "Vencimento: 20/11/2026" em campos de texto livre.
  function vencimentoNoTexto(...textos) {
    for (const t of textos) {
      const m = String(t || '').match(/venc(?:imento|to\.?|\.)?\s*(?:em|:)?\s*(\d{2}\/\d{2}\/\d{4})/i);
      if (m && data(m[1])) return data(m[1]);
    }
    return '';
  }
  const cnpjDe = (xml) => soDigitos(valor(xml, 'Cnpj', 'CNPJ', 'Cpf', 'CPF'));
  const itens = (lista) => lista.filter((i) => i.descricao).map((i) => ({
    descricao: i.descricao.slice(0, 500), quantidade: numero(i.quantidade), valorUnitario: numero(i.valorUnitario), valorTotal: numero(i.valorTotal),
  }));

  function abrasf(xml) {
    const inf = bloco(xml, 'InfNfse');
    const s = inf.inner;
    const prestador = dentro(s, 'PrestadorServico') || dentro(s, 'Prestador');
    const tomador = dentro(s, 'TomadorServico') || dentro(s, 'Tomador');
    const declaracao = dentro(s, 'InfDeclaracaoPrestacaoServico') || s;
    const servico = dentro(declaracao, 'Servico');
    const lista = itens(blocos(servico, 'ItensServico').map((b) => ({
      descricao: valor(b.inner, 'Descricao', 'Discriminacao'), quantidade: valor(b.inner, 'Quantidade'),
      valorUnitario: valor(b.inner, 'ValorUnitario'), valorTotal: valor(b.inner, 'ValorTotal'),
    })));
    const outras = valor(s, 'OutrasInformacoes');
    return {
      tipoXml: 'nfse_abrasf',
      numero: valor(s, 'Numero'),
      serie: valor(dentro(declaracao, 'IdentificacaoRps'), 'Serie') || valor(declaracao, 'Serie'),
      chave: soDigitos(atributo(inf.attrs, 'Id')),
      codigoVerificacao: valor(s, 'CodigoVerificacao'),
      emissorNome: valor(prestador, 'RazaoSocial'),
      emissorFantasia: valor(prestador, 'NomeFantasia'),
      cnpjEmissor: cnpjDe(dentro(prestador, 'IdentificacaoPrestador') || prestador),
      destinatarioNome: valor(tomador, 'RazaoSocial'),
      cnpjDestinatario: cnpjDe(tomador),
      // <Endereco> aninhado em <Endereco>: busca direto no bloco (o leitor não conta aninhamento).
      municipioCodigo: valor(prestador, 'CodigoMunicipio') || valor(servico, 'CodigoMunicipio'),
      cidade: valor(tomador, 'Cidade', 'xMun'),
      valorTotal: numero(valor(dentro(s, 'ValoresNfse'), 'ValorLiquidoNfse') || valor(servico, 'ValorServicos')),
      dataEmissao: data(valor(s, 'DataEmissao')),
      dataVencimento: data(valor(s, 'DataVencimento')) || vencimentoNoTexto(outras, valor(servico, 'Discriminacao')),
      competencia: data(valor(declaracao, 'Competencia')).slice(0, 7),
      descricaoServico: (lista.map((i) => i.descricao).join('; ') || valor(servico, 'Discriminacao') || outras).slice(0, 1000),
      servicos: lista,
    };
  }

  function nacional(xml) {
    const inf = bloco(xml, 'infNFSe');
    const s = inf.inner;
    const emit = dentro(s, 'emit');
    const dps = dentro(s, 'infDPS');
    const toma = dentro(dps, 'toma') || dentro(s, 'toma');
    const serv = dentro(dps, 'serv');
    const descricao = valor(dentro(serv, 'cServ'), 'xDescServ') || valor(s, 'xTribNac', 'xTribMun');
    return {
      tipoXml: 'nfse_nacional',
      numero: valor(s, 'nNFSe'),
      serie: valor(dps, 'serie') || valor(s, 'serie'),
      chave: soDigitos(valor(s, 'chNFSe')) || soDigitos(atributo(inf.attrs, 'Id')),
      codigoVerificacao: '',
      emissorNome: valor(emit, 'xNome'),
      emissorFantasia: valor(emit, 'xFant'),
      cnpjEmissor: cnpjDe(emit),
      destinatarioNome: valor(toma, 'xNome'),
      cnpjDestinatario: cnpjDe(toma),
      municipioCodigo: valor(s, 'cLocIncid', 'cLocPrestacao'),
      cidade: valor(s, 'xLocPrestacao', 'xLocIncid'),
      valorTotal: numero(valor(dentro(s, 'valores'), 'vLiq') || valor(dentro(dps, 'vServPrest'), 'vServ')),
      dataEmissao: data(valor(s, 'dhEmi') || valor(dps, 'dhEmi')),
      dataVencimento: data(valor(s, 'dtVenc', 'dVenc')) || vencimentoNoTexto(valor(s, 'xInfComp'), valor(dps, 'xInfComp')),
      competencia: data(valor(s, 'competencia') || valor(dps, 'dCompet')).slice(0, 7),
      descricaoServico: descricao.slice(0, 1000),
      servicos: descricao ? [{ descricao: descricao.slice(0, 500), quantidade: 1, valorUnitario: null, valorTotal: null }] : [],
    };
  }

  // NF-e (modelo 55) e NFCom (modelo 62) têm estrutura parecida: ide, emit, dest, det/prod, total.
  function nfeOuNfcom(xml, tipo) {
    const inf = bloco(xml, tipo === 'nfcom' ? 'infNFCom' : 'infNFe');
    const s = inf.inner;
    const ide = dentro(s, 'ide');
    const emit = dentro(s, 'emit');
    const dest = dentro(s, 'dest');
    const lista = itens(blocos(s, 'det').map((b) => {
      const prod = dentro(b.inner, 'prod');
      return { descricao: valor(prod, 'xProd', 'xItem'), quantidade: valor(prod, 'qCom', 'qFaturada'), valorUnitario: valor(prod, 'vUnCom', 'vItem'), valorTotal: valor(prod, 'vProd') };
    }));
    const vencimentos = blocos(s, 'dup').map((b) => data(valor(b.inner, 'dVenc'))).filter(Boolean).sort();
    return {
      tipoXml: tipo,
      numero: valor(ide, 'nNF'),
      serie: valor(ide, 'serie'),
      chave: soDigitos(atributo(inf.attrs, 'Id')) || soDigitos(valor(xml, 'chNFe', 'chNFCom')),
      codigoVerificacao: '',
      emissorNome: valor(emit, 'xNome'),
      emissorFantasia: valor(emit, 'xFant'),
      cnpjEmissor: cnpjDe(emit),
      destinatarioNome: valor(dest, 'xNome'),
      cnpjDestinatario: cnpjDe(dest),
      municipioCodigo: valor(dentro(dest, 'enderDest'), 'cMun') || valor(ide, 'cMunFG'),
      cidade: valor(dentro(dest, 'enderDest'), 'xMun'),
      valorTotal: numero(valor(dentro(s, 'total'), 'vNF')),
      dataEmissao: data(valor(ide, 'dhEmi', 'dEmi')),
      dataVencimento: vencimentos[0] || data(valor(dentro(s, 'gFat'), 'dVencFat')) || vencimentoNoTexto(valor(s, 'infCpl')),
      competencia: (valor(dentro(s, 'gFat'), 'CompetFat') || '').replace(/^(\d{4})(\d{2})$/, '$1-$2'),
      descricaoServico: lista.map((i) => i.descricao).join('; ').slice(0, 1000),
      servicos: lista,
    };
  }

  function lerXmlFiscal(texto) {
    const bruto = String(texto ?? '');
    if (!bruto.trim()) return { ok: false, extrator: VERSAO, erro: 'XML vazio.' };
    if (bruto.length > LIMITE) return { ok: false, extrator: VERSAO, erro: 'XML maior que 2 MiB.' };
    if (/<!DOCTYPE|<!ENTITY/i.test(bruto)) return { ok: false, extrator: VERSAO, erro: 'XML com DOCTYPE/ENTITY não é aceito.' };
    const xml = bruto.replace(/^\uFEFF/, '').replace(/<!--[\s\S]*?-->/g, '')
      .replace(/<(?:[\w.-]+:)?CamposTreinamento[\s\S]*?<\/(?:[\w.-]+:)?CamposTreinamento\s*>/gi, '');
    if (!/^\s*(<\?xml[^>]*\?>\s*)?</.test(xml)) return { ok: false, extrator: VERSAO, erro: 'O arquivo não é XML.' };
    let r = null;
    if (bloco(xml, 'InfNfse')) r = abrasf(xml);
    else if (bloco(xml, 'infNFSe')) r = nacional(xml);
    else if (bloco(xml, 'infNFCom')) r = nfeOuNfcom(xml, 'nfcom');
    else if (bloco(xml, 'infNFe')) r = nfeOuNfcom(xml, 'nfe');
    if (!r) return { ok: false, extrator: VERSAO, erro: 'Tipo de XML não reconhecido (esperado NFS-e, NF-e ou NFCom).' };
    // Serviço único sem valor no XML (comum na NFS-e nacional): o valor do item é o total da nota.
    if (r.servicos.length === 1 && r.servicos[0].valorTotal === null && r.valorTotal !== null) {
      r.servicos[0] = { ...r.servicos[0], valorTotal: r.valorTotal, valorUnitario: r.servicos[0].valorUnitario ?? r.valorTotal };
    }
    const faltando = ['numero', 'emissorNome', 'valorTotal', 'dataEmissao'].filter((k) => r[k] === '' || r[k] === null);
    return { ok: true, extrator: VERSAO, ...r, camposAusentes: faltando };
  }

  // Campos fiscais que o XML define (prioridade sobre a leitura do PDF). Vencimento só se o XML trouxer.
  const CAMPOS_PRIORIDADE = [
    ['numero', 'numero'], ['serie', 'serie'], ['chave', 'chave'], ['emissorNome', 'emissorNome'],
    ['cnpjEmissor', 'cnpjEmissor'], ['cnpjDestinatario', 'cnpjDestinatario'], ['valorTotal', 'valorTotal'],
    ['dataEmissao', 'dataEmissao'], ['dataVencimento', 'dataVencimento'], ['descricaoServico', 'descricaoServico'],
  ];
  const VAZIO_PDF = (v) => v === null || v === undefined || v === '' || String(v).trim() === '999999999';

  // Mesmo número com outra formatação não é divergência: "000004572" (PDF) = "4572" (XML); CNPJ com ou sem pontuação.
  function mesmoIdentificador(campo, a, b) {
    const limpo = (v) => String(v ?? '').trim().toUpperCase();
    if (campo === 'cnpjEmissor') return limpo(a).replace(/\D/g, '') === limpo(b).replace(/\D/g, '');
    if (campo === 'numero') {
      const n = (v) => limpo(v).replace(/[^0-9A-Z]/g, '').replace(/^0+(?=.)/, '');
      return n(a) === n(b);
    }
    return limpo(a) === limpo(b);
  }

  // Junta a leitura do PDF (campos) com o XML: o XML vence; as diferenças relevantes ficam registradas.
  function aplicarPrioridadeXml(campos, xmlLido) {
    const saida = { ...campos };
    if (!xmlLido || !xmlLido.ok) return saida;
    const divergencias = [];
    for (const [destino, origem] of CAMPOS_PRIORIDADE) {
      const doXml = xmlLido[origem];
      if (doXml === '' || doXml === null || doXml === undefined) continue;
      const doPdf = saida[destino];
      if (!VAZIO_PDF(doPdf) && ['numero', 'valorTotal', 'dataVencimento', 'cnpjEmissor'].includes(destino)) {
        const iguais = destino === 'valorTotal' ? Math.abs(Number(doPdf) - Number(doXml)) < 0.01 : mesmoIdentificador(destino, doPdf, doXml);
        if (!iguais) divergencias.push({ campo: destino, pdf: doPdf, xml: doXml });
      }
      saida[destino] = doXml;
    }
    if (xmlLido.destinatarioNome && !saida.destinatarioNome) saida.destinatarioNome = xmlLido.destinatarioNome;
    if (xmlLido.servicos?.length) saida.servicos = xmlLido.servicos;
    saida.origemCampos = 'xml';
    saida.divergenciasXml = divergencias;
    // Campos que o XML preencheu saem da revisão.
    const preenchidos = new Set(CAMPOS_PRIORIDADE.map(([d]) => d).filter((d) => !VAZIO_PDF(saida[d])));
    saida.camposParaRevisar = (saida.camposParaRevisar || []).filter((c) => !preenchidos.has(c));
    if (divergencias.length && !saida.camposParaRevisar.includes('divergenciasXml')) saida.camposParaRevisar.push('divergenciasXml');
    return saida;
  }

  return { VERSAO, lerXmlFiscal, aplicarPrioridadeXml };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = XmlFiscalSIGp;
