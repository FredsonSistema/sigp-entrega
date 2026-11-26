# Fine-tuning: base × base com RAG × ajustado × ajustado com RAG

Gerado por `gerar_comparacao.py` a partir das evidências; nenhum número foi digitado à mão. Execução: [`comparar_finetuning.py`](comparar_finetuning.py), em 2026-11-26T18:57:50 UTC. Evidência: [`finetuning-comparacao.json`](../../sqlserver/evidence/parte3/finetuning-comparacao.json).

## Como foi medido

- **Mesmo modelo, mesmas condições.** `Qwen/Qwen2.5-0.5B-Instruct` (revisão `7ae557604adf`) em float32 na CPU, num único servidor Transformers. "Base" é esse modelo com o adaptador desligado; "ajustado" é o mesmo com o adaptador LoRA do SIGp (rank 4, `q_proj` e `v_proj`, treinado em 80 exemplos sintéticos). Geração sem amostragem, mesmo prompt de sistema do treino.
- **Só o modelo.** A decisão da regra não entra no prompt: aqui se mede se o modelo classifica sozinho.
- **RAG do sistema entregue.** Nos conjuntos A e C, "com RAG" usa os documentos que o próprio serviço avaliado recuperou em cada caso (busca por embedding, `embeddinggemma`, dentro do escopo LOC-001; `source_ids` gravados em [`ia-avaliacao-final.json`](../../sqlserver/evidence/parte3/ia-avaliacao-final.json)). Sem RAG, a Evidência diz "nenhuma evidência recuperada".
- **Fora do treino.** [`verificar_sobreposicao.py`](verificar_sobreposicao.py) comparou os 28 casos de teste com os 80 exemplos de treino: nenhum provedor em comum e nenhuma descrição igual. 6 casos finais (IA-001, IA-006, IA-008, IA-011, IA-012, IA-013) usam o mesmo nome de serviço do treino ("link principal fibra", "link de contingência"; semelhança 0,60, no limite fixado de 0,60), com outro provedor, valor e evidência; o resultado deles sai separado abaixo. Os 12 casos fora de escopo não se parecem com nenhum exemplo de treino (maior semelhança 0,43).
- **As quatro configurações rodaram intercaladas, caso a caso**, para a carga da máquina pesar igual em todas.
- **Custo por 1.000 usos.** Não há cobrança por token (modelo local). O custo vem do tempo de geração medido: tempo de CPU e energia do processador entre 15 W (potência base) e 55 W (turbo máximo), na tarifa de R$ 1,2418/kWh. Fontes: Intel Core i5-1345U: potência base 15 W, turbo máximo 55 W (ficha da Intel, via cpu-monkey.com/en/benchmark-intel_core_i5_1345u-cpu_performance_per_watt); Coelba, residencial B1 com impostos, vigência desde 22/04/2026 (ANEEL, Resolução Homologatória nº 3.578/2026; valor em apontasol.com.br/tarifa/coelba). Energia só do processador, estimada a partir do tempo de geração medido; tela, memória e o resto da máquina não entram. Não há cobrança por token (modelo local).

## Conjunto A: os 16 casos finais (fora do treino, RAG real)

| Configuração | RAG | Acerto | F1 macro | Falsas aprovações | Latência média (p95) | Tokens de entrada | 1.000 usos: CPU · energia |
|---|---|---|---|---|---|---|---|
| Modelo base | não | 4/16 (0,25) | 0,133 | 12 | 2,19 s (3,07 s) | 148 | 36,6 min · R$ 0,011 a 0,042 |
| Base com RAG | sim | 6/16 (0,38) | 0,281 | 10 | 3,49 s (4,37 s) | 463 | 58,2 min · R$ 0,018 a 0,066 |
| Modelo ajustado (LoRA) | não | 5/16 (0,31) | 0,159 | 0 | 1,55 s (1,86 s) | 148 | 25,9 min · R$ 0,008 a 0,029 |
| Ajustado com RAG | sim | 7/16 (0,44) | 0,348 | 1 | 3,63 s (4,29 s) | 463 | 60,4 min · R$ 0,019 a 0,069 |
| *Referência: regra do sistema (decisão)* | sim | 16/16 (1,00) | 1,000 | 0 | — | — | sem modelo |

O que cada configuração respondeu:

| Configuração | CONTRATADO | DIVERGENTE | REVISAR |
|---|---|---|---|
| Modelo base | 16 | 0 | 0 |
| Base com RAG | 14 | 0 | 2 |
| Modelo ajustado (LoRA) | 0 | 3 | 13 |
| Ajustado com RAG | 1 | 10 | 5 |

Casos que usam o nome de serviço do treino (6) × os que não usam (10): base com RAG 4/6 × 2/10; ajustado com RAG 1/6 × 6/10. Parecer com o treino não ajudou o modelo ajustado.

## Conjunto C: os 12 casos fora de escopo (nenhum parecido com o treino, RAG do sistema)

