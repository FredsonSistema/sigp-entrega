// Testes das funções de wf08_lib.js com dados fictícios.
// Executar (PowerShell, na raiz do projeto):
//   Get-Content n8n\wf08\wf08_lib.js, n8n\wf08\testes_wf08.js -Raw | docker exec -i sigp_n8n node
const assert = require('assert');
const SYSTEM_PROMPT = 'teste';
let falhas = 0;
const caso = (nome, fn) => {
  try { fn(); console.log(`ok   - ${nome}`); } catch (e) { falhas += 1; console.log(`FALHA - ${nome}: ${e.message}`); }
};

const boleto = [
  'Recibo do Pagador',
  'Beneficiário                     Agência/Código      Nosso número',
  'FIBRA EXEMPLO TELECOM LTDA        00.000.000/0001-91',
  'Nº Documento: 77001               Vencimento: 10/11/2026     Valor documento 129,90',
  '12345.67890 12345.678901 12345.678901 1 16260000012990',
  'Pagador',
  'ROTA TRANSPORTES RODOVIARIOS LTDA      11.222.333/0001-81',
  'AVENIDA EXEMPLO, 100 - 40000-000 SALVADOR',
  '(+) ACESSO A INTERNET FIBRA 300M - PERIODO 01/10/2026 A 31/10/2026    R$ 129,90',
].join('\n');

caso('linha digitável gera valor e vencimento (fator 1626 = 10/11/2026)', () => {
  const r = lerLinhaDigitavel(boleto);
  assert.strictEqual(r.linhaDigitavel.length, 47);
  assert.strictEqual(r.valorBoleto, 129.9);
  assert.strictEqual(r.vencimentoBoleto, '2026-11-10');
});

caso('extração separa emissor e destinatário', () => {
  const e = extrairCampos(boleto);
  assert.strictEqual(e.cnpjEmissor, '00000000000191');
  assert.strictEqual(e.cnpjDestinatario, '11222333000181');
  assert.ok(e.empresaDestinataria.startsWith('ROTA TRANSPORTES RODOVIARIOS LTDA'), e.empresaDestinataria);
  assert.strictEqual(e.numero, '77001');
  assert.strictEqual(e.dataVencimento, '2026-11-10');
  assert.ok(e.descricaoServico.startsWith('ACESSO A INTERNET'), e.descricaoServico);
});

caso('datas e competência são normalizadas', () => {
  assert.strictEqual(normalizarData('10/11/2026'), '2026-11-10');
  assert.strictEqual(normalizarData('2026-02-30'), '');
  assert.strictEqual(normalizarCompetencia('10/2026'), '2026-10');
});

const meta = { remetente: 'Fibra Exemplo <fatura@fibraexemplo.net>', assunto: 'Sua fatura chegou', origemBusca: 'nova' };

caso('fatura coerente vai para associação sem revisão', () => {
  const ia = { tipoDocumento: 'boleto_fatura', provedorNome: 'FIBRA EXEMPLO TELECOM LTDA', empresaDestinataria: 'ROTA TRANSPORTES RODOVIARIOS LTDA', valor: 129.9, vencimento: '2026-11-10', competencia: '2026-10', confianca: 0.9, motivo: 'boleto de internet' };
  const r = consolidar({ ia, iaErro: '', regras: { categoria: 'FATURA_INTERNET' }, ext: extrairCampos(boleto), meta, modelo: 'qwen2.5:3b' });
  assert.strictEqual(r.decisao, 'importar');
  assert.strictEqual(r.dadosExtracao.revisaoManual, false, r.dadosExtracao.camposParaRevisar.join(','));
  assert.strictEqual(r.dadosExtracao.valorTotal, 129.9);
});

caso('divergência entre IA e boleto manda para revisão', () => {
  const ia = { tipoDocumento: 'boleto_fatura', provedorNome: 'FIBRA EXEMPLO', valor: 12.99, vencimento: '10/11/2026', confianca: 0.95 };
  const r = consolidar({ ia, iaErro: '', regras: {}, ext: extrairCampos(boleto), meta, modelo: 'm' });
  assert.strictEqual(r.dadosExtracao.valorTotal, 129.9);
  assert.ok(r.dadosExtracao.camposParaRevisar.includes('divergencias'));
  assert.strictEqual(r.dadosExtracao.revisaoManual, true);
});

caso('IA não pode usar empresa do grupo como provedor nem endereço como cliente', () => {
  const ia = { tipoDocumento: 'boleto_fatura', provedorNome: 'EXPRESSO BRASILEIRO TRANSPORTES LTDA', empresaDestinataria: 'RUA EXEMPLO, 10 - 40000-000', confianca: 0.9 };
  const r = consolidar({ ia, iaErro: '', regras: {}, ext: extrairCampos('Total a pagar R$ 50,00'), meta, modelo: 'm' });
  assert.strictEqual(r.dadosExtracao.emissorNome, 'Fibra Exemplo');
  assert.strictEqual(r.dadosExtracao.empresaDestinataria, '');
});

