// Testes da n8n/lib/xml_fiscal.js. Rodar:  node --test tests/n8n/xml_fiscal.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const XF = require('../../n8n/lib/xml_fiscal.js');

const PASTA = path.join(__dirname, '..', '..', 'docs', 'XML para testes');
const gabarito = (t, n) => ((t.match(new RegExp(`<CamposTreinamento>[\\s\\S]*?<${n}>([^<]*)</${n}>`)) || [])[1] || '').trim();

test('os 10 XML de teste (ABRASF e nacional) batem com o gabarito <CamposTreinamento>', { skip: !fs.existsSync(PASTA) }, () => {
  const arquivos = fs.readdirSync(PASTA).filter((f) => f.endsWith('.xml'));
  assert.ok(arquivos.length >= 10);
  for (const f of arquivos) {
    const t = fs.readFileSync(path.join(PASTA, f), 'utf8');
    const r = XF.lerXmlFiscal(t);
    assert.equal(r.ok, true, f);
    assert.equal(r.numero, gabarito(t, 'NumeroNota'), `${f} número`);
    assert.equal(r.chave, gabarito(t, 'ChaveNota'), `${f} chave`);
    assert.equal(r.emissorNome, gabarito(t, 'Provedor'), `${f} emissor`);
    assert.equal(r.valorTotal, Number(gabarito(t, 'ValorTotal')), `${f} valor`);
    assert.equal(r.dataEmissao, gabarito(t, 'Emissao').slice(0, 10), `${f} emissão`);
    assert.equal(r.dataVencimento, gabarito(t, 'Vencimento').slice(0, 10), `${f} vencimento`);
    // O leitor não usa o gabarito: sem o bloco, o resultado é o mesmo.
    const semGabarito = t.replace(/<CamposTreinamento>[\s\S]*?<\/CamposTreinamento>/, '');
    assert.deepEqual(XF.lerXmlFiscal(semGabarito), r, `${f} independe do gabarito`);
  }
});

test('NF-e (modelo 55) com prefixo de namespace e duplicata', () => {
  const xml = `<?xml version="1.0"?><nfe:nfeProc xmlns:nfe="http://www.portalfiscal.inf.br/nfe"><nfe:NFe><nfe:infNFe Id="NFe29261098765432000110550010000162101069255990">
    <nfe:ide><nfe:nNF>16210</nfe:nNF><nfe:serie>1</nfe:serie><nfe:dhEmi>2026-10-27T09:49:06-03:00</nfe:dhEmi></nfe:ide>
    <nfe:emit><nfe:CNPJ>98765432000110</nfe:CNPJ><nfe:xNome>WKVE TELECOM &amp; DADOS LTDA</nfe:xNome></nfe:emit>
    <nfe:dest><nfe:CNPJ>87654321000120</nfe:CNPJ><nfe:xNome>EXPRESSO BRASILEIRO TRANSPORTES LTDA</nfe:xNome><nfe:enderDest><nfe:cMun>2910800</nfe:cMun><nfe:xMun>Eunapolis</nfe:xMun></nfe:enderDest></nfe:dest>
    <nfe:det nItem="1"><nfe:prod><nfe:xProd>LINK INTERNET 400MB</nfe:xProd><nfe:qCom>1.0000</nfe:qCom><nfe:vUnCom>89.90</nfe:vUnCom><nfe:vProd>89.90</nfe:vProd></nfe:prod></nfe:det>
    <nfe:total><nfe:ICMSTot><nfe:vNF>89.90</nfe:vNF></nfe:ICMSTot></nfe:total>
    <nfe:cobr><nfe:dup><nfe:nDup>001</nfe:nDup><nfe:dVenc>2026-11-17</nfe:dVenc></nfe:dup></nfe:cobr>
  </nfe:infNFe></nfe:NFe></nfe:nfeProc>`;
  const r = XF.lerXmlFiscal(xml);
  assert.equal(r.tipoXml, 'nfe');
  assert.equal(r.chave, '29261098765432000110550010000162101069255990');
  assert.deepEqual([r.numero, r.serie, r.emissorNome, r.cnpjEmissor], ['16210', '1', 'WKVE TELECOM & DADOS LTDA', '98765432000110']);
  assert.deepEqual([r.cnpjDestinatario, r.cidade, r.valorTotal, r.dataEmissao, r.dataVencimento], ['87654321000120', 'Eunapolis', 89.9, '2026-10-27', '2026-11-17']);
  assert.equal(r.descricaoServico, 'LINK INTERNET 400MB');
});

