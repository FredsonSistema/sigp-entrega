# Trilha de auditoria: quem fez o quê

Teste: [`../sqlserver/14_auditoria_testes.sql`](../sqlserver/14_auditoria_testes.sql) · Evidência antes e depois: [`../sqlserver/evidence/parte3/auditoria/`](../sqlserver/evidence/parte3/auditoria/) · Código: [`../sqlserver/01_schema_seed.sql`](../sqlserver/01_schema_seed.sql) (gatilho `app.trg_Notas_Auditoria`) e [`../sqlserver/13_sql_server_audit.sql`](../sqlserver/13_sql_server_audit.sql) (auditoria nativa).

## Três camadas

| Camada | O que registra | Onde | Quem lê |
|---|---|---|---|
| **IA** (procedimentos `ai.usp_*`) | Quem pediu, qual contexto foi lido, quais fontes, o que a IA respondeu (decisão, sugestão do modelo e hash da resposta) e os acessos negados | `audit.Eventos` | papel `sigp_auditor` |
| **Gravações** (gatilho `app.trg_Notas_Auditoria`) | Toda inserção, alteração e exclusão em `app.Notas`: usuário real, o que mudou (antes → depois), quando. Mais de 100 linhas viram um evento só (`_LOTE`) | `audit.Eventos` | papel `sigp_auditor` |
| **Tentativas** (SQL Server Audit) | Gravações nos schemas `app`, `audit` e `security` com `sucesso` 0 ou 1, mudança de papel e de permissão, personificação; com o principal real e o comando | arquivo `.sqlaudit` no volume do banco | só o administrador do servidor |

O gatilho só registra o que **foi** gravado: quando uma instrução é negada, ela é desfeita junto com o evento. Por isso a
auditoria nativa é a terceira camada, para as tentativas.

Exemplo real (evidência `trilha-depois.txt`):

```text
sigp_operador_loc001 | NOTA_INSERIDA      | nota_id=…; local_id=LOC-001; provedor_id=PROV-001; valor=11.00; emissao=2026-11-01; … db_principal=sigp_operador_loc001
sigp_operador_loc001 | NOTA_ALTERADA      | nota_id=…; mudou: valor 11.00→12.50; status PENDENTE→RECEBIDA; db_principal=sigp_operador_loc001
sigp_operador_loc001 | NOTA_ALTERADA      | nota_id=…; mudou: chave_fiscal (valor omitido); …
dbo                  | NOTA_EXCLUIDA      | nota_id=…; local_id=LOC-001; valor=22.00; …; db_principal=dbo
dbo                  | NOTA_INSERIDA_LOTE | linhas=150; ids=…; locais=LOC-002; …
SQL Server Audit     | IN   sucesso=0     | sigp_operador_loc001 tentou INSERT INTO audit.Eventos (evento forjado)
SQL Server Audit     | APRL sucesso=0     | sigp_operador_loc001 tentou ALTER ROLE sigp_auditor ADD MEMBER sigp_operador_loc001
```

## Decisões

- **Usuário real.** O gatilho não usa `EXECUTE AS`: `USER_NAME()` é quem gravou. O gatilho e a trilha têm o mesmo dono, então a gravação na trilha passa pelo encadeamento de propriedade, mesmo com o papel da API sem permissão de escrever nela.
- **Dado sensível fora da trilha.** A chave fiscal nunca entra no texto, só o aviso de que mudou.
- **A trilha não se forja.** O papel da API tinha INSERT direto em `audit.Eventos`, sem uso nenhum, e com ele um operador inseria um evento falso em nome do auditor. A permissão foi retirada (`DENY INSERT`). A trilha agora só recebe eventos dos procedimentos e do gatilho.
- **Lote.** Uma carga de 100 mil notas vira um evento com a quantidade, a faixa de ids e os locais, em vez de 100 mil linhas na trilha.

## Resultado: antes e depois

