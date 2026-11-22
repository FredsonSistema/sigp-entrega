// Nós 'Janela desde a última leitura' e 'Retirar mensagens já lidas' do WF-08 (leitura automática pela busca do SIGp).
// Uso: node tests/n8n/wf08_janela.test.js n8n_workflow_wf08_gmail_inbox.json
const wf = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const code = (n) => wf.nodes.find((x) => x.name === n).parameters.jsCode;
const estado = {};
const run = (src, ctx) => new Function('$getWorkflowStaticData', '$json', '$input', '$', src)(() => estado, ctx.json, { all: () => ctx.itens || [] }, () => ({ first: () => ({ json: ctx.janela }) }));
let falhas = 0; const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) falhas++; };
const consulta = '-label:sigp-importado -label:sigp-ignorado -label:sigp-sem-anexo {from:(a.com) subject:(fatura)}';
let j = run(code('Janela desde a última leitura'), { json: { consulta } })[0].json;
ok(/after:\d+$/.test(j.q) && j.q.startsWith(consulta), 'primeira leitura: busca do SIGp + after');
ok(Number(j.q.split('after:')[1]) <= j.inicio - 900 + 1, 'primeira leitura olha 15 min para tras');
let s = run(code('Retirar mensagens já lidas'), { janela: j, itens: [{ json: { id: 'm1' } }, { json: { id: 'm2' } }] });
ok(s.length === 2 && estado.ultimaLeitura === j.inicio, 'entrega 2 novas e grava a hora');
const j2 = run(code('Janela desde a última leitura'), { json: { consulta } })[0].json;
ok(Number(j2.q.split('after:')[1]) === j.inicio - 300, 'segunda leitura: 5 min de sobreposicao');
s = run(code('Retirar mensagens já lidas'), { janela: j2, itens: [{ json: { id: 'm2' } }, { json: { id: 'm3' } }] });
ok(s.length === 1 && s[0].json.id === 'm3', 'sobreposicao nao repete m2');
s = run(code('Retirar mensagens já lidas'), { janela: j2, itens: [{ json: {} }] });
ok(s.length === 0, 'caixa vazia (item vazio do alwaysOutputData) nao segue');
let erro = ''; try { run(code('Janela desde a última leitura'), { json: { ok: false, error: 'x' } }); } catch (e) { erro = e.message; }
ok(/Configura/.test(erro), 'sem busca do SIGp: erro, nada e lido');
for (let i = 0; i < 600; i++) estado.vistas.push('x' + i);
run(code('Retirar mensagens já lidas'), { janela: j2, itens: [] });
ok(estado.vistas.length === 500, 'lista de vistas limitada a 500');
const t = wf.nodes.map((n) => n.type);
ok(!t.includes('n8n-nodes-base.gmailTrigger') && !JSON.stringify(wf).includes('@gmail.com'), 'sem gatilho fixo e sem gmail no JSON');
console.log(falhas ? falhas + ' falha(s)' : 'todos passaram'); process.exit(falhas ? 1 : 0);