caso('documento sem cobrança com IA segura e regras fracas é ignorado', () => {
  const ia = { tipoDocumento: 'outro', confianca: 0.9, motivo: 'recibo de multa' };
  const r = consolidar({ ia, iaErro: '', regras: { categoria: 'REVISAO' }, ext: extrairCampos('RECIBO DE PAGAMENTO 12,55'), meta, modelo: 'm' });
  assert.strictEqual(r.decisao, 'ignorar');
});

caso('remetente cadastrado impede ignorar', () => {
  const ia = { tipoDocumento: 'outro', confianca: 0.9 };
  const r = consolidar({ ia, iaErro: '', regras: { categoria: 'REVISAO', provedoresPorRemetente: ['Fibra Exemplo'] }, ext: extrairCampos(''), meta, modelo: 'm' });
  assert.strictEqual(r.decisao, 'importar');
});

caso('nota fiscal sem sinal de internet e IA segura: ignorada (baixa), mesmo com termo fiscal', () => {
  const ia = { tipoDocumento: 'outro', confianca: 0.9, motivo: 'locação de software' };
  const regras = { categoria: 'DOCUMENTO_FISCAL_REVISAO', palavrasFiscais: ['nfse'], palavrasInternet: [], provedoresEncontrados: [] };
  const r = consolidar({ ia, iaErro: '', regras, ext: extrairCampos('NFS-e locação de software R$ 1.910,52'), meta, modelo: 'm', caracteresTexto: 7000 });
  assert.strictEqual(r.decisao, 'ignorar');
  assert.strictEqual(r.probabilidade, 'baixa');
  assert.strictEqual(r.autoDescarte, false);
});

caso('PDF sem texto legível nunca é ignorado (inconclusivo)', () => {
  const ia = { tipoDocumento: 'outro', confianca: 0.9, motivo: 'texto de OCR sem frases legíveis' };
  const r = consolidar({ ia, iaErro: '', regras: { categoria: 'REVISAO' }, ext: extrairCampos(''), meta, modelo: 'm', caracteresTexto: 12 });
  assert.strictEqual(r.decisao, 'importar');
  assert.strictEqual(r.probabilidade, 'inconclusivo');
});

caso('termo de internet com IA dizendo "não é cobrança": inconclusivo, não ignora', () => {
  const ia = { tipoDocumento: 'outro', confianca: 0.95 };
  const r = consolidar({ ia, iaErro: '', regras: { categoria: 'REVISAO', palavrasInternet: ['wi-fi'] }, ext: extrairCampos('hotel wi-fi'), meta, modelo: 'm', caracteresTexto: 900 });
  assert.strictEqual(r.decisao, 'importar');
  assert.strictEqual(r.probabilidade, 'inconclusivo');
});

caso('remetente confirmado 3 vezes: descarte automático mesmo se a IA hesitar', () => {
  const ia = { tipoDocumento: 'nota_fiscal', confianca: 0.6 };
  const regras = { categoria: 'DOCUMENTO_FISCAL_REVISAO', remetente: { confirmadosNaoCobranca: 3, cobrancasConfirmadas: 0 } };
  const r = consolidar({ ia, iaErro: '', regras, ext: extrairCampos('NFS-e'), meta, modelo: 'm', caracteresTexto: 5000 });
  assert.strictEqual(r.decisao, 'ignorar');
  assert.strictEqual(r.autoDescarte, true);
});

caso('remetente que já teve cobrança associada nunca é descartado automaticamente', () => {
  const ia = { tipoDocumento: 'outro', confianca: 0.9 };
  const regras = { categoria: 'DOCUMENTO_FISCAL_REVISAO', remetente: { confirmadosNaoCobranca: 5, cobrancasConfirmadas: 1 } };
  const r = consolidar({ ia, iaErro: '', regras, ext: extrairCampos('NFS-e'), meta, modelo: 'm', caracteresTexto: 5000 });
  assert.strictEqual(r.autoDescarte, false);
  assert.strictEqual(r.probabilidade, 'baixa');
});

caso('alta probabilidade sem valor vira inconclusivo; OCR com erro também', () => {
  assert.strictEqual(probabilidadeFinal({ emissorNome: 'X', dataVencimento: '2026-12-10' }, 'alta', '').probabilidade, 'inconclusivo');
  assert.strictEqual(probabilidadeFinal({ emissorNome: 'X', valorTotal: 10, dataVencimento: '2026-12-10' }, 'alta', 'ok').probabilidade, 'alta');
  assert.strictEqual(probabilidadeFinal({}, 'baixa', '', { ocrErro: true }).probabilidade, 'inconclusivo');
  assert.strictEqual(probabilidadeFinal({}, 'baixa', '', { xml: true }).probabilidade, 'inconclusivo');
});