| Id | Teste | Antes | Depois |
|---|---|---|---|
| T1a | Inserção do operador registrada com o usuário real | 0 eventos | 2 eventos (sigp_operador_loc001) |
| T1b | Alteração registra o antes e o depois | não registrado | valor 11.00→12.50; status PENDENTE→RECEBIDA |
| T1c | Troca de chave fiscal registrada sem o valor da chave | não registrado | registrada, valor omitido |
| T1d | Exclusão registrada com quem apagou | 0 eventos | 1 evento (dbo) |
| T1e | Lote de 150 notas vira um evento só | 0 eventos | 1 evento, linhas=150 |
| T2a | Operador forja um evento na trilha | **PERMITIDO** | negado (229) |
| T2b | Operador apaga a trilha | negado (229) | negado (37359: a trilha agora é ledger, ver abaixo) |
| T2c | Operador desliga o gatilho de auditoria | gatilho não existia | negado (1088) |
| T2d | Operador lê a trilha | negado (229) | negado (229) |
| T2e | Auditor lê a trilha | permitido | permitido |
| T3a | Tentativa de gravar no LOC-002 (barrada pela RLS) fica registrada | não registrada | registrada (operador, app.Notas) |
| T3b | Tentativa de entrar no papel de auditor fica registrada | não registrada | registrada, sucesso=0 |
| | **Resultado** | **REPROVADO** (9 falhas) | **APROVADO** |

Depois da mudança, também passam:
- `08_ataque_escalonamento.sql`: APROVADO;
- `02_security_tests.sql`: PASS;
- `07_mascaramento_parte2.sql`;
- `12_resumo_testes.sql`: APROVADO;
- o teste por perfil da IA (`testar_ia_perfis.py`): APROVADO;
- os 21 testes unitários da IA.

## Achado no caminho: acentos gravados errado desde a instalação

O T1b falhou na primeira execução depois da correção com o texto aparentemente certo. A seta gravada pelo gatilho era "â†’".

A causa: os scripts `.sql` não tinham a marca UTF-8 (BOM), e o `setup-academic.ps1` chamava o `sqlcmd` sem `-f 65001`. Com isso, o `sqlcmd` lia os arquivos na página de código do Windows. Desde a instalação, ficaram com os acentos errados:
- os nomes dos locais e provedores ("FictÃ­cia");
- as 100.020 descrições de itens;
- as 100.020 justificativas de conciliação;
- as mensagens de erro dos procedimentos da IA ("nÃ£o autorizado").

As decisões da IA não mudavam, porque usam os arquivos JSON, mas o modelo recebia nomes quebrados no contexto.

A correção:
- todos os scripts `.sql` ganharam a marca UTF-8;
- o setup passou a usar `-f 65001`;
- o `01_schema_seed.sql` ganhou um reparo que só age nas linhas com o sinal da leitura errada (`dbo.fn_reparar_utf8_lido_como_1252`).

A conferência em comparação binária deu 0 linhas quebradas e mensagens certas. Ver [`../historico-evolucao.md`](../historico-evolucao.md), H-22.

## Quarta camada: trilha à prova de adulteração (ledger)

Revisão externa: "Hoje DELETE e UPDATE são negados, mas quem tem db_owner ainda altera." Era verdade, e foi medido numa cópia do banco restaurada do backup de antes da mudança ([`16_ledger_antes.sql`](../sqlserver/16_ledger_antes.sql), evidência [`ledger-antes.txt`](../sqlserver/evidence/parte3/ledger-antes.txt)): o `sa` reescreveu 280 eventos e apagou 61 sem erro, e a trilha da aplicação não guardou nada da alteração.

