# Escolha do modelo da triagem do Gmail

Gerado por `gerar_escolha_modelo.py` a partir das evidências [`triagem-modelos.json`](../sqlserver/evidence/parte3/triagem-modelos.json) (primeira medição) e [`triagem-modelos-corrigido.json`](../sqlserver/evidence/parte3/triagem-modelos-corrigido.json) (depois da correção); nenhum número foi digitado à mão. O critério foi escrito e versionado **antes** da primeira medição: [`escolha-modelo-criterio.md`](escolha-modelo-criterio.md).

**Escolha final: opção C, `qwen2.5:3b` por padrão, `qwen2.5:0.5b` opcional (`instalar.ps1 -ModeloTriagem qwen2.5:0.5b`).**

## A decisão

O pacote da entrega precisa baixar pouco. Hoje a triagem do Gmail (WF-08) usa o Qwen 2.5 3B (~1,9 GB) e a IA acadêmica usa o 0,5B (~400 MB). Um modelo menor faria a triagem bem o bastante?

## Riscos de um modelo menor

- Errar o tipo de documento, o evento ou o provedor e mandar mais documentos para revisão humana.
- Ler uma fatura de internet como "outro" (candidata a ser ignorada se as regras também não acharem evidência e não houver boleto).
- Ler um documento que não é de internet como cobrança (iria para associação, com revisão humana).
- Não terminar a resposta: o nó do WF-08 desiste em 300 s e manda o documento para Revisão, mas trava a fila nesse tempo.

O que não muda com o modelo: valor e vencimento da linha digitável prevalecem sobre a IA, provedor que não aparece no documento é descartado, e falha ou resposta inválida vai para Revisão, nunca é ignorada.

## Como foi medido

- Método: pedido do nó do WF-08 (prompt, JSON Schema, temperatura 0); um modelo de cada vez, variantes intercaladas; aquecimento antes; limite de 300 s por pedido como no WF-08.
- 10 documentos fictícios, com o esperado tirado das definições do prompt:
  - T01: Fatura de internet com boleto
  - T02: Fatura e nota fiscal (NFCom) no mesmo PDF
  - T03: Segunda via com novo vencimento
  - T04: Lembrete de vencimento
  - T05: Aviso de atraso com bloqueio
  - T06: Pagamento confirmado
  - T07: Nota de hotel (não é cobrança de internet)
  - T08: NFS-e de internet sem boleto
  - T09: Conta de energia (outra concessionária, não internet)
  - T10: Boleto de internet com OCR ruidoso
- Campos pontuados quando o documento os tem: tipo, evento, provedor, empresa pagadora, valor e vencimento. Uma resposta inválida conta como 1 campo errado (`json`), então o percentual só compara bem modelos que responderam aos mesmos documentos.

## 1ª medição: o pedido como hoje e com limite de 512 tokens

| Modelo | Variante | Download | Campos certos | Respostas válidas | Tempo esgotado (300 s) | Erros graves | Latência média | p95 |
|---|---|---|---|---|---|---|---|---|
| `qwen2.5:0.5b` | como hoje | 397 MB | 25/42 (59,5%) | 10/10 | 0 | 2 | 9,2 s | 10,9 s |
| `qwen2.5:0.5b` | num predict 512 | 397 MB | 24/42 (57,1%) | 10/10 | 0 | 2 | 7,2 s | 8,4 s |
| `qwen2.5:1.5b` | como hoje | 986 MB | 0/3 (0,0%) | 0/10 | 3 (+7 não medidos) | 3 | 300,7 s | 300,8 s |
| `qwen2.5:1.5b` | num predict 512 | 986 MB | 0/10 (0,0%) | 0/10 | 0 | 10 | 55,8 s | 62,5 s |
| `qwen2.5:3b` | como hoje | 1.9 GB | 25/31 (80,6%) | 6/10 | 3 (+1 não medidos) | 4 | 131,2 s | 301,2 s |
| `qwen2.5:3b` | num predict 512 | 1.9 GB | 21/28 (75,0%) | 6/10 | 0 | 6 | 57,4 s | 92,5 s |

| Modelo | empresa | evento | json | provedor | tipo | valor | vencimento |
|---|---|---|---|---|---|---|---|
| `qwen2.5:0.5b` | 4/5 | 4/8 | — | 6/8 | 3/9 | 7/7 | 0/5 |
| `qwen2.5:1.5b` | — | — | 0/10 | — | — | — | — |
| `qwen2.5:3b` | 3/3 | 5/5 | 0/4 | 4/5 | 3/5 | 4/4 | 2/2 |

