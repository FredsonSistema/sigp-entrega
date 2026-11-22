// Testes da importação CSV (frontend/modules/importar-csv.js). Contatos fictícios. Rodar: node --test tests/n8n/importar_csv.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../../frontend/modules/importar-csv.js');

const CAB = '\uFEFFNome;Cidade;CEP;Endereço;Número;Vencimento Fatura;Última Visita;Responsáveis;Provedores;Redes;Marcadores;Observações';
const CSV = [
  CAB,
  'CNPC;ITABUNA;;Fernando;;;;Fernando - (11) 90000-0001;CLARO 500Mb - (73) 90000-0002 | VOX 10Mb Dedicado - 0800 020 4100;172.16.12.3;Regional Itabuna | Propria | RT;',
  'CAMAMU;Camamu;45445000;Rodoviaria Camamu;S/N;;;MARTINS/LIVIA - (73) 90000-0003 | (73) 90000-0004;CONECT TELECOM - 7500000010;;Regional Jequíe | Terceirizado | CS;Proprietario paga a conexão',
  'DARIO MEIRA;Dário Meira;45590000;DARIO MEIRA;S/N;;;ROMILDA - (73) 90000-0005 - romilda@exemplo.com;CONSULTAR;;Regional Jequíe | CS;',
  'SALA VIP ARACAJU;Aracaju;49080470;Avenida Tancredo Neves;S/N;;;;Opix 300Mb - 129,90 - 7935121681 | Brisanet - 888182-0637 - https://www.brisanet.com.br/;172.16.12.14:8135;;',
  'ITAMARAJU;Itamaraju;45836000;Praça Castelo Branco;S/N;;;;Megatech - 08001232017;0000aaaa1111.sn.mynetname.net - 172.16.12.44;Regional Eunapolis | EB;',
  'São Gonçalo;Cachoeira;44300000;Rua CENTRO;S/N;;;Clemilda - (75) 90000-0006;Tsunami Net - 7582095408 - http://138.255.240.6:8000/central - venc. dia 10;Sem rede Mikrotik;;Responsável por São Gonçalo.',
  'BOM DESPACHO;Vera Cruz;44470000;BOM DESPACHO;S/N;28/09/2026;05/09/2026;OSMUNDO - (73) 90000-0007;RAMOS NET - RAMOS NET;;Regional Jequíe | CS;',
  'ANDARAI;ANDARAI;;;;;;Marleide - (75) 90000-0008;Ibisol - 7500000009 - venc. dia 20;;CS;"Empresa paga a conta e cobra do agente\nVIACAO JEQUIE - ITABERABA\t65.432.109/0001-40"',
  'ROD ARACAJU;Aracaju;49095-000;Av. Tancredo Neves;s/n;05/10/2026;;Janilton - (79) 90000-0009;OPIX SERVICOS - 79 3512-1681 - venc. dia 5 | OPIX SERVICOS - 83 3113-2512 - venc. dia 5;;Regional Salvador | RT;',
  ';SEM NOME;;;;;;;;;;',
  'CNPC;ITABUNA;;;;;;;;;;',
].join('\r\n');

test('lê o CSV: BOM, CRLF, aspas com quebra de linha', () => {
  const linhas = C.lerCsv(CSV);
  assert.equal(linhas.length, 12);
  assert.match(linhas[8][11], /cobra do agente\nVIACAO JEQUIE/);
});

test('prévia: criar, erro e repetido no arquivo', () => {
  const p = C.previaLocais(CSV, []);
  const acoes = p.linhas.map((l) => l.acao);
  assert.deepEqual(acoes, ['criar', 'criar', 'criar', 'criar', 'criar', 'criar', 'criar', 'criar', 'criar', 'erro', 'juntar']);
});

test('responsáveis: telefone sem nome herda o nome anterior; e-mail separado', () => {
  const { registro } = C.paraLocal({ nome: 'X', cidade: 'Y', responsaveis: 'MARTINS/LIVIA - (73) 90000-0003 | (73) 90000-0004 | ROMILDA - (73) 90000-0005 - romilda@exemplo.com' });
  assert.deepEqual(registro.responsaveis.map((r) => [r.nome, r.telefone, r.email]), [
    ['MARTINS/LIVIA', '(73) 90000-0003', ''], ['MARTINS/LIVIA', '(73) 90000-0004', ''], ['ROMILDA', '(73) 90000-0005', 'romilda@exemplo.com'],
  ]);
});

