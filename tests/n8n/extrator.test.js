// Testes da n8n/lib/extrator.js (B-01). Rodar:  node --test tests/n8n/extrator.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const X = require('../../n8n/lib/extrator.js');

// Linha digitável fictícia: fator 1626 = 22/02/2025 + 626 dias = 2026-11-10; valor 119,90.
const LINHA = '23790.12345 60000.123456 78901.234567 1 16260000011990';

test('número vazio recebe o padrão 999999999 e vai para revisão', () => {
  const r = X.extrairDoTexto({ texto: 'Prestador: OPIX INTERNET LTDA\nValor total: R$ 119,90\nVencimento: 10/11/2026' });
  assert.equal(r.numero, '999999999');
  assert.equal(r.numeroPadrao, true);
  assert.ok(r.camposParaRevisar.includes('numero'));
  assert.equal(r.emissorNome, 'OPIX INTERNET LTDA');
  assert.equal(r.valorTotal, 119.9);
  assert.equal(r.dataVencimento, '2026-11-10');
});

test('número lido que é rótulo, data ou CNPJ vira padrão e guarda o original', () => {
  assert.equal(X.motivoNumeroInvalido('12.345.678/0001-90'), 'parece CNPJ/CPF');
  assert.equal(X.motivoNumeroInvalido('05/11/2026'), 'parece uma data');
  assert.equal(X.motivoNumeroInvalido('R$ 10,00'), 'parece um valor em dinheiro');
  assert.equal(X.motivoNumeroInvalido('0000'), 'só zeros');
  assert.equal(X.motivoNumeroInvalido('302500'), '');
  const c = X.aplicarPadraoIdentificacao({ numero: '0000', chave: '' });
  assert.deepEqual([c.numero, c.numeroOriginal, c.chave, c.chavePadrao], ['999999999', '0000', '999999999', true]);
  assert.ok(!c.camposParaRevisar.includes('chave')); // chave vazia é normal em boleto
});

test('linha digitável prevalece sobre o texto para valor e vencimento', () => {
  const r = X.extrairDoTexto({ texto: `Beneficiário: VOX TELECOM LTDA\nValor do documento 200,00\nVencimento: 01/01/2027\n${LINHA}` });
  assert.equal(r.linhaDigitavelUsada, true);
  assert.equal(r.valorTotal, 119.9);
  assert.equal(r.dataVencimento, '2026-11-10');
});

test('boleto em colunas: rótulo numa linha, valor na seguinte', () => {
  const texto = 'Nº documento       Vencimento\n77001              05/11/2026\n(+) Serviço de internet R$ 89,90';
  const r = X.extrairDoTexto({ texto });
  assert.equal(r.numero, '77001');
  assert.equal(r.dataVencimento, '2026-11-05');
  assert.equal(r.descricaoServico, 'Serviço de internet');
});

test('"Nº.:" do DANFECom: \\b com º funciona como no Python', () => {
  assert.equal(X.extrairDoTexto({ texto: 'DANFECom\nNº.: 16713\nWKVE TELECOMUNICACOES LTDA' }).numero, '16713');
});

test('chave da NFS-e nacional (50 dígitos) na linha de baixo do rótulo', () => {
  const chave = '29333071221098765000180260000001575226110027288988';
  assert.equal(X.extrairDoTexto({ texto: `CHAVE DE ACESSO DA NFS-e\n${chave}\n\nNÚMERO DA NFS-e\n2600000015752` }).chave, chave);
  // Tamanho fora de 44/50: não inventa chave.
  assert.equal(X.extrairDoTexto({ texto: 'CHAVE DE ACESSO\n1234567890123456789012345678901234567890123' }).chave, '999999999');
});

test('"Nº documento:" no meio da linha, seguido de outras colunas', () => {
  assert.equal(X.extrairDoTexto({ texto: '41310-600 - SALVADOR   Nº documento: 2847941\nR$ 174,00' }).numero, '2847941');
});

test('DANFE-COM: "NOTA FISCAL Nº" no meio da linha e chave em grupos de 4 com DV conferido', () => {
  const texto = 'EXPRESSO BRASILEIRO TRANSPORTES   NOTA FISCAL Nº 16210 - SÉRIE: 1\n'
    + 'INSCRIÇÃO ESTADUAL:   12345678   CHAVE DE ACESSO:\n'
    + 'CÓD. DO CLIENTE: 31457   2926 1098 7654 3200 0110 6200 1000 0162 1010 6925 5993';
  const r = X.extrairDoTexto({ texto });
  assert.equal(r.numero, '16210');
  assert.equal(r.chave, '29261098765432000110620010000162101069255993');
  // Mesmo formato com o último dígito trocado: DV não confere, não vira chave.
  assert.equal(X.extrairDoTexto({ texto: texto.replace(/5993$/, '5994') }).chave, '999999999');
});

