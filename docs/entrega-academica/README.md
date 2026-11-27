# SIGp — Auditoria de faturas de provedores

**Grupo e integrantes:** ver [`identificacao.json`](identificacao.json) (a mesma identificação de todos os PDFs).  
**Disciplinas:** Projeto de Inteligência Artificial; Segurança e Otimização de Banco de Dados.  
**Repositório da entrega:** <https://github.com/FredsonSistema/sigp-entrega> (só o fluxo avaliado, a parte acadêmica e uma base fictícia).  
**Comece por aqui:** [`guia-de-correcao.pdf`](guia-de-correcao.pdf) (1 página: cada comentário da professora, o resultado e onde conferir). Versões HTML simples, para enviar em separado: [`relatorio-final.html`](relatorio-final.html) e [`apresentacao-sistema.html`](apresentacao-sistema.html).

## Entrega final (01/12/2026)
- **Instalação e configuração:** [`GUIA-INSTALACAO.md`](GUIA-INSTALACAO.md) (máquina sem nada instalado até o sistema funcionando),
  [`GUIA-CONFIGURACAO.md`](GUIA-CONFIGURACAO.md) (endereços, chaves, Gmail, alertas e o assistente da IA) e [`ENDPOINTS.md`](ENDPOINTS.md) (o que testar e o resultado esperado).
- **Mudanças desde a Entrega 2:** [`MUDANCAS-DESDE-ENTREGA-2.md`](MUDANCAS-DESDE-ENTREGA-2.md) (o que melhorou, o que foi corrigido, o que permaneceu inalterado e a mudança da web para uma janela do Windows).
- **Resultados:** página interativa com os mesmos dados dos relatórios em [`apresentacao.html`](apresentacao.html) (abre sem internet); demonstração guiada, passo a passo, em [`demo-final.ps1`](demo-final.ps1) (`pwsh -File docs/entrega-academica/demo-final.ps1`; com `-SemPausa` grava `sqlserver/evidence/parte3/demo-final-saida.txt`).
- **Relatórios:** [`relatorio-final.pdf`](relatorio-final.pdf) e [`relatorio-limitacoes.pdf`](relatorio-limitacoes.pdf). Histórico de cada falha, correção e reteste: [`historico-evolucao.md`](historico-evolucao.md).
- **IA:** [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) (casos finais e fora de escopo no sistema entregue, injeção, validação cega congelada e intervalos de 95%), [`ia/rag-embeddings.md`](ia/rag-embeddings.md) (RAG: busca por palavras × embeddings, critério em [`ia/rag-embeddings-criterio.md`](ia/rag-embeddings-criterio.md)), [`ia/escolha-modelo-triagem.md`](ia/escolha-modelo-triagem.md) (critério, medição e escolha do modelo), [`ia/finetuning/comparacao-final.md`](ia/finetuning/comparacao-final.md) (4 configurações fora e dentro do treino, custo e latência), [`ia/segredos-n8n.md`](ia/segredos-n8n.md) e [`ia/prompts/CHANGELOG.md`](ia/prompts/CHANGELOG.md).
- **Segurança e otimização:** [`seguranca/matriz-permissoes.md`](seguranca/matriz-permissoes.md), [`seguranca/protecao-dados-sensiveis.md`](seguranca/protecao-dados-sensiveis.md), [`seguranca/otimizacao-consultas.md`](seguranca/otimizacao-consultas.md), [`seguranca/ataque-escalonamento.md`](seguranca/ataque-escalonamento.md), [`seguranca/trilha-auditoria.md`](seguranca/trilha-auditoria.md) e [`seguranca/auditoria-e-ia-por-perfil.md`](seguranca/auditoria-e-ia-por-perfil.md) e [`seguranca/avaliacao-vulnerabilidades.md`](seguranca/avaliacao-vulnerabilidades.md) (27 regras no estilo do SQL Vulnerability Assessment e do CIS, antes e depois), [`seguranca/restauracao-tde.md`](seguranca/restauracao-tde.md) (backup em outro servidor, sem e com o certificado) e [`seguranca/injecao-sql.md`](seguranca/injecao-sql.md) (ataques pela API, nos procedimentos e na primitiva do banco). Banco, papéis e RLS: [`sqlserver/README.md`](sqlserver/README.md).
- **Evidências:** [`sqlserver/evidence/parte3/`](sqlserver/evidence/parte3/). Nenhum número dos documentos foi digitado à mão: os geradores leem esses arquivos. Em [`sqlserver/evidence/parte2/`](sqlserver/evidence/parte2/) ficaram só os cinco arquivos da Entrega 2 que os documentos finais usam como comparação (casos da API, tempos do benchmark, demonstração de perfis, memória de exemplos e teste inverso).

<!-- respostas-professora:inicio -->
## Respostas aos comentários da professora

Devolutiva da Entrega 2 (Prof.ª Bruna). Seção gerada por `docs/entrega-academica/apresentacao/gerar_respostas.py` com os mesmos dados dos relatórios; os números vêm das evidências.