- Erros graves de `qwen2.5:0.5b`: T07: não-cobrança lida como cobrança; T09: não-cobrança lida como cobrança.
- Erros graves de `qwen2.5:1.5b`: T01: sem resposta válida (vai para Revisão); T02: sem resposta válida (vai para Revisão); T03: sem resposta válida (vai para Revisão); T04: sem resposta válida (vai para Revisão); T05: sem resposta válida (vai para Revisão); T06: sem resposta válida (vai para Revisão); T07: sem resposta válida (vai para Revisão); T08: sem resposta válida (vai para Revisão); T09: sem resposta válida (vai para Revisão); T10: sem resposta válida (vai para Revisão).
- Erros graves de `qwen2.5:3b`: T01: sem resposta válida (vai para Revisão); T03: sem resposta válida (vai para Revisão); T04: sem resposta válida (vai para Revisão); T05: cobrança lida como "outro"; T07: sem resposta válida (vai para Revisão); T09: não-cobrança lida como cobrança.

Pelo critério, na variante com limite: `qwen2.5:0.5b`: critério 1 não passa (2 erro(s) grave(s), 0 tempo(s) esgotado(s)); critério 2 não passa (57,1% dos campos contra 75,0% do 3B). `qwen2.5:1.5b`: critério 1 não passa (10 erro(s) grave(s), 0 tempo(s) esgotado(s)); critério 2 não passa (0,0% dos campos contra 75,0% do 3B). `qwen2.5:3b`: critério 1 não passa (6 erro(s) grave(s), 0 tempo(s) esgotado(s)); critério 2 passa (75,0% dos campos contra 75,0% do 3B). Nenhum modelo passa nos critérios 1 e 2: vale o item 4 do critério. Item 4: o 3B não é confiável nesta variante (6/10 respostas válidas, 0 tempo(s) esgotado(s), 17,9 pontos a mais): opção D.
Resultado da 1ª aplicação: opção D (`qwen2.5:0.5b` por padrão). O 3B não era confiável: sem limite, esgotou 300 s em parte dos documentos; com o limite, teve respostas cortadas.

## A causa e a correção

Olhando a resposta crua de um documento que travou, o 3B preenchia os campos certos, mas **o campo `motivo` não acabava**: continuava a frase até 700 tokens e o JSON nunca fechava. A correção, no próprio JSON Schema do WF-08: `maxLength` em cada texto (`motivo` até 200 caracteres, `vencimento` 10, `competencia` 7...), o que obriga o modelo a fechar o campo, mais `num_predict = 400` como segunda proteção. Ela passou a valer em produção no WF-08 (`n8n/wf08/schema_classificacao.json` e `build_wf08.ps1`).

## 2ª medição: com a correção (variante proposta para a produção)

| Modelo | Variante | Download | Campos certos | Respostas válidas | Tempo esgotado (300 s) | Erros graves | Latência média | p95 |
|---|---|---|---|---|---|---|---|---|
| `qwen2.5:3b` | corrigido | 1.9 GB | 37/42 (88,1%) | 10/10 | 0 | 2 | 36,4 s | 56,7 s |
| `qwen2.5:0.5b` | corrigido | 397 MB | 25/42 (59,5%) | 10/10 | 0 | 2 | 8,4 s | 9,6 s |

| Modelo | empresa | evento | provedor | tipo | valor | vencimento |
|---|---|---|---|---|---|---|
| `qwen2.5:3b` | 5/5 | 8/8 | 6/8 | 6/9 | 7/7 | 5/5 |
| `qwen2.5:0.5b` | 4/5 | 5/8 | 6/8 | 3/9 | 7/7 | 0/5 |

- Erros graves de `qwen2.5:3b`: T05: cobrança lida como "outro"; T09: não-cobrança lida como cobrança.
- Erros graves de `qwen2.5:0.5b`: T07: não-cobrança lida como cobrança; T09: não-cobrança lida como cobrança.

## A escolha, pelo mesmo critério

A variante proposta para a produção mudou depois da 1ª medição (era o limite de 512; passou a ser a corrigida). O critério é o mesmo, aplicado à nova variante. O item 4 não definia "diferença grande"; a definição usada, escrita junto com a correção, é: o 3B responde a todos os documentos, sem tempo esgotado, e acerta pelo menos 20 pontos percentuais a mais que o modelo leve.

1. `qwen2.5:3b`: critério 1 não passa (2 erro(s) grave(s), 0 tempo(s) esgotado(s)); critério 2 passa (88,1% dos campos contra 88,1% do 3B).
2. `qwen2.5:0.5b`: critério 1 não passa (2 erro(s) grave(s), 0 tempo(s) esgotado(s)); critério 2 não passa (59,5% dos campos contra 88,1% do 3B).
3. Nenhum modelo passa nos critérios 1 e 2: vale o item 4 do critério.
4. Item 4: o 3B respondeu 10/10 sem tempo esgotado e acertou 28,6 pontos percentuais a mais que o qwen2.5:0.5b (diferença grande: 20 ou mais): opção C.

**Escolha final: opção C, `qwen2.5:3b` por padrão, `qwen2.5:0.5b` opcional (`instalar.ps1 -ModeloTriagem qwen2.5:0.5b`)**.

O que isso significa no pacote: a triagem por IA só roda se o Gmail for conectado. Os dois modelos ainda erram a classificação de alguns documentos (os erros graves acima): esses vão para a revisão humana, e nada é pago nem ignorado por causa da IA. O sistema completo da empresa continua com o 3B, agora com a correção.