test('NFCom (modelo 62) com vencimento da fatura', () => {
  const xml = `<nfcomProc><NFCom><infNFCom Id="NFCom29261098765432000110620010000162101069255993"><ide><nNF>16210</nNF><serie>1</serie><dhEmi>2026-10-27T09:49:06-03:00</dhEmi></ide>
    <emit><CNPJ>98765432000110</CNPJ><xNome>WKVE LTDA</xNome></emit><dest><CNPJ>87654321000120</CNPJ><xNome>EXPRESSO BRASILEIRO</xNome></dest>
    <det><prod><xProd>SCM 400MB</xProd><vProd>89.90</vProd></prod></det><total><vNF>89.90</vNF></total><gFat><CompetFat>202610</CompetFat><dVencFat>2026-11-17</dVencFat></gFat></infNFCom></NFCom></nfcomProc>`;
  const r = XF.lerXmlFiscal(xml);
  assert.deepEqual([r.tipoXml, r.numero, r.valorTotal, r.dataVencimento, r.competencia], ['nfcom', '16210', 89.9, '2026-11-17', '2026-10']);
});

test('recusa DOCTYPE/ENTITY, texto que não é XML e tipo desconhecido', () => {
  assert.equal(XF.lerXmlFiscal('<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><x>&a;</x>').ok, false);
  assert.equal(XF.lerXmlFiscal('%PDF-1.4').ok, false);
  assert.match(XF.lerXmlFiscal('<pedido><id>1</id></pedido>').erro, /não reconhecido/);
  assert.equal(XF.lerXmlFiscal('').ok, false);
});

test('prioridade do XML sobre o PDF e registro das divergências', { skip: !fs.existsSync(PASTA) }, () => {
  const pdf = { numero: '999999999', chave: '999999999', emissorNome: 'OPIX', valorTotal: 100, dataVencimento: '2026-11-20', camposParaRevisar: ['numero', 'chave'] };
  const xml = XF.lerXmlFiscal(fs.existsSync(PASTA) ? fs.readFileSync(path.join(PASTA, '01-ITABUNA-7001001-CONNECT-FIBRA.xml'), 'utf8') : '');
  const r = XF.aplicarPrioridadeXml(pdf, xml);
  assert.equal(r.numero, '7001001'); // padrão do PDF não conta como divergência
  assert.equal(r.valorTotal, 89.9);
  assert.equal(r.origemCampos, 'xml');
  assert.deepEqual(r.divergenciasXml.map((d) => d.campo), ['valorTotal']);
  assert.ok(r.camposParaRevisar.includes('divergenciasXml') && !r.camposParaRevisar.includes('numero'));
  // Sem XML válido, nada muda.
  assert.deepEqual(XF.aplicarPrioridadeXml(pdf, { ok: false }), pdf);
});
test('mesmo número com zeros à esquerda e CNPJ com pontuação não são divergência (NFCom Infortel: 000004572 x 4572)', () => {
  const xml = { ok: true, numero: '4572', cnpjEmissor: '54321098000150', valorTotal: 1880 };
  const r = XF.aplicarPrioridadeXml({ numero: '000004572', cnpjEmissor: '54.321.098/0001-50', valorTotal: 1880, camposParaRevisar: [] }, xml);
  assert.deepEqual(r.divergenciasXml, []);
  assert.ok(!r.camposParaRevisar.includes('divergenciasXml'));
  const outro = XF.aplicarPrioridadeXml({ numero: '4573', valorTotal: 1880, camposParaRevisar: [] }, xml);
  assert.deepEqual(outro.divergenciasXml.map((d) => d.campo), ['numero']);
});