caso('evento: frase da regra vale; sem frase, a LLM com 80%+; senão fatura nova', () => {
  const ia = { tipoDocumento: 'lembrete', confianca: 0.9, evento: 'aviso_atraso' };
  const ext = extrairCampos('Total R$ 10,00');
  const porRegra = consolidar({ ia, iaErro: '', regras: { evento: { tipo: 'pagamento_confirmado', frase: 'recebemos seu pagamento' } }, ext, meta, modelo: 'm' });
  assert.strictEqual(porRegra.dadosExtracao.evento.tipo, 'pagamento_confirmado');
  const porIA = consolidar({ ia, iaErro: '', regras: { evento: { tipo: 'fatura_nova' } }, ext, meta, modelo: 'm' });
  assert.deepStrictEqual([porIA.dadosExtracao.evento.tipo, porIA.dadosExtracao.evento.origem], ['aviso_atraso', 'ia']);
  const duvida = consolidar({ ia: { ...ia, confianca: 0.5 }, iaErro: '', regras: {}, ext, meta, modelo: 'm' });
  assert.strictEqual(duvida.dadosExtracao.evento.tipo, 'fatura_nova');
});

caso('provedor da IA que não aparece no documento é descartado (não copia de exemplo)', () => {
  const ia = { tipoDocumento: 'nota_fiscal', confianca: 0.95, provedorNome: 'JEQUIE FIBRA NET LTDA' };
  const r = consolidar({ ia, iaErro: '', regras: {}, ext: extrairCampos('Fatura Claro S.A. Total R$ 52,42'), meta: { ...meta, remetente: 'Fatura Claro <faturadigital@minhaclaro.com.br>' }, modelo: 'm', texto: 'Fatura Claro S.A. Total R$ 52,42' });
  assert.notStrictEqual(r.dadosExtracao.emissorNome, 'JEQUIE FIBRA NET LTDA');
  const ok = consolidar({ ia: { ...ia, provedorNome: 'CLARO S.A.' }, iaErro: '', regras: {}, ext: extrairCampos(''), meta, modelo: 'm', texto: 'Fatura Claro S.A.' });
  assert.strictEqual(ok.dadosExtracao.emissorNome, 'CLARO S.A.');
});

caso('falha da IA importa para revisão e nunca ignora', () => {
  const lido = lerRespostaIA({ error: { message: 'timeout' } });
  const r = consolidar({ ia: lido.ia, iaErro: lido.erro, regras: {}, ext: extrairCampos(''), meta, modelo: 'm' });
  assert.strictEqual(r.decisao, 'importar');
  assert.ok(r.dadosExtracao.camposParaRevisar.includes('classificacaoIA'));
});

caso('resposta do Ollama é lida do campo message.content', () => {
  const lido = lerRespostaIA({ message: { content: '{"tipoDocumento":"lembrete","confianca":0.8}' } });
  assert.strictEqual(lido.ia.tipoDocumento, 'lembrete');
  assert.strictEqual(lerRespostaIA({ message: { content: 'texto' } }).ia, null);
});


// Boleto OPIX — texto real extraído pelo OCR do BOLETO_302500.pdf
// Layout de colunas: rótulos na linha, valores na linha seguinte.
const boletoOpix = [
  'Recibo do Pagador',
  'Beneficiário                                                                 Agência/Código do Beneficiário    Espécie     Quantidade     Nosso número',
  'OPIX SERVICOS DE TECNOLOGIA EIRELI                                                                             R$                               000000000000038115',
  'Nº Documento                                       CPF/CNPJ                           Vencimento                           Valor documento',
  '302500                                             32.109.876/0001-70                 10/11/2026                                                              119,90',
  'Demonstrativo',
  'Referente ao Acesso a Internet via Fibra de 11/10/2026 a 10/11/2026',
  'Pagador',
  'ROTA TRANSPORTES RODOVIÁRIOS LTDA                                                                                                   Contrato: 4821',
  'RUA EXEMPLO, 100 - GARAGEM DA ROTA TRANSPORTES                                                                               CPF/CNPJ: 76.543.210/0001-30',
  '_____________________________________________________________________________',
  'Local de Pagamento                                                                                                         Vencimento',
  'Qualquer agência bancária                                                                                                                                10/11/2026',
  'Beneficiário                                                                                                               Agência/Código do Beneficiário',
  'OPIX SERVICOS DE TECNOLOGIA EIRELI',
  'Data do documento            Nº Documento                            Espécie Doc.       Aceite     Data Processamento      Nosso Número',
  '04/09/2026                   302500                                  DM                 A          04/09/2026                                  000000000000038115',
  'Uso do banco                 Carteira                Espécie       Quantidade                         Valor documento      (=) Valor documento',
  '                             0                       R$                                                                                                     119,90',
].join('\n');