Outra conta (energia, água, aluguel, telefonia móvel, software, compra de equipamento), outro local, outro idioma e documentos que não são fatura ([`casos-fora-escopo.json`](../casos-fora-escopo.json)). Em todos, o certo é REVISAR.

| Configuração | RAG | Acerto | F1 macro | Falsas aprovações | Latência média (p95) | Tokens de entrada | 1.000 usos: CPU · energia |
|---|---|---|---|---|---|---|---|
| Modelo base | não | 0/12 (0,00) | 0,000 | 12 | 1,75 s (1,93 s) | 142 | 29,1 min · R$ 0,009 a 0,033 |
| Base com RAG | sim | 4/12 (0,33) | 0,167 | 8 | 3,24 s (3,77 s) | 430 | 54,1 min · R$ 0,017 a 0,062 |
| Modelo ajustado (LoRA) | não | 11/12 (0,92) | 0,319 | 0 | 1,55 s (1,66 s) | 142 | 25,8 min · R$ 0,008 a 0,029 |
| Ajustado com RAG | sim | 6/12 (0,50) | 0,222 | 0 | 3,15 s (3,39 s) | 430 | 52,6 min · R$ 0,016 a 0,060 |
| *Referência: regra do sistema (decisão)* | sim | 12/12 (1,00) | 0,333 | 0 | — | — | sem modelo |

| Configuração | CONTRATADO | DIVERGENTE | REVISAR |
|---|---|---|---|
| Modelo base | 12 | 0 | 0 |
| Base com RAG | 8 | 0 | 4 |
| Modelo ajustado (LoRA) | 0 | 1 | 11 |
| Ajustado com RAG | 0 | 6 | 6 |

## Conjunto B: os 20 casos de teste do treino (mesma distribuição do treino)

| Configuração | Evidência no prompt | Acerto | F1 macro | Falsas aprovações | Latência média (p95) | Tokens de entrada | 1.000 usos: CPU · energia |
|---|---|---|---|---|---|---|---|
| Modelo base | não | 6/20 (0,30) | 0,154 | 14 | 1,62 s (1,85 s) | 133 | 26,9 min · R$ 0,008 a 0,031 |
| Base com RAG | sim | 13/20 (0,65) | 0,522 | 7 | 1,69 s (2,11 s) | 144 | 28,2 min · R$ 0,009 a 0,032 |
| Modelo ajustado (LoRA) | não | 7/20 (0,35) | 0,233 | 0 | 1,66 s (1,82 s) | 133 | 27,7 min · R$ 0,009 a 0,032 |
| Ajustado com RAG | sim | 18/20 (0,90) | 0,900 | 0 | 1,71 s (1,94 s) | 144 | 28,5 min · R$ 0,009 a 0,032 |

| Configuração | CONTRATADO | DIVERGENTE | REVISAR |
|---|---|---|---|
| Modelo base | 20 | 0 | 0 |
| Base com RAG | 13 | 0 | 7 |
| Modelo ajustado (LoRA) | 0 | 4 | 16 |
| Ajustado com RAG | 5 | 8 | 7 |

Conferência: "base com evidência" (0,65, F1 0,522) e "ajustado com evidência" (0,90, F1 0,900) reproduzem o experimento da entrega 2 (`training-results.json`: 0,65 → 0,90 e F1 0,522 → 0,900).

## Análise

1. **O modelo base aprova quase tudo.** Sem RAG ele respondeu CONTRATADO em 16 dos 16 casos finais e em 12 dos 12 fora de escopo (12 + 12 falsas aprovações). Com RAG ainda foram 10 + 8. Num sistema de contas a pagar, é o pior erro possível.
2. **O ajuste tornou o modelo cauteloso, não mais certo.** Sem RAG, o ajustado respondeu REVISAR em 13 dos 16 casos finais, com 0 falsas aprovações e 5/16 de acerto. Fora de escopo, o mesmo hábito dá 11/12: o certo ali é sempre REVISAR, e é isso que ele responde quando não tem evidência. É acerto por cautela, não por entender que o documento está fora do escopo.
3. **Com RAG, o ajustado erra para o lado de DIVERGENTE.** Respondeu DIVERGENTE em 10 dos 16 casos finais e em 6 dos 12 fora de escopo; no link contratado IA-001 respondeu DIVERGENTE. Acerto 7/16 nos finais (base com RAG: 6/16) e 6/12 fora de escopo. No treino, a evidência era uma frase curta ("contrato vigente inclui exatamente X por R$ Y"); o RAG entrega o texto do contrato, que diz o que *não* está incluído ("não inclui IP adicional nem serviço de voz"). O modelo lê a negação como divergência. É troca de distribuição: o ajuste aprendeu o formato do treino, não a tarefa.
4. **Na distribuição do treino, o ajuste funciona.** Conjunto B: 13/20 → 18/20 com evidência, e as falsas aprovações caem de 7 para 0. Fora dela (A e C), o ganho some.
5. **O ajustado com RAG obedeceu a um prompt injection.** A falsa aprovação dele nos casos finais (IA-009) é um caso em que o texto da fatura traz instruções para aprovar. A regra deu REVISAR. Isso mostra, com medição, por que o modelo não tem autoridade.
6. **Custo e latência.** O RAG multiplica os tokens de entrada (de 148 para 463 em média nos casos finais) e por isso a latência e o custo (de 1,55 s para 3,63 s). O adaptador LoRA (rank 4) não muda o custo: base e ajustado gastam o mesmo tempo para o mesmo prompt.

