# Escolha do modelo da triagem do Gmail: critério definido antes da medição

Escrito em 21/11/2026, **antes** de ver os resultados da medição ([`tests/n8n/comparar_modelos_triagem.js`](../../../tests/n8n/comparar_modelos_triagem.js)).
O commit deste arquivo é anterior ao da evidência (`sqlserver/evidence/parte3/triagem-modelos.json`), para que o critério não seja
ajustado ao resultado.

## A decisão

O pacote de instalação da entrega precisa baixar pouco. Hoje a triagem do Gmail (WF-08) usa o Qwen 2.5 3B (cerca de 1,9 GB) e a
IA acadêmica usa o 0,5B (cerca de 400 MB). A pergunta: um modelo menor faz a triagem bem o bastante?

| Opção | Download total | Observação |
|---|---|---|
| A. 0,5B para tudo | ~400 MB | mesmo modelo nas duas partes |
| B. 0,5B + 1,5B na triagem | ~1,4 GB | intermediário |
| C. 0,5B + 3B (como hoje) | ~2,3 GB | o melhor medido até agora |
| D. leve por padrão, 3B opcional | 400 MB ou 2,3 GB | o professor escolhe |

## Riscos de um modelo menor

- Errar o tipo de documento, o evento ou o provedor, e mandar mais documentos para revisão humana.
- Ler uma fatura de internet como "outro". O documento só é ignorado se, além disso, as regras do SIGp não acharem evidência e não
  houver boleto; senão, vai para Revisão.
- O que **não** muda: valor e vencimento da linha digitável prevalecem sobre a IA; provedor que não aparece no documento é descartado;
  falha ou resposta inválida vai para Revisão, nunca é ignorada.

## Critério (fixado antes da medição)

1. Na variante com `num_predict = 512` (a que seria proposta para a produção), **nenhum erro grave** e **nenhum tempo esgotado**.
   Erro grave: fatura de internet lida como "outro", ou documento que não é de internet lido como cobrança.
2. Acerto de campos **até 10 pontos percentuais abaixo do 3B** na mesma variante.
3. Entre os modelos que passam em 1 e 2, o de **menor download**.
4. Se nenhum modelo menor passar, o pacote fica com a opção D (leve por padrão, com o 3B opcional e o aviso do que se perde),
   ou com a C, se a diferença for grande.

## Como é medido

- 10 documentos fictícios com o esperado tirado das definições do prompt (`n8n/wf08/prompt_classificacao.md`): fatura, fatura com
  NFCom, segunda via, lembrete, aviso de atraso, pagamento confirmado, nota de hotel, NFS-e sem boleto, conta de energia e boleto com
  OCR ruidoso.
- O pedido é montado pelo próprio código do nó do WF-08 (mesmo prompt, mesmo JSON Schema, temperatura 0); só o modelo muda.
- Duas variantes: o pedido **como o WF-08 manda hoje** e com `num_predict = 512`. A segunda entrou porque, no primeiro aquecimento,
  o 1,5B não terminou a resposta em 15 minutos (geração sem fim, sem limite de tamanho).
- Modelos e variantes intercalados, documento a documento; cada um aquecido antes; limite de 300 s por pedido, o mesmo do nó do
  WF-08 (depois disso o documento vai para Revisão).
- Campos pontuados: tipo de documento, evento, provedor, empresa pagadora, valor e vencimento, quando o documento os tem.
