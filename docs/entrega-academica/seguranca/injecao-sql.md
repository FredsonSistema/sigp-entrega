# Injeção de SQL: ataques em três níveis

Gerado por `seguranca/testar_injecao_sql.py` a partir de `sqlserver/evidence/parte3/injecao-sql-antes.json` e `injecao-sql-depois.json`. Cada ataque roda contra o sistema no ar, e o banco é conferido antes e depois (linhas de notas, pagamentos, locais e provedores, objetos, permissões da IA e membros do sysadmin).

| | Antes (2026-11-25T18:00:10+00:00) | Depois (2026-11-25T18:02:54+00:00) |
|---|---|---|
| Resultado | REPROVADO | APROVADO |
| Ataques pela API sem efeito | 10/10 | 10/10 |
| Ataques nos procedimentos sem efeito | 6/6 | 6/6 |
| Banco igual depois dos ataques | sim | sim |
| Senha na trilha de auditoria | não | não |
| Procedimentos com SQL dinâmico | 0 | 0 |
| Primitiva da API troca `$(VARIÁVEL)` | sim: o sqlcmd trocou $(SIGP_AI_API_KEY), $(HOME) pelo valor da variável de ambiente | não: $(SIGP_AI_API_KEY) e $(HOME) ficaram como texto |

## 1. Pela API da IA (como um usuário mal-intencionado)

| Ataque | HTTP | Resposta |
|---|---|---|
| aspas e comando empilhado | 200 | REVISAR |
| escalar privilégio | 200 | REVISAR |
| OR 1=1 com comentário | 200 | REVISAR |
| aspa Unicode (U+02BC) para contrabando | 200 | REVISAR |
| variável do sqlcmd com a senha | 200 | DIVERGENTE |
| comando do sistema pelo sqlcmd (:!!) | 200 | DIVERGENTE |
| UNION para ler outro local | 200 | REVISAR |
| valor com SQL | 400 | amount deve ser numérico (ex.: 450.00 ou 450,00). |
| texto gigante (100 mil caracteres) | 413 | <!doctype html> |
| local de outro escopo no corpo | 400 | O escopo local vem da credencial do serviço e não pode vir no corpo. |

Por que nada passa: o texto da fatura nunca entra no SQL. A descrição vira um hash (SHA-256), o provedor é trocado pelo código de uma lista fixa (ou PROV-UNKNOWN), o valor só aceita número, a classificação do modelo só aceita três valores e o motivo é um texto fixo das regras. O local vem da credencial do serviço, nunca do corpo (400).

## 2. Direto nos procedimentos, com o usuário da IA

| Ataque | Resultado |
|---|---|
| aspas no provedor | sem efeito (nenhuma linha de outro local, nada executado) |
| local de outro escopo | Msg 51001, Level 16, State 1, Server ce6f854ecbd5, Procedure ai.usp_get_context, Line 45 |
| take gigante | Msg 51003, Level 16, State 1, Server ce6f854ecbd5, Procedure ai.usp_get_context, Line 31 |
| ler a tabela direto | Msg 229, Level 14, State 5, Server ce6f854ecbd5, Line 1 |
| apagar a trilha | Msg 37359, Level 16, State 3, Server ce6f854ecbd5, Line 1 |
| SQL dinâmico para ler a tabela | Msg 229, Level 14, State 5, Server ce6f854ecbd5, Line 1 |

Os erros 51001 e 51003 são do próprio procedimento (escopo e limite conferidos); 229 é permissão negada (a IA não lê tabela, nem por SQL dinâmico); 37359 é a trilha ledger recusando apagar. Nenhum procedimento dos schemas `ai` e `app` monta SQL dinâmico.

## 3. A primitiva que fala com o banco (achado e correção)

A API chama o `sqlcmd` com o texto da consulta. O `sqlcmd` troca `$(VARIÁVEL)` pelo valor da variável de ambiente: na primeira rodada, `$(SIGP_AI_API_KEY)` virou um texto de 64 caracteres (a chave da API da IA) e `$(HOME)` a pasta do usuário. Hoje nenhum texto do usuário chega à consulta, mas bastaria um campo novo com texto livre para a chave ir parar na trilha ou numa mensagem de erro. Correção: `-x` no `sqlcmd` de `ia/app.py` (desliga a troca). Depois: as duas variáveis ficam como texto. Só o tamanho é medido; o valor nunca é lido.
