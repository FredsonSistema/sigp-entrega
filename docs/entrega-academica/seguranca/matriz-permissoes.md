# Matriz final de papéis e permissões

Gerada por [`gerar_matriz.py`](gerar_matriz.py) a partir do banco: cada célula é a permissão **efetiva** medida como o usuário de teste (`HAS_PERMS_BY_NAME` com `EXECUTE AS USER`, que considera GRANT, DENY, papéis e herança do schema), não uma cópia do script. Script: [`../sqlserver/15_matriz_permissoes.sql`](../sqlserver/15_matriz_permissoes.sql). Evidência: [`matriz-permissoes.json`](../sqlserver/evidence/parte3/matriz-permissoes.json).

## Perfis

| Usuário de teste | Perfil | Papéis | Escopo (RLS) |
|---|---|---|---|
| `sigp_api_test` | API do sistema (papel sigp_api) | sigp_api | LOC-001,LOC-002,LOC-003 |
| `sigp_operador_loc001` | Operador regional do LOC-001 (papel sigp_api) | sigp_api | LOC-001 |
| `sigp_auditor_test` | Auditor (papel sigp_auditor) | sigp_auditor | LOC-001,LOC-002,LOC-003 |
| `sigp_fiscal_test` | Fiscal (papel sigp_fiscal) | sigp_fiscal | LOC-001 |
| `sigp_ia_loc001` | IA do LOC-001 (papel sigp_ia) | sigp_ia | LOC-001 |
| `sigp_denied_test` | Sem papel | — | nenhum |

## Tabelas e view

L = ler, I = inserir, A = alterar, E = apagar; — = nada. A RLS filtra ainda as linhas de `app.Notas` e `app.ResumoDiario` pelo escopo, e os predicados BLOCK impedem gravar fora dele.

| Objeto | `sigp_api_test` | `sigp_operador_loc001` | `sigp_auditor_test` | `sigp_fiscal_test` | `sigp_ia_loc001` | `sigp_denied_test` |
|---|---|---|---|---|---|---|
| `app.Notas` | LIA | LIA | — | L | — | — |
| `app.ItensNota` | LIA | LIA | — | — | — | — |
| `app.Pagamentos` | LIA | LIA | — | L | — | — |
| `app.Conciliacoes` | LIA | LIA | — | — | — | — |
| `app.Locais` | LIA | LIA | — | — | — | — |
| `app.Provedores` | LIA | LIA | — | — | — | — |
| `app.ResumoDiario` | L | L | — | — | — | — |
| `security.LocalScope` | — | — | — | — | — | — |
| `audit.Eventos` | — | — | L | — | — | — |
| `ai.vw_contexto_minimo` | — | — | L | — | — | — |

## Procedimentos, dado sensível e privilégios

| Permissão | `sigp_api_test` | `sigp_operador_loc001` | `sigp_auditor_test` | `sigp_fiscal_test` | `sigp_ia_loc001` | `sigp_denied_test` |
|---|---|---|---|---|---|---|
| EXECUTE `ai.usp_get_context` | — | — | — | — | sim | — |
| EXECUTE `ai.usp_log_sources` | — | — | — | — | sim | — |
| EXECUTE `ai.usp_log_response` | — | — | — | — | sim | — |
| UNMASK `app.Notas.chave_fiscal` | — | — | — | sim | — | — |
| UNMASK `app.Pagamentos.referencia` | — | — | — | sim | — | — |
| ALTER no papel `sigp_auditor` (entrar nele) | — | — | — | — | — | — |
| IMPERSONATE `sigp_ia_loc002` (se passar por ele) | — | — | — | — | — | — |

Leitura rápida: a API e o operador leem e gravam o negócio, mas nunca apagam, e a chave fiscal chega a eles mascarada. O auditor só lê a trilha e a view sem chave fiscal. O fiscal é o único que vê a chave fiscal. A IA não lê nenhuma tabela: só executa os três procedimentos, que conferem o local. Ninguém consegue entrar noutro papel nem se passar por outro usuário.

## Os DENY e por que existem