## Conclusão

**O ajuste não compensou como tomador de decisão.** Fora do treino, o ajustado com RAG acertou 7/16 nos casos finais e 6/12 fora de escopo; a regra do sistema entregue acertou 16/16 e 12/12. Ele ganhou em segurança (falsas aprovações nos casos finais de 10 para 1), mas continua sensível ao formato da evidência. O desenho do sistema fica como está: a regra decide sobre a evidência estruturada, o modelo só sugere e sua concordância é medida. Para o ajuste valer a pena, o treino precisaria de exemplos com o texto real dos contratos recuperados pelo RAG, de documentos fora de escopo e de instruções embutidas, avaliados num conjunto separado como os dos casos finais e fora de escopo.

## Latência e custo do sistema no ar

Caminho: API → SQL Server (RLS) → RAG → Qwen 0,5B no Ollama (CPU, quantizado) → regra → auditoria. A regra decide; o modelo é chamado em toda análise para a sugestão medida.

| Medição | Chamadas | CPU da máquina | Média | Mediana | p95 | 1.000 usos: CPU · energia |
|---|---|---|---|---|---|---|
| Prompt 3.0 · **fatura nova**, máquina com outros programas | 16 | 45,2% → 43,6% | 31,31 s | 34,57 s | 36,13 s | 521,9 min · R$ 0,162 a 0,594 |
| Prompt 3.0 · as mesmas 16 faturas de novo (prompt no cache do Ollama) | 16 | 40,6% → 33,6% | 0,77 s | 0,76 s | 0,91 s | 12,9 min · R$ 0,004 a 0,015 |
| **Prompt 3.1 · fatura nova**, máquina com outros programas | 16 | 43,9% → 46,1% | 3,09 s | 2,86 s | 4,82 s | 51,4 min · R$ 0,016 a 0,059 |
| A mesma fatura repetida (o Ollama reaproveita o prompt) | 20 | — | 0,83 s | 0,81 s | 1,02 s | — |

**O número que vale para o uso real é o da fatura nova**: cada fatura que chega é diferente, e o prompt não está no cache. O Ollama guarda os últimos 16 prompts; repetir faturas já vistas (ou a mesma fatura) mede só o cache. A diferença mostra onde está o tempo: quase todo ele é o modelo processando o prompt da API numa CPU de notebook. No prompt 3.0, dois terços do prompt eram 20 linhas de contexto do banco (notas de carga que a regra não usa); os casos IA-005 e IA-016, sem contexto, respondiam em cerca de 5 s contra mais de 30 s nos outros.

**Prompt 3.1 (correção):** 3 linhas de contexto, só com descrição, valor, vencimento e situação; o modelo recebe os 3 primeiros documentos (a regra continua avaliando os 5); a parte estável (contexto do provedor) vai antes e a fatura por último, para o Ollama reaproveitar o prefixo. Resultado na mesma situação de carga: média 3,09 s e p95 4,82 s, contra 31,31 s e 36,13 s no 3.0; 51,4 min de CPU por 1.000 usos. Pior caso (modelo descarregado, depois de 30 min sem uso): 11,7 s na primeira análise, que inclui carregar o modelo, e 1,0 s na seguinte (`latencia-partida-fria.json`). As decisões não mudaram (`ia-avaliacao-prompt-v31.json`): 16/16 nos casos, os mesmos ataques detectados e o mesmo resultado na validação cega. **Sistema entregue (prompt 3.1 + busca por embedding):** na avaliação final, os 16 casos tiveram média 4,59 s e p95 6,63 s (faturas já vistas na rodada anterior); a busca por embedding custa 145 ms (mediana) por consulta ([`rag-embeddings.md`](../rag-embeddings.md)). A decisão (a regra) não depende do modelo e sai em milissegundos.

## Limites

- Conjuntos pequenos (16, 12 e 20 casos) e sintéticos; servem para comparar as configurações entre si, não para estimar acerto em produção.
- Energia só do processador, estimada pelo tempo medido e pela potência de catálogo; a máquina inteira gasta mais.
- O modelo do sistema no ar (Ollama, quantizado) não é o mesmo binário do usado na comparação (Transformers, float32); por isso a comparação e a latência do sistema estão em tabelas separadas.