test('provedores: dia de vencimento, valor, URL, CONSULTAR, nome repetido e provedor duplicado na linha', () => {
  const p = C.previaLocais(CSV, []).linhas;
  const sala = p[3].registro.provedores;
  assert.deepEqual([sala[0].nome, sala[0].valor, sala[0].contato], ['Opix 300Mb', '129.90', '7935121681']);
  assert.match(sala[1].contato, /brisanet\.com\.br/);
  const tsunami = p[5].registro.provedores[0];
  assert.deepEqual([tsunami.nome, tsunami.diaVencimento], ['Tsunami Net', '10']);
  assert.equal(p[2].registro.provedores.length, 0); // CONSULTAR não é provedor
  assert.match(p[2].registro.obs, /Provedor: CONSULTAR/);
  assert.ok(p[2].avisos.some((a) => /não é nome de provedor/.test(a)));
  assert.deepEqual(p[6].registro.provedores.map((x) => [x.nome, x.contato]), [['RAMOS NET', '']]);
  const opix = p[8].registro.provedores;
  assert.equal(opix.length, 1); // mesmo provedor com dois telefones vira um só
  assert.match(opix[0].contato, /79 3512-1681 \/ 83 3113-2512/);
});

test('redes: IP com porta, dois endereços e texto sem IP', () => {
  const p = C.previaLocais(CSV, []).linhas;
  assert.deepEqual(p[3].registro.redes, [{ label: '', ipWireguard: '172.16.12.14:8135' }]);
  assert.equal(p[4].registro.redes[0].ipWireguard, '0000aaaa1111.sn.mynetname.net');
  assert.match(p[4].registro.redes[0].label, /172\.16\.12\.44/);
  assert.equal(p[5].registro.redes.length, 0);
  assert.match(p[5].registro.obs, /Rede: Sem rede Mikrotik/);
});

test('datas, marcadores e visita', () => {
  const r = C.previaLocais(CSV, []).linhas[6].registro;
  assert.equal(r.vencimentoFatura, '2026-09-28');
  assert.equal(r.ultimaVisita, '2026-09-05');
  assert.deepEqual(r.marcadores, ['Regional Jequíe', 'CS']);
});

test('atualizar não apaga nem mexe no valor/vencimento da fatura do provedor', () => {
  const existentes = [{
    id: 'a_1', nome: 'cnpc', cidade: 'Itabuna', cep: '45600000', obs: 'antiga',
    provedores: [{ id: 'p1', nome: 'CLARO 500Mb', valor: '199.90', dataVencimento: '2026-11-20', contato: '' }],
    responsaveis: [], redes: [],
  }];
  const p = C.previaLocais(CSV, existentes);
  assert.equal(p.linhas[0].acao, 'atualizar');
  const cont = C.aplicarLocais(p, existentes, new Set(p.linhas.map((l) => l.linha)));
  assert.equal(existentes.length, 9); // 1 atualizado + 8 novos (erro e repetido não criam)
  assert.equal(cont.criados, 8);
  const cnpc = existentes[0];
  assert.deepEqual([cnpc.cep, cnpc.obs], ['45600000', 'antiga']);
  const claro = cnpc.provedores.find((x) => x.nome === 'CLARO 500Mb');
  assert.deepEqual([claro.valor, claro.dataVencimento, claro.contato], ['199.90', '2026-11-20', '(73) 90000-0002']);
  assert.ok(cnpc.provedores.some((x) => x.nome === 'VOX 10Mb Dedicado'));
  assert.ok(existentes.every((e) => e.id) && existentes.flatMap((e) => e.provedores).every((x) => x.id));
  // Importar de novo o mesmo arquivo não muda nada.
  const de_novo = C.previaLocais(CSV, existentes);
  assert.ok(de_novo.linhas.filter((l) => l.acao !== 'erro').every((l) => l.acao === 'igual'), JSON.stringify(de_novo.linhas.map((l) => [l.acao, l.mudancas])));
});

test('sistemas: senha na observação não é importada; repetido fica igual', () => {
  const csv = '\uFEFFNome;Tipo;URL/IP;Usuário;Observação\r\nUnifi;Servidor;https://10.0.0.1:8443/;admin;Troca@2021\r\nZabbix;Monitoramento;http://10.0.0.2/zabbix;ti;Monitoramento da matriz\r\nZabbix;Monitoramento;http://10.0.0.2/zabbix;ti;';
  const p = C.previaSistemas(csv, []);
  assert.deepEqual(p.linhas.map((l) => l.acao), ['criar', 'criar', 'igual']);
  assert.equal(p.linhas[0].registro.observacao, '');
  assert.ok(p.linhas[0].avisos.some((a) => /parece uma senha/.test(a)));
  assert.equal(p.linhas[1].registro.observacao, 'Monitoramento da matriz');
  const lista = [];
  assert.equal(C.aplicarSistemas(p, lista, new Set([2, 3, 4])).criados, 2);
});

test('cabeçalho errado é recusado', () => {
  assert.match(C.previaLocais('Cidade;CEP\nX;Y', []).erro, /Nome/);
});
