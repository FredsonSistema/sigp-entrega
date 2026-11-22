// Mesmos casos de backend/identificadores.py (tests/casos_identificadores.json) na função do WF-08.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, '..', '..');
const lib = fs.readFileSync(path.join(RAIZ, 'n8n', 'wf08', 'wf08_lib.js'), 'utf8');
// eslint-disable-next-line no-new-func
const { lerIdentificadoresCliente, normalizarCodigo } = new Function(`${lib}\nreturn { lerIdentificadoresCliente, normalizarCodigo };`)();
const casos = JSON.parse(fs.readFileSync(path.join(RAIZ, 'tests', 'casos_identificadores.json'), 'utf8'));

for (const caso of casos) {
  test(caso.nome, () => {
    assert.deepStrictEqual(lerIdentificadoresCliente(caso.texto).map((i) => [i.tipo, i.valor]), caso.esperado);
  });
}
test('normalização igual à do backend', () => {
  assert.strictEqual(normalizarCodigo('00077120'), '77120');
  assert.strictEqual(normalizarCodigo('CT-778/2'), 'CT7782');
});