| Disciplina | Comentário | O que foi feito | Evidência |
|---|---|---|---|
| IA | O relatório cita a v4.2 como prompt atual, enquanto o fluxo avaliado ainda roda a v3.0. | Cada fluxo tem o seu prompt: a análise de fatura avaliada (/api/analyze) usa o v3.1 e a triagem do Gmail (WF-08/WF-10), o v4.2. A avaliação final foi feita no serviço com o mesmo prompt, modelo e busca que o pacote de entrega sobe, e um teste falha se o pacote divergir da evidência. | [`ia/prompts/CHANGELOG.md`](ia/prompts/CHANGELOG.md) (Qual prompt cada fluxo usa hoje) · [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) · [`tests/test_pacote_mesma_ia.py`](../../tests/test_pacote_mesma_ia.py) |
| IA | RAG com embeddings. | Busca por embedding (embeddinggemma, no Ollama local) escolhida por critério versionado antes da medição, entre 3 modelos e a busca híbrida: fonte certa em 13/14 paráfrases contra 7/14 da lexical, sem perder nenhum caso final (14/14) e sem documento de outro local. Ligada no sistema entregue. | [`sqlserver/evidence/parte3/rag-embeddings.json`](sqlserver/evidence/parte3/rag-embeddings.json) · [`ia/rag-embeddings-criterio.md`](ia/rag-embeddings-criterio.md) · [`ia/rag-embeddings.md`](ia/rag-embeddings.md) |
| IA | Mais casos de teste, incluindo fora de escopo. | 12 casos fora de escopo (outra conta, outro local, outro idioma, não é fatura), com o esperado escrito antes de rodar. A 1ª rodada achou uma falsa aprovação (fatura de outra unidade aprovada com o contrato da Agência Centro), corrigida; final 12/12, segurança 12/12. | [`ia/casos-fora-escopo.json`](ia/casos-fora-escopo.json) · [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) · [`ia-avaliacao-final.json`](sqlserver/evidence/parte3/ia-avaliacao-final.json) |
| IA | Fine-tuning medido em cenários fora do treino. | Medido nos casos finais (7/16) e nos fora de escopo (6/12), com o RAG do sistema entregue; no teste do próprio treino, 18/20. A sobreposição com os 80 exemplos de treino foi conferida caso a caso: nenhum provedor em comum; os 6 casos que usam o nome de serviço do treino saem separados. Conclusão: o ajuste não generaliza fora do treino. | [`ia/finetuning/comparacao-final.md`](ia/finetuning/comparacao-final.md) · [`finetuning-comparacao.json`](sqlserver/evidence/parte3/finetuning-comparacao.json) · [`sobreposicao-treino.json`](sqlserver/evidence/parte3/sobreposicao-treino.json) |
| BD | Explicar nos planos o que mudou (scan × seek, custo). | Cada operador dos planos reais lido do XML: tipo de acesso (scan ou seek), linhas lidas e devolvidas, custo próprio e da consulta, por configuração, com o porquê da mudança. | [`seguranca/otimizacao-consultas.md`](seguranca/otimizacao-consultas.md) (seção "O que mudou no plano") · [`evidence/parte3/otimizacao/*.sqlplan`](sqlserver/evidence/parte3/otimizacao/) |
| BD | Melhorar a consulta 1 (ganho ainda pequeno). | Só com índice o ganho era 1,4× (o plano mostra que sobra somar as notas da janela). Com o resumo diário (desnormalização com gatilho e RLS): 168,7 → 25,3 ms (6,7×) e 3.281 → 13 leituras lógicas, com a mesma resposta. | [`seguranca/otimizacao-consultas.md`](seguranca/otimizacao-consultas.md) · [`evidence/parte3/otimizacao/`](sqlserver/evidence/parte3/otimizacao/) |
| BD | Proteger a tabela de auditoria contra alteração. | audit.Eventos virou tabela ledger só de inserção: antes o sa reescrevia 280 e apagava 61 eventos; agora ninguém altera nem apaga (erro 37359), e a trilha é conferida contra o digest guardado fora do banco (APROVADO). | [`sqlserver/evidence/parte3/ledger-antes.txt`](sqlserver/evidence/parte3/ledger-antes.txt) e ledger-verificacao.json |
| IA e BD | Repositório só com a parte acadêmica, com commits de todos os integrantes. | A entrega é o repositório do pacote: só o fluxo avaliado (gestão de contas de provedores), a parte acadêmica e uma base fictícia, com instalação em um comando. É o único repositório citado nos documentos. | <https://github.com/FredsonSistema/sigp-entrega> |

## Onde está cada requisito

Conferido pelo gerador: cada documento abaixo existe no repositório da entrega; o resultado vem das evidências.