| Papel | DENY | Em | Por quê | Teste que prova |
|---|---|---|---|---|
| `sigp_api` | DELETE | `app.ResumoDiario` | Mesmo motivo. | 12_resumo_testes.sql |
| `sigp_api` | INSERT | `app.ResumoDiario` | O resumo da consulta 1 só muda pelo gatilho; gravar direto forjaria totais. | 12_resumo_testes.sql |
| `sigp_api` | UPDATE | `app.ResumoDiario` | Mesmo motivo: forjar o total faturado. | 12_resumo_testes.sql (forjar total) |
| `sigp_api` | DELETE | `audit.Eventos` | Ninguém apaga a trilha. | 08 (E4); 14 (T2b) |
| `sigp_api` | INSERT | `audit.Eventos` | A trilha só recebe eventos dos procedimentos da IA e do gatilho de auditoria. Com INSERT direto, o operador forjava eventos em nome de outro (achado H-21). | 14_auditoria_testes.sql (T2a) |
| `sigp_api` | SELECT | `audit.Eventos` | Quem é auditado não lê a própria trilha: saberia o que ficou registrado e o que não ficou. | 14_auditoria_testes.sql (T2d) |
| `sigp_api` | UPDATE | `audit.Eventos` | Ninguém reescreve a trilha. | 08_ataque_escalonamento.sql (E5) |
| `sigp_api` | DELETE | `SCHEMA::app` | Nota fiscal, pagamento e conciliação são registro contábil: erro se corrige com novo status ou estorno, nunca apagando. Só o dono do banco apaga, numa manutenção registrada pela auditoria nativa. DENY e não só ausência de GRANT: o DENY vence qualquer GRANT que a API ganhe depois por outro papel (prova abaixo, com db_datawriter). | 02_security_tests.sql (delete_api_negado); prova do DENY abaixo |
| `sigp_ia` | DELETE | `ai.vw_contexto_minimo` | Idem. | 02_security_tests.sql |
| `sigp_ia` | INSERT | `ai.vw_contexto_minimo` | A view é só leitura para a IA. | 02_security_tests.sql |
| `sigp_ia` | SELECT | `ai.vw_contexto_minimo` | A view não filtra por escopo sozinha; quem confere o local é o procedimento ai.usp_get_context. | 02_security_tests.sql |
| `sigp_ia` | UPDATE | `ai.vw_contexto_minimo` | Idem. | 02_security_tests.sql |
| `sigp_ia` | DELETE | `SCHEMA::ai` | Idem. | 02_security_tests.sql |
| `sigp_ia` | INSERT | `SCHEMA::ai` | A IA não cria nem altera objetos e dados do schema ai. | 02_security_tests.sql |
| `sigp_ia` | UPDATE | `SCHEMA::ai` | Idem. | 02_security_tests.sql |
| `sigp_ia` | DELETE | `SCHEMA::app` | Idem. | 02_security_tests.sql |
| `sigp_ia` | INSERT | `SCHEMA::app` | A IA não grava dado de negócio: só sugere. | 02_security_tests.sql |
| `sigp_ia` | SELECT | `SCHEMA::app` | A IA só recebe o contexto mínimo pelo procedimento que confere o local. Sem leitura direta, nem um prompt injection nem uma credencial vazada da IA leem as tabelas. | 02 (leitura_direta_negada); testar_ia_perfis.py |
| `sigp_ia` | UPDATE | `SCHEMA::app` | Idem: a IA não altera nota nem pagamento. | 02_security_tests.sql |
| `sigp_ia` | DELETE | `SCHEMA::audit` | A IA não apaga a trilha. | testar_ia_perfis.py |
| `sigp_ia` | INSERT | `SCHEMA::audit` | A IA não escreve na trilha direto; só pelos procedimentos, que validam o conteúdo e o escopo. | testar_ia_perfis.py (D1) |
| `sigp_ia` | SELECT | `SCHEMA::audit` | A IA não lê a trilha que a registra. | testar_ia_perfis.py (parte D) |
| `sigp_ia` | UPDATE | `SCHEMA::audit` | A IA não reescreve a trilha. | testar_ia_perfis.py |

## Prova do DENY: o DENY vence um GRANT dado depois

O DENY de exclusão da API no schema `app` é o DENY principal. Sem ele, bastaria alguém colocar a API num papel amplo para ela passar a apagar notas fiscais. O teste faz exatamente isso, dentro de uma transação desfeita:

| Teste | Esperado | Obtido | Veredito |
|---|---|---|---|
| API no papel db_datawriter (DELETE em tudo) | membro | membro | OK |
| Com db_datawriter, apagar uma nota (schema app, DENY DELETE) | negado (229) | negado (229) | OK |
| Controle: com db_datawriter, apagar em security.LocalScope (sem DENY) | permitido | permitido | OK |
| Depois do ROLLBACK, o escopo de RLS continua com todas as linhas | 13 linhas | 13 linhas | OK |
| Depois do ROLLBACK, a API voltou a não ter db_datawriter | não | não | OK |

Resultado: **APROVADO**. O controle mostra que o papel db_datawriter de fato dá DELETE; só o DENY segura as tabelas do schema `app`.

## Os testes que provam a matriz em uso

| Teste | O que prova |
|---|---|
| [`02_security_tests.sql`](../sqlserver/02_security_tests.sql) | IA lê só pelo procedimento e só o próprio local; DELETE da API negado; sem papel não executa nada; auditor lê a trilha |
| [`07_mascaramento_parte2.sql`](../sqlserver/07_mascaramento_parte2.sql) | API vê a chave mascarada; fiscal vê a chave real; auditor não lê as notas; a view da IA não tem a chave |
| [`08_ataque_escalonamento.sql`](../sqlserver/08_ataque_escalonamento.sql) | Escalonamento vertical e horizontal barrados (ver [`ataque-escalonamento.md`](ataque-escalonamento.md)) |
| [`12_resumo_testes.sql`](../sqlserver/12_resumo_testes.sql) | Resumo da consulta 1 com a mesma RLS; ninguém forja o total |
| [`14_auditoria_testes.sql`](../sqlserver/14_auditoria_testes.sql) | Trilha de quem fez o quê, sem como forjar, apagar, ler (operador) ou desligar |
| [`testar_ia_perfis.py`](../sqlserver/testar_ia_perfis.py) | A IA não vaza o que o banco protege, perfil por perfil |
