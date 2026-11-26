# RAG com embeddings: medição e escolha

Documento gerado por `ia/medir_rag_embeddings.py documento` a partir de [`sqlserver/evidence/parte3/rag-embeddings.json`](../sqlserver/evidence/parte3/rag-embeddings.json) (medido em 2026-11-26T13:42:42+00:00). O critério foi fixado e versionado antes da medição: [`rag-embeddings-criterio.md`](rag-embeddings-criterio.md).

## Modelos

| Modelo | Download | Dimensão | Vetorizar os 20 documentos |
|---|---:|---:|---:|
| `nomic-embed-text` | 274 MB | 768 | 3936 ms |
| `embeddinggemma` | 622 MB | 768 | 4819 ms |
| `bge-m3` | 1158 MB | 1024 | 7879 ms |

## Resultado

| Método | Paráfrases r@5 | Paráfrases r@3 | Paráfrases MRR | Casos finais r@5 | Latência mediana | Fora do escopo |
|---|---:|---:|---:|---:|---:|---|
| lexical | 7/14 (50%) | 6/14 (43%) | 0.33 | 14/14 (100%) | 0 ms | nenhum |
| embedding:nomic-embed-text | 9/14 (64%) | 7/14 (50%) | 0.32 | 14/14 (100%) | 88 ms | nenhum |
| hibrido:nomic-embed-text | 8/14 (57%) | 6/14 (43%) | 0.36 | 14/14 (100%) | 88 ms | nenhum |
| embedding:embeddinggemma | 13/14 (93%) | 12/14 (86%) | 0.77 | 14/14 (100%) | 145 ms | nenhum |
| hibrido:embeddinggemma | 10/14 (71%) | 7/14 (50%) | 0.42 | 14/14 (100%) | 146 ms | nenhum |
| embedding:bge-m3 | 13/14 (93%) | 12/14 (86%) | 0.74 | 14/14 (100%) | 214 ms | nenhum |
| hibrido:bge-m3 | 10/14 (71%) | 7/14 (50%) | 0.35 | 14/14 (100%) | 214 ms | nenhum |

## Critério aplicado

| Método | 1. Não piora os casos finais | 2. Ganho ≥ 20 pp | Ganho | 4. Download ≤ 1,3 GB | 4. Latência ≤ 1 s | Escopo | Passa |
|---|---|---|---:|---|---|---|---|
| embedding:nomic-embed-text | sim | **não** | +14.3 pp | sim | sim | sim | **não** |
| hibrido:nomic-embed-text | sim | **não** | +7.1 pp | sim | sim | sim | **não** |
| embedding:embeddinggemma | sim | sim | +42.9 pp | sim | sim | sim | sim |
| hibrido:embeddinggemma | sim | sim | +21.4 pp | sim | sim | sim | sim |
| embedding:bge-m3 | sim | sim | +42.9 pp | sim | sim | sim | sim |
| hibrido:bge-m3 | sim | sim | +21.4 pp | sim | sim | sim | sim |

## Decisão

**embedding:embeddinggemma** (regra 3: maior revocação@5 nas paráfrases entre os aprovados; empate de até 1 consulta vai para o menor download). Ganho de +42.9 pp sobre a lexical nas paráfrases, sem perder nenhum caso final.

## Consultas que a lexical perde

| Consulta | Fontes | Lexical (top 5) | embedding:embeddinggemma (top 5) |
|---|---|---|---|
| RP-04 | DOC-POL-04 | DOC-ALFA-03, DOC-POL-10, DOC-ALFA-01, DOC-POL-07, DOC-POL-11 | DOC-ALFA-03, DOC-POL-04, DOC-POL-05, DOC-ALFA-02, DOC-POL-10 |
| RP-05 | DOC-POL-05 | DOC-ALFA-03, DOC-ALFA-01, DOC-POL-07, DOC-POL-11, DOC-ALFA-02 | DOC-POL-05, DOC-ALFA-01, DOC-ALFA-02, DOC-ALFA-03, DOC-POL-07 |
| RP-06 | DOC-POL-08 | DOC-ALFA-01, DOC-ALFA-02, DOC-ALFA-03 | DOC-POL-08, DOC-ALFA-01, DOC-ALFA-02, DOC-POL-12, DOC-POL-07 |
| RP-07 | DOC-POL-09 | DOC-POL-01, DOC-ALFA-01, DOC-ALFA-02, DOC-ALFA-03 | DOC-POL-09, DOC-POL-03, DOC-POL-02, DOC-POL-06, DOC-ALFA-02 |
| RP-08 | DOC-POL-06 | DOC-ALFA-03, DOC-ALFA-01, DOC-POL-07, DOC-POL-11, DOC-ALFA-02 | DOC-ALFA-03, DOC-POL-06, DOC-ALFA-01, DOC-ALFA-02, DOC-POL-10 |
| RP-10 | DOC-POL-03 | DOC-ALFA-02, DOC-ALFA-01, DOC-POL-01, DOC-POL-02, DOC-POL-09 | DOC-POL-03, DOC-POL-09, DOC-POL-01, DOC-ALFA-02, DOC-ALFA-03 |
| RP-12 | DOC-POL-02 | DOC-ALFA-02, DOC-ALFA-01, DOC-ALFA-03 | DOC-ALFA-03, DOC-ALFA-01, DOC-ALFA-02, DOC-POL-02, DOC-POL-09 |

## Consultas que embedding:embeddinggemma ainda perde

- RP-11: precisava de DOC-POL-01; trouxe DOC-POL-09, DOC-ALFA-02, DOC-ALFA-03, DOC-ALFA-01, DOC-POL-03.

## Avaliação completa da IA com o embedding ligado (critério 1)

| Rodada | Modelo de embedding | Casos aprovados | Decisão certa | Falsas aprovações | Injeção detectada | Validação cega | Latência média |
|---|---|---:|---:|---:|---:|---:|---:|
| lexical (prompt v3.1) ([`ia-avaliacao-prompt-v31.json`](../sqlserver/evidence/parte3/ia-avaliacao-prompt-v31.json)) | — | 16/16 | 16/16 | 0 | 13/13 | 4/8 | 3572 ms |
| embedding ligado ([`ia-avaliacao-rag-embeddings.json`](../sqlserver/evidence/parte3/ia-avaliacao-rag-embeddings.json)) | embeddinggemma | 16/16 | 16/16 | 0 | 13/13 | 4/8 | 3623 ms |
| final (embedding + regra de outra unidade) ([`ia-avaliacao-final.json`](../sqlserver/evidence/parte3/ia-avaliacao-final.json)) | embeddinggemma | 16/16 | 16/16 | 0 | 13/13 | 4/8 | 4595 ms |

## Onde fica no sistema

`ia/app.py` (`retrieve_with_method`): com `EMBED_MODEL` definido, os documentos do escopo são ordenados pelo cosseno entre o vetor da fatura e o de cada documento (os 20 vetores são calculados uma vez); sem a variável, ou se o Ollama falhar, a busca é a lexical. A resposta de `/api/analyze` informa a busca usada (`rag_method`). A decisão continua na regra sobre a evidência estruturada.