| Disciplina | Requisito | Documento | Resultado |
|---|---|---|---|
| IA | Casos de teste com métrica e análise das falhas | [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) | 16/16 e 12/12 fora de escopo; acurácia, F1, matriz e intervalo de 95% |
| IA | RAG (com embeddings) | [`ia/rag-embeddings.md`](ia/rag-embeddings.md) | embedding:embeddinggemma: 13/14 paráfrases |
| IA | Fine-tuning: base, base + RAG, ajustado, ajustado + RAG; custo e latência; fora do treino | [`ia/finetuning/comparacao-final.md`](ia/finetuning/comparacao-final.md) | 4 configurações em 3 conjuntos (finais, fora de escopo, teste do treino) |
| IA | Prompt injection testado e as defesas | [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) | bateria 13/13; 2ª validação cega 11/12; 8 camadas |
| IA | Versionamento do prompt (qual fluxo usa qual) | [`ia/prompts/CHANGELOG.md`](ia/prompts/CHANGELOG.md) | análise de fatura v3.1; triagem v4.2 |
| IA | Fluxo do n8n sem segredo | [`ia/segredos-n8n.md`](ia/segredos-n8n.md) | APROVADO |
| BD | Papéis e permissões com DENY justificado | [`seguranca/matriz-permissoes.md`](seguranca/matriz-permissoes.md) | 23 DENY, cada um com motivo e teste |
| BD | Dados sensíveis (RLS, mascaramento e TDE) | [`seguranca/protecao-dados-sensiveis.md`](seguranca/protecao-dados-sensiveis.md) | TDE: APROVADO |
| BD | Duas consultas lentas: plano (scan × seek, custo) e tempos | [`seguranca/otimizacao-consultas.md`](seguranca/otimizacao-consultas.md) | 6,7× e 5,1× |
| BD | Ataque e correção (escalonamento) | [`seguranca/ataque-escalonamento.md`](seguranca/ataque-escalonamento.md) | falha reproduzida e barrada |
| BD | Trilha 'quem fez o quê', protegida contra alteração | [`seguranca/trilha-auditoria.md`](seguranca/trilha-auditoria.md) | ledger: APROVADO |
| BD | Auditoria do que a IA respondeu e a IA por perfil | [`seguranca/auditoria-e-ia-por-perfil.md`](seguranca/auditoria-e-ia-por-perfil.md) | APROVADO |
| BD | Vulnerabilidades, restauração do backup e injeção de SQL | [`seguranca/avaliacao-vulnerabilidades.md`](seguranca/avaliacao-vulnerabilidades.md) | 25 regras passando, 0 falhas |
| IA e BD | Histórico de falhas, correções e retestes | [`historico-evolucao.md`](historico-evolucao.md) | 50 itens |
| IA e BD | Mudanças desde a Entrega 2 | [`MUDANCAS-DESDE-ENTREGA-2.md`](MUDANCAS-DESDE-ENTREGA-2.md) | melhorado, corrigido e inalterado |
| IA e BD | Respostas aos comentários da professora | [`README.md`](README.md) | 8 comentários |
| IA e BD | Relatório de limitações (até 2 páginas) | [`relatorio-limitacoes.pdf`](relatorio-limitacoes.pdf) | gerado das evidências |
| IA e BD | Guia de correção (1 página) | [`guia-de-correcao.pdf`](guia-de-correcao.pdf) | comentários, resultados e como conferir |
| IA e BD | Apresentação do sistema (HTML), com as mudanças desde a Entrega 2 | [`apresentacao-sistema.html`](apresentacao-sistema.html) | um arquivo, sem internet |
| IA e BD | Relatório final e contribuição individual | [`relatorio-final.pdf`](relatorio-final.pdf) | 4 integrantes |
| IA e BD | Instalação reproduzível com base fictícia | [`GUIA-INSTALACAO.md`](GUIA-INSTALACAO.md) | um comando; janela própria no Windows |

<!-- respostas-professora:fim -->

## Problema e objetivo

Quem acompanha as contas de internet de agências, rodoviárias e garagens precisa identificar faturas vencidas, diferenças de valor e serviços cobrados que não constam no contrato. Os dados chegam em arquivos separados e em momentos diferentes. O SIGp organiza esses documentos e destaca casos para conferência humana, sem autorizar pagamentos.

## Usuário, entradas e saídas

- **Usuário:** responsável por conferir contas e auditor.
- **Entradas:** faturas PDF e notas/pagamentos em XML ou JSON, importados manualmente ou pelo fluxo n8n (e-mail).
- **Saídas:** conciliação, divergências justificadas, itens pendentes de revisão e trilha de auditoria.

## Maior risco

Sugestão errada ou instrução maliciosa em um documento influenciar a análise. Mitigação: contexto delimitado, citações, testes de prompt injection, permissões sem escrita para a IA e aprovação humana. Os testes e resultados estão em [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) e [`seguranca/ataque-escalonamento.md`](seguranca/ataque-escalonamento.md).

## Entregas anteriores

Os documentos e PDFs das Entregas 1 (02/11/2026) e 2 (16/11/2026) saíram do repositório na limpeza da entrega final e continuam no histórico do Git (último commit com eles: `52e65ae`). O que mudou desde então, com cada falha, correção e reteste, está em [`historico-evolucao.md`](historico-evolucao.md).
