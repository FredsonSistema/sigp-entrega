// Confere a sintaxe dos nós Code do WF-08 gerado (serve também para o WF-10: copie-o para /tmp/wf08.json).
// Uso (PowerShell, na raiz do projeto):
//   docker cp n8n_workflow_wf08_gmail_inbox.json sigp_n8n:/tmp/wf08.json
//   Get-Content n8n\wf08\verificar_sintaxe.js -Raw | docker exec -i sigp_n8n node
const wf = JSON.parse(require('fs').readFileSync('/tmp/wf08.json', 'utf8'));
let erros = 0;
for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code')) {
  try {
    // O n8n executa o nó Code como função assíncrona (aceita await, ex.: getBinaryDataBuffer).
    const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;
    new AsyncFunction('$input', '$json', '$', '$env', node.parameters.jsCode);
    console.log('sintaxe ok:', node.name);
  } catch (e) {
    erros += 1;
    console.log('ERRO:', node.name, '-', e.message);
  }
}
const nomes = new Set(wf.nodes.map((n) => n.name));
for (const [origem, saida] of Object.entries(wf.connections)) {
  if (!nomes.has(origem)) { erros += 1; console.log('ERRO: conexão de nó inexistente', origem); }
  for (const ramo of saida.main) for (const alvo of ramo || []) {
    if (!nomes.has(alvo.node)) { erros += 1; console.log('ERRO: conexão para nó inexistente', alvo.node); }
  }
}
const semEntrada = wf.nodes.filter((n) => !/trigger|\.webhook$/i.test(n.type)  // webhook também é gatilho (WF-10)
  && !Object.values(wf.connections).some((s) => s.main.some((r) => (r || []).some((a) => a.node === n.name))));
for (const n of semEntrada) { erros += 1; console.log('ERRO: nó sem entrada', n.name); }
console.log(erros ? `${erros} problema(s)` : `workflow ok: ${wf.nodes.length} nós`);
process.exitCode = erros ? 1 : 0;
