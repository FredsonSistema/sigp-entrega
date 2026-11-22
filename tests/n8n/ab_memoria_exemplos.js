// A/B da memória de exemplos (etapa 4) com a LLM real (qwen2.5:3b no Ollama local).
// Mesmo documento, com e sem exemplos do operador. Monta o pedido com o código do nó do WF-08 gerado.
// Uso, na raiz:  node tests/n8n/ab_memoria_exemplos.js   (chama o Ollama pelo container sigp_academic_ai)
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, '..', '..');
const wf = JSON.parse(fs.readFileSync(path.join(RAIZ, 'n8n_workflow_wf08_gmail_inbox.json'), 'utf8'));
const code = wf.nodes.find((n) => n.name === 'Extrair campos e montar pedido à IA').parameters.jsCode;
const SAIDA = path.join(RAIZ, 'docs', 'entrega-academica', 'sqlserver', 'evidence', 'parte2', 'memoria-exemplos-ab.json');

const meta = { remetente: '"Reservas" <reservas@hotel-exemplo.com.br>', assunto: 'Faturamento Hotel - Técnico Ilhéus', nomeArquivo: 'Nota_Fiscal_Hotel_Ilheus.pdf', corpo: 'Segue a nota da hospedagem do técnico.' };
const texto = 'NOTA FISCAL DE SERVIÇO ELETRÔNICA\nPrestador: POUSADA BEIRA MAR LTDA CNPJ 11.222.333/0001-81\nTomador: ROTA TRANSPORTES RODOVIARIOS LTDA\n'
  + 'Discriminação do serviço: Hospedagem de técnico - 3 diárias - serviço de internet Wi-Fi incluso\nValor total: R$ 450,00\nVencimento: 25/11/2026';
const exemplos = [
  { id: 'nrec-ceb5b929', rotulo: 'nao_cobranca', remetente: 'reservas@hotel-exemplo.com.br', assunto: 'Faturamento Hotel - Técnico Itabuna', motivo: 'Não é cobrança de internet/telecom' },
];

function pedido(comExemplos) {
  const itens = {
    'Recuperar itens e etiquetas': { json: meta, binary: {} },
    'OCR local': { json: { text: texto } },
    'Classificar com regras do SIGp': { json: { classificacao: {} } },
  };
  // eslint-disable-next-line no-new-func
  return new Function('$json', '$', '$env', code)({ exemplos: comExemplos ? exemplos : [] }, (n) => ({ item: itens[n] }), {}).json.ollamaBody;
}

function chamar(body) {
  const py = "import sys,urllib.request as u;r=u.Request('http://ollama:11434/api/chat',data=sys.stdin.buffer.read(),headers={'Content-Type':'application/json'});print(u.urlopen(r,timeout=600).read().decode())";
  const inicio = Date.now();
  const saida = execFileSync('docker', ['exec', '-i', 'sigp_academic_ai', 'python', '-c', py], { input: JSON.stringify(body), encoding: 'utf8', maxBuffer: 1e7 });
  const resp = JSON.parse(saida);
  return { ms: Date.now() - inicio, resposta: JSON.parse(resp.message.content) };
}

const resultado = { executado_em_utc: new Date().toISOString(), modelo: 'qwen2.5:3b (temperatura 0)', documento: meta, texto, exemplos, rodadas: [] };
for (const comExemplos of [false, true]) {
  const r = chamar(pedido(comExemplos));
  resultado.rodadas.push({ comExemplos, latencia_ms: r.ms, tipoDocumento: r.resposta.tipoDocumento, confianca: r.resposta.confianca, motivo: r.resposta.motivo, provedorNome: r.resposta.provedorNome });
  console.log(`${comExemplos ? 'COM ' : 'SEM '} exemplos: ${r.resposta.tipoDocumento} (confiança ${r.resposta.confianca}) em ${r.ms} ms — ${r.resposta.motivo}`);
}
fs.writeFileSync(SAIDA, JSON.stringify(resultado, null, 2));