test('descrição: não pega a linha seguinte nem rótulos de encargo do boleto', () => {
  const d = (texto) => X.extrairDoTexto({ texto }).descricaoServico;
  assert.equal(d('Discriminação do serviço:\n\nDescrição   Contrato   Valor Unitário   Qtde.\nLINK FIBRA 400MB   204567   R$ 76,95'), 'LINK FIBRA 400MB');
  assert.equal(d('(-) Desconto   (+) Mora / Multa / Juros   (+) Outros acréscimos   (=) Valor cobrado'), '');
  assert.equal(d('(+) Mora / Multa\n(+) Prestação de serviço de internet - Plano: FIBRA 350 MEGAS - R$ 79.99   Autenticação mecânica'),
    'Prestação de serviço de internet - Plano: FIBRA 350 MEGAS');
  assert.equal(d('(+) Outros acréscimos\nReferente ao Acesso a Internet via Fibra de 11/10/2026 a 10/11/2026'), 'Acesso a Internet via Fibra de 11/10/2026 a 10/11/2026');
  assert.equal(d('Ref. 10/10/2026 até 09/11/2026   Rua X'), '');
  assert.equal(d('Descrição do serviço: Internet 300MB'), 'Internet 300MB');
});

test('data inexistente não é aceita', () => {
  assert.equal(X.parseDataOcr('31/02/2026'), '');
  assert.equal(X.parseDataOcr('05/11/2026 16:14:47'), '2026-11-05');
  assert.equal(X.parseDataOcr('2026-1-5'), '2026-01-05');
});

test('empresa do grupo nunca é emissora', () => {
  // A empresa do grupo aparece primeiro e com cara de razão social; as linhas logo após "Tomador" são do cliente.
  const texto = 'EXPRESSO BRASILEIRO TRANSPORTES LTDA\nITS TELECOMUNICACOES LTDA\nCNPJ 22.222.222/0001-22\n'
    + 'Tomador CNPJ: 11.111.111/0001-11\nEXPRESSO BRASILEIRO TRANSPORTES LTDA';
  const r = X.extrairDoTexto({ texto });
  assert.equal(r.emissorNome, 'ITS TELECOMUNICACOES LTDA');
  assert.equal(r.cnpjEmissor, '22222222000122');
});

test('comparação com o esperado e PDF sem texto', () => {
  const r = X.extrairDoTexto({ texto: 'Fatura OPIX\nTotal a pagar: 119,90', provedorEsperado: 'Opix', valorEsperado: '119.90' });
  assert.deepEqual([r.emissorNome, r.comparacao.emissorConfere, r.comparacao.valorConfere], ['Opix', true, true]);
  const vazio = X.extrairDoTexto({ texto: '   ' });
  assert.equal(vazio.textEncontrado, false);
  assert.ok(vazio.aviso);
  assert.deepEqual(vazio.camposParaRevisar, ['emissorNome', 'valorTotal', 'dataVencimento', 'numero']);
});

// NFS-e Nacional (texto fictício no layout real): rótulo e valor em colunas, em linhas diferentes. Antes saía vazio e a IA
// preenchia R$ 0,30; "Valor Total Apurado - IBS" (imposto, R$ 0,03) não pode virar o valor da conta.
test('NFS-e Nacional: valor total em coluna, sem pegar o imposto', () => {
  assert.equal(X.extrairDoTexto({ texto: 'Alíq. Efetiva Municipal - IBS                Valor Apurado Municipal - IBS                 Alíq. Efetiva Estadual - IBS\n0,00 %                                       R$ 0,00                                       0,10 %\nValor Total Apurado - IBS                    Alíquota - CBS                                Alíquota Efetiva - CBS\nR$ 0,03                                      0,90 %                                        0,90 %\nVALOR TOTAL DA NFS-E                         VALOR DA OPERAÇÃO / SERVIÇO                   Desconto Incondicionado\nR$ 15,00                                      -                                                    -\nTotal das Retenções (ISSQN / Federais)       VALOR LÍQUIDO DA NFS-e                        Total do IBS/CBS\n-                                            R$ 15,00                                      R$ 0,13\n' }).valorTotal, 15);
  assert.equal(X.extrairDoTexto({ texto: 'Total das Retenções (ISSQN / Federais)       VALOR LÍQUIDO DA NFS-e                        Total do IBS/CBS\n-                                            R$ 1.234,50                                   R$ 0,13\n' }).valorTotal, 1234.5);
  assert.equal(X.extrairDoTexto({ texto: 'Valor Total Apurado - IBS                    Alíquota - CBS\nR$ 0,03                                      0,90 %\n' }).valorTotal, null);
});