caso('OPIX: numero nao captura CNPJ', () => {
  const e = extrairCampos(boletoOpix);
  assert.strictEqual(e.numero, '302500', `Obtido: "${e.numero}"`);
});

caso('OPIX: data do documento capturada como dataEmissao', () => {
  const e = extrairCampos(boletoOpix);
  assert.strictEqual(e.dataEmissao, '2026-09-04', `Obtido: "${e.dataEmissao}"`);
});

caso('OPIX: vencimento extraido corretamente', () => {
  const e = extrairCampos(boletoOpix);
  assert.strictEqual(e.dataVencimento, '2026-11-10', `Obtido: "${e.dataVencimento}"`);
});

caso('OPIX: emissor identificado pelo CNPJ', () => {
  const e = extrairCampos(boletoOpix);
  assert.strictEqual(e.cnpjEmissor, '32109876000170', `Obtido: "${e.cnpjEmissor}"`);
});

// VCA Telecomunicacoes — NFCom com "Nº.:" e "DATA EMISSÃO" em coluna lateral
const nfcomVca = [
  'EMITENTE',
  '                                                                                                                        Nº.: 16713                                                   DANFECom',
  '                    VCA Telecomunicacoes LTDA',
  'CNPJ                                                                  INSCRIÇÃO ESTADUAL                                                         FINALIDADE                                              DATA EMISSÃO',
  '21.098.765/0001-80                                                    123456789                                                                  NFCom Normal                                            05/11/2026 16:14:47',
  'ROTA TRANSPORTES RODOVIARIOS LTDA                                                                                                                                          76.543.210/0001-30',
  'DADOS DA FATURA',
  'VENCIMENTO                                          COMPETÊNCIA',
  '                               10/11/2026                                              10/2026',
  '75691.00009 01234.567890 12345.678901 9 16260000059999',
].join('\n');

caso('VCA NFCom: numero extraido do padrao "Nº.:"', () => {
  const e = extrairCampos(nfcomVca);
  assert.strictEqual(e.numero, '16713', `Obtido: "${e.numero}"`);
});

caso('VCA NFCom: dataEmissao extraida de coluna lateral com horario', () => {
  const e = extrairCampos(nfcomVca);
  assert.strictEqual(e.dataEmissao, '2026-11-05', `Obtido: "${e.dataEmissao}"`);
});

caso('VCA NFCom: vencimento via coluna', () => {
  const e = extrairCampos(nfcomVca);
  assert.strictEqual(e.dataVencimento, '2026-11-10', `Obtido: "${e.dataVencimento}"`);
});

caso('VCA NFCom: linha digitavel extrai valor', () => {
  const e = extrairCampos(nfcomVca);
  assert.strictEqual(e.valorBoleto, 599.99, `Obtido: "${e.valorBoleto}"`);
});

// DSTECH (Saturno Comunicacoes) — boleto com "Nº documento" em coluna
const boletoDstech = [
  'Beneficiário                                                                CPF/CNPJ Beneficiário      Ag/Cod. Beneficiário           Vencimento',
  'SATURNO COMUNICACOES LTDA                                                   10.987.654/0001-90                         1234 / 56789                       10/11/2026',
  'Pagador',
  '                                                                                                       Nº documento                   Nosso número',
  'EXP***** / 13.***.***/****-07',
  '                                                                                                                           2767076                        2082408-9',
  'Data do documento                  Nº documento                  Espécie doc.       Aceite   Data processamento        Nosso número',
  '05/11/2026                         2767076                       DS                 N        06/11/2026                                                   2082408-9',
].join('\n');

caso('DSTECH: numero extraido da coluna (nao captura "Nosso")', () => {
  const e = extrairCampos(boletoDstech);
  assert.strictEqual(e.numero, '2767076', `Obtido: "${e.numero}"`);
});

caso('DSTECH: dataEmissao via "Data do documento" em coluna', () => {
  const e = extrairCampos(boletoDstech);
  assert.strictEqual(e.dataEmissao, '2026-11-05', `Obtido: "${e.dataEmissao}"`);
});

caso('DSTECH: vencimento na primeira secao do boleto', () => {
  const e = extrairCampos(boletoDstech);
  assert.strictEqual(e.dataVencimento, '2026-11-10', `Obtido: "${e.dataVencimento}"`);
});
console.log(falhas ? `${falhas} teste(s) falharam` : 'todos os testes passaram');
process.exitCode = falhas ? 1 : 0;
