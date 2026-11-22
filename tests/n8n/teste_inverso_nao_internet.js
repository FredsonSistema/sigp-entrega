// Teste inverso: documento que NÃO é de internet/telecom passa pela cadeia completa do WF-08 atual
// (OCR → regras do SIGp → exemplos → LLM qwen2.5:3b com o prompt v4.1 → decisão), sem gravar nada.
// Usa PDFs já guardados no SIGp. Uso, na raiz:  node tests/n8n/teste_inverso_nao_internet.js <id-nota> [<id-nota> ...]
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const RAIZ = path.join(__dirname, '..', '..');
const wf = JSON.parse(fs.readFileSync(path.join(RAIZ, 'n8n_workflow_wf08_gmail_inbox.json'), 'utf8'));
const codigo = (nome) => wf.nodes.find((n) => n.name === nome).parameters.jsCode;
const lib = fs.readFileSync(path.join(RAIZ, 'n8n', 'wf08', 'wf08_lib.js'), 'utf8');
// eslint-disable-next-line no-new-func
const { consolidar, lerRespostaIA } = new Function(`${lib}\nreturn { consolidar, lerRespostaIA };`)();
const SAIDA = path.join(RAIZ, 'docs', 'entrega-academica', 'sqlserver', 'evidence', 'parte2', 'teste-inverso-nao-internet.json');

// OCR, regras e exemplos de dentro do container da API (mesmos serviços que o n8n chama).
const PY_SIGP = String.raw`
import sys, json, os, sqlite3, urllib.request as u, urllib.parse as p
nid = sys.argv[1]
c = sqlite3.connect('/app/backend/data/sigp.db'); c.row_factory = sqlite3.Row
r = c.execute('select remetente, assunto, nome_arquivo, arquivo_storage, dados_json from notas_recebidas where id=?', (nid,)).fetchone()
pdf = open('/app/backend/data/notas_recebidas/' + r['arquivo_storage'], 'rb').read()
def chamar(url, data=None, tipo='application/json', metodo=None):
    req = u.Request(url, data=data, method=metodo, headers={'Content-Type': tipo, 'X-API-Key': os.environ['SIGP_API_KEY']})
    try:
        return json.loads(u.urlopen(req, timeout=300).read().decode())
    except Exception as e:
        return {'erro': str(e)[:300]}
ocr = chamar('http://ocr:5002/extract', pdf, 'application/pdf')
texto = str(ocr.get('text') or '')
api = 'http://127.0.0.1:5001'
regras = chamar(api + '/api/notas-recebidas/classificar', json.dumps({'texto': texto, 'assunto': r['assunto'], 'remetente': r['remetente'], 'nomeArquivo': r['nome_arquivo']}).encode())
q = p.urlencode({'remetente': r['remetente'], 'assunto': r['assunto'], 'limite': 4})
exemplos = chamar(api + '/api/llm/exemplos?' + q)
antes = json.loads(r['dados_json']).get('classificacao') or {}
print(json.dumps({'meta': {'remetente': r['remetente'], 'assunto': r['assunto'], 'nomeArquivo': r['nome_arquivo'], 'corpo': ''},
                  'texto': texto, 'ocrErro': ocr.get('erro') or ocr.get('error') or '', 'regras': regras.get('classificacao') or {},
                  'exemplos': exemplos.get('exemplos') or [],
                  'antes': {'categoria': antes.get('categoria'), 'confianca': antes.get('confianca'), 'ia': antes.get('ia')}}, ensure_ascii=False))
`;
const PY_OLLAMA = "import sys,urllib.request as u;r=u.Request('http://ollama:11434/api/chat',data=sys.stdin.buffer.read(),headers={'Content-Type':'application/json'});print(u.urlopen(r,timeout=900).read().decode())";

const resultado = { executado_em_utc: new Date().toISOString(), modelo: 'qwen2.5:3b (temperatura 0)', prompt: 'v4.1', casos: [] };
for (const id of process.argv.slice(2)) {
  const doc = JSON.parse(execFileSync('docker', ['exec', 'sigp_api', 'python', '-c', PY_SIGP, id], { encoding: 'utf8', maxBuffer: 1e8 }));
  const itens = {
    'Recuperar itens e etiquetas': { json: doc.meta, binary: {} },
    'OCR local': { json: { text: doc.texto } },
    'Classificar com regras do SIGp': { json: { classificacao: doc.regras } },
  };
  // eslint-disable-next-line no-new-func
  const pedido = new Function('$json', '$', '$env', codigo('Extrair campos e montar pedido à IA'))(
    { exemplos: doc.exemplos }, (n) => ({ item: itens[n] }), {}).json;
  const inicio = Date.now();
  let resposta;
  try {
    resposta = JSON.parse(execFileSync('docker', ['exec', '-i', 'sigp_academic_ai', 'python', '-c', PY_OLLAMA],
      { input: JSON.stringify(pedido.ollamaBody), encoding: 'utf8', maxBuffer: 1e7 }));
  } catch (e) { resposta = { erro: String(e.message).slice(0, 300) }; }
  const ms = Date.now() - inicio;
  const { ia, erro } = lerRespostaIA(resposta);
  const r = consolidar({ ia, iaErro: erro, regras: pedido.regras, ext: pedido.extracao, meta: doc.meta, modelo: pedido.modelo, ocrUsado: true });
  const caso = {
    id, assunto: doc.meta.assunto, arquivo: doc.meta.nomeArquivo, caracteresOcr: doc.texto.length, ocrErro: doc.ocrErro,
    antes: doc.antes,
    agora: {
      regras: { categoria: doc.regras.categoria, confianca: doc.regras.confianca, palavrasFiscais: doc.regras.palavrasFiscais, palavrasInternet: doc.regras.palavrasInternet },
      exemplosUsados: doc.exemplos.map((e) => `${e.rotulo}:${e.id}`),
      ia: ia ? { tipoDocumento: ia.tipoDocumento, confianca: ia.confianca, motivo: ia.motivo, provedorNome: ia.provedorNome } : { erro },
      latencia_ms: ms,
      decisao: r.decisao,
    },
  };
  resultado.casos.push(caso);
  console.log(`${id} ${doc.meta.nomeArquivo} | OCR ${doc.texto.length} car. ${doc.ocrErro ? '(erro OCR)' : ''}| regras ${doc.regras.categoria} ${doc.regras.confianca} | exemplos ${doc.exemplos.length} | IA ${caso.agora.ia.tipoDocumento} ${caso.agora.ia.confianca} "${caso.agora.ia.motivo || caso.agora.ia.erro}" | ${ms} ms | decisão: ${r.decisao}`);
}
fs.writeFileSync(SAIDA, JSON.stringify(resultado, null, 2));
console.log('FIM');