A correção: `audit.Eventos` virou uma **tabela ledger "somente inclusão"** do SQL Server 2022 ([`01_schema_seed.sql`](../sqlserver/01_schema_seed.sql)):
- ninguém altera nem apaga um evento, nem o `sa` nem o `db_owner` (erro 37359; `TRUNCATE` dá 13545);
- um `DROP TABLE` não apaga os dados: a tabela fica guardada como "dropped ledger table", e a operação entra no histórico da ledger;
- cada transação entra numa cadeia de hashes. O **digest** do banco é guardado fora dele, em [`ledger-digests.json`](../sqlserver/evidence/parte3/ledger-digests.json), que vai para o Git. `sp_verify_database_ledger` confere que nada mudou desde cada digest; um evento alterado direto no arquivo do banco quebraria a cadeia.

A migração copiou os 1.255 eventos com os mesmos números e gravou, na própria ledger, o evento `LEDGER_ATIVADA` com a contagem e o SHA-256 do conteúdo antigo. Antes de rodar no banco real, ela foi ensaiada numa cópia restaurada do backup (`SIGp_n8n_backups/antes-ledger-*.bak`), e o ensaio pegou um erro de sintaxe antes de chegar ao banco real.

Verificação ([`verificar_ledger.py`](verificar_ledger.py), evidência [`ledger-verificacao.json`](../sqlserver/evidence/parte3/ledger-verificacao.json)): **APROVADO**

| Teste | Esperado | Obtido | Veredito |
|---|---|---|---|
| A trilha é uma tabela ledger somente inclusão | APPEND_ONLY_LEDGER_TABLE | APPEND_ONLY_LEDGER_TABLE | OK |
| Ledger confere com os 2 digest(s) guardados fora do banco | verificada | verificada | OK |
| Controle: digest adulterado é recusado | erro 37392 | erro 37392 | OK |
| O sa altera um evento (UPDATE) | negado (erro 37359) | negado (erro 37359) | OK |
| O sa apaga eventos (DELETE) | negado (erro 37359) | negado (erro 37359) | OK |
| O sa esvazia a trilha (TRUNCATE) | negado (erro 13545) | negado (erro 13545) | OK |
| Nenhum evento sumiu depois das tentativas | >= 1259 | 1259 | OK |
| Migração registrada na própria trilha (LEDGER_ATIVADA) | 1 evento com contagem e SHA-256 | eventos_copiados=1255; sha256_antes=0x67528BBE3BCF117B69E703… | OK |

Efeito nos testes anteriores: o operador que tenta apagar ou reescrever a trilha agora recebe 37359 em vez de 229, porque a ledger recusa o comando na compilação, antes da checagem de permissão. O `08_ataque_escalonamento.sql` passou a aceitar 37359 como barrado (E4 e E5); a permissão `DENY` continua no lugar, como mostra a matriz de permissões.

## Limites

- O SQL Server Audit grava o **comando** da tentativa, que pode conter valores digitados, como uma chave fiscal num INSERT. Por isso o arquivo só é legível pelo administrador do servidor.
- Os gatilhos e a auditoria nativa deixam a gravação mais lenta. O custo do resumo diário foi medido antes deles, em [`otimizacao-consultas.md`](otimizacao-consultas.md). O custo total por nota gravada ainda não foi medido de novo.
- O `db_owner` e o `sa` ainda podem **deixar de registrar** daqui em diante: desligar o gatilho ou a auditoria nativa. O que já foi registrado eles não alteram nem apagam (ledger). Desligar o gatilho hoje não fica registrado: a auditoria nativa não inclui o grupo `SCHEMA_OBJECT_CHANGE_GROUP`, que cobre alteração de tabela e gatilho (próximo passo). A defesa contra isso continua operacional: a senha do `sa` só existe no `.env.academic`, ignorado pelo Git, e a IA e a API usam principais próprios, sem esses papéis.
- Os eventos de antes da migração foram copiados para a ledger em 21/11/2026: uma alteração feita antes dessa data não é detectável. O SHA-256 do conteúdo copiado está no evento `LEDGER_ATIVADA`.
- O digest é guardado no Git a cada execução do verificador. Sem um armazenamento imutável automático (no Azure, Blob imutável), a garantia vale até o último digest publicado.
