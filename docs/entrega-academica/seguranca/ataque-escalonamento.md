# Ataque de escalonamento de privilégio

Script: [`../sqlserver/08_ataque_escalonamento.sql`](../sqlserver/08_ataque_escalonamento.sql) · Evidência: [`../sqlserver/evidence/parte3/escalonamento.txt`](../sqlserver/evidence/parte3/escalonamento.txt) · Correção: [`../sqlserver/01_schema_seed.sql`](../sqlserver/01_schema_seed.sql) (função `security.fn_local_scope_escrita` e política `security.LocalScopePolicy`).

## Cenário

Cada principal do banco só deve ver e alterar as notas dos locais do seu escopo (`security.LocalScope`). O atacante é um **operador regional** (`sigp_operador_loc001`): tem o papel de gravação `sigp_api`, mas o escopo dele é só o **LOC-001**. A pergunta do teste é se ele consegue passar desse limite:

- **horizontal**: alcançar dados de outro local (LOC-002);
- **vertical**: ganhar poderes de outro papel (auditor) ou apagar o próprio rastro.

Cada ataque roda como o principal de teste (`EXECUTE AS USER`). Tudo acontece dentro de transação e termina em `ROLLBACK`, então o banco não muda.

## A falha encontrada

A Row-Level Security tinha só o predicado **FILTER**. O FILTER esconde as linhas na leitura, mas não confere o que é gravado. O operador do LOC-001 conseguia:

- **E6**: inserir uma nota com `local_id = 'LOC-002'`;
- **E7**: mudar o `local_id` de uma nota do LOC-001 para LOC-002.

No E7, a nota some para quem é dono dela e aparece em outro local, com valor e vencimento escolhidos pelo atacante. Os dois são escalonamento horizontal: o operador grava num escopo que não é o dele.

## A correção

Uma segunda função de escopo, `security.fn_local_scope_escrita`, e a política recriada com quatro predicados **BLOCK** além do FILTER:

| Predicado | O que barra |
|---|---|
| `AFTER INSERT` | inserir nota em local fora do escopo |
| `BEFORE UPDATE` | alterar nota de local fora do escopo |
| `AFTER UPDATE` | mover uma nota para local fora do escopo |
| `BEFORE DELETE` | apagar nota de local fora do escopo (a API já tem `DENY DELETE`; é a segunda camada) |

A função libera o `db_owner`. Ele já pode alterar a própria política, então barrá-lo não acrescenta proteção, e a carga de volume (`03_load_benchmark.sql`) grava como dono do banco. Os demais principais só gravam nos locais do seu escopo.

## Resultado

Uma única execução mostra as duas fases. A **fase 1** volta temporariamente a política para só FILTER e reproduz a falha. A **fase 2** roda os ataques contra a política corrigida.

| Fase | Id | Tipo | Quem | Ataque | Esperado | Obtido |
|---|---|---|---|---|---|---|
| antes | E6 | horizontal | sigp_operador_loc001 | Nota gravada no LOC-002 (INSERT) | passa | **PERMITIDO** (a falha) |
| antes | E7 | horizontal | sigp_operador_loc001 | Nota movida para o LOC-002 (UPDATE) | passa | **PERMITIDO** (a falha) |
| depois | E1 | horizontal | sigp_ia_loc001 | IA grava o próprio escopo | barrado | barrado (229) |
| depois | E2 | horizontal | sigp_ia_loc001 | IA personifica a identidade do LOC-002 | barrado | barrado (15517) |
| depois | E3 | vertical | sigp_operador_loc001 | Operador entra no papel `sigp_auditor` | barrado | barrado (15151) |
| depois | E4 | vertical | sigp_operador_loc001 | Operador apaga a auditoria | barrado | barrado (229) |
| depois | E5 | vertical | sigp_operador_loc001 | Operador reescreve a auditoria | barrado | barrado (229) |
| depois | E6 | horizontal | sigp_operador_loc001 | Nota gravada no LOC-002 (INSERT) | barrado | **barrado (33504)** |
| depois | E7 | horizontal | sigp_operador_loc001 | Nota movida para o LOC-002 (UPDATE) | barrado | **barrado (33504)** |
| depois | E8 | injeção | sigp_ia_loc001 | SQL Injection em `@local_id` | barrado | barrado (51001) |
| depois | C1 | controle | sigp_operador_loc001 | Gravar e atualizar nota no **próprio** local | permitido | permitido |

Resultado final: **APROVADO**. Os códigos de erro significam:

- 229: sem permissão no objeto;
- 15151: sem permissão para alterar o papel;
- 15517: personificação negada;
- 33504: violação do predicado BLOCK;
- 51001: o procedimento negou o escopo.

Só esses erros contam como "barrado". Qualquer outro erro reprova o teste, para que uma falha de execução não seja confundida com defesa.

O controle positivo (C1) mostra que a correção não quebrou o uso legítimo. Os testes anteriores também continuam passando depois da correção:

- `02_security_tests.sql`: PASS;
- `07_mascaramento_parte2.sql`: mascaramento e negações mantidos;
- a análise da IA de ponta a ponta continua respondendo, com 20 linhas de contexto do LOC-001.

## Por que os outros ataques já falhavam

- **E1 e E4/E5**: a IA e a API não têm `INSERT` em `security.LocalScope` nem `UPDATE`/`DELETE` em `audit.Eventos` (`DENY` explícito). A trilha de auditoria só aceita inserção.
- **E2**: nenhum principal tem `IMPERSONATE`.
- **E3**: ninguém além do dono tem `ALTER` nos papéis.
- **E8**: o procedimento da IA recebe o local como parâmetro tipado. Não há SQL dinâmico. O texto injetado vira um `local_id` inexistente e o escopo é negado.

## Riscos que restam

- O `sa` e o `db_owner` continuam acima da RLS. A defesa é operacional: a senha do `sa` só existe no `.env.academic` ignorado pelo Git, e a IA e a API usam principais próprios, sem `db_owner`.
- O nome de quem pediu (`@requested_by`) é texto informado pelo chamador e vai para o campo `ator` da auditoria. O principal real do banco também é gravado (`db_principal=...` no detalhe). Por isso um nome falso não apaga a identidade verdadeira. Mesmo assim, a apresentação deve citar o `db_principal` como prova.
- `TRUSTWORTHY` está desligado no banco (conferido), o que fecha o caminho clássico de `db_owner` para `sysadmin`.

## Como rodar

Na raiz do projeto, com a senha só em variável de ambiente:

```powershell
$env:SQLCMDPASSWORD = '<MSSQL_SA_PASSWORD do .env.academic>'
sqlcmd -S 127.0.0.1,14333 -U sa -d SIGpAcademic -C -I -W -s "|" -f 65001 -i docs/entrega-academica/sqlserver/08_ataque_escalonamento.sql
Remove-Item Env:SQLCMDPASSWORD
```

Antes, o `01_schema_seed.sql` atualizado precisa ter rodado (o `setup-academic.ps1` faz isso). O script para com mensagem clara se faltar o operador de teste ou os predicados BLOCK.
