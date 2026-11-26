# RAG com embeddings: critério definido antes da medição

Escrito em 26/11/2026, **antes** de medir qualquer modelo de embedding. O commit deste arquivo e do conjunto
[`rag-parafrases.json`](rag-parafrases.json) é anterior ao da evidência (`sqlserver/evidence/parte3/rag-embeddings.json`), para
que o critério e os casos não sejam ajustados ao resultado. Atende ao pedido da Prof.ª Bruna para a entrega final: "RAG com
embeddings".

## A pergunta

A busca da IA acadêmica é **lexical** (palavras em comum, no estilo BM25, com reforço para os termos do contrato). Ela acerta
quando a fatura usa as palavras do contrato e falha quando usa outras ("IP estático" × "IP fixo", "locação do roteador" ×
"aluguel de equipamento"). Embeddings comparam o **sentido** do texto. A pergunta: a busca por embeddings, sozinha ou junto com a
lexical, traz as fontes certas mais vezes, sem piorar o que já funciona?

## O que não muda

- **O escopo vem antes da busca.** Só entram documentos do local e do provedor da credencial (LOC-001/PROV-001) e as políticas
  gerais. A busca, de qualquer tipo, só ordena o que o escopo já permite: nenhum documento de outro local pode voltar.
- **A decisão continua sendo da regra** sobre a evidência estruturada; o modelo só sugere.
- Tudo local (Ollama), sem serviço externo.

## Candidatos

| Modelo (Ollama) | Download | Observação |
|---|---|---|
| `nomic-embed-text` | ~274 MB | o menor; treinado sobretudo em inglês |
| `embeddinggemma` | ~621 MB | multilíngue |
| `bge-m3` | ~1,2 GB | multilíngue, o maior |

Métodos: **lexical** (o atual), **embedding** (cada modelo, similaridade de cosseno) e **híbrido** (lexical + embedding pela
fusão de postos recíprocos, RRF com k = 60).

## Conjuntos

1. **Paráfrases** ([`rag-parafrases.json`](rag-parafrases.json), 14 consultas): a cobrança com palavras que não estão no documento.
2. **Os 16 casos finais** ([`casos-finais.json`](casos-finais.json)): a descrição da fatura como chega hoje; as fontes obrigatórias
   de cada caso.

Métrica principal: **revocação@5** (a fonte obrigatória está entre os 5 documentos trazidos). Também: revocação@3, MRR (posição
média da primeira fonte certa) e latência da consulta.

## Critério de escolha (fixado agora)

1. **Não piorar o que funciona:** nos 16 casos finais, a revocação@5 do método escolhido tem de ser **igual ou maior** que a da
   lexical. Depois de ligado, a avaliação completa da IA (`avaliar_ia.py`) tem de repetir o acerto da decisão (16/16).
2. **Ganho real nas paráfrases:** pelo menos **+20 pontos percentuais** de revocação@5 sobre a lexical. Abaixo disso, a busca
   continua lexical e o resultado é registrado como achado.
3. Entre os que passam em 1 e 2: o de **maior revocação@5 nas paráfrases**; empate (diferença de até 1 consulta) → o **menor
   download**.
4. Limites: download do modelo de embedding até **1,3 GB**; latência mediana da consulta até **1 s** na CPU.
5. Entre "embedding sozinho" e "híbrido" com o mesmo modelo, o critério 1 decide primeiro; se os dois passarem, o de maior
   revocação@5 nas paráfrases.

## Riscos

- Embedding pode trazer um documento "parecido" e errado (por exemplo, a política de IP para uma fatura de voz). Mitigação: a
  decisão continua na regra, que exige o termo do contrato; o modelo só sugere.
- Mais tempo por consulta (cada fatura gera um vetor). Medido.
- Mais um download na instalação. Medido e limitado (critério 4).
