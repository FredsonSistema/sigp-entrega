# Avaliação de vulnerabilidades do SQL Server acadêmico

Gerado por `seguranca/avaliar_vulnerabilidades.py` a partir de `sqlserver/evidence/parte3/vulnerabilidades-antes.json` e `vulnerabilidades-depois.json`; nenhum número foi digitado à mão.

Regras no estilo do **SQL Vulnerability Assessment** (Microsoft, códigos VA) e do **CIS Microsoft SQL Server Benchmark** (códigos CIS), mais as proteções próprias do projeto (RLS, mascaramento, ledger, TDE). SQL Server 16.0.4305.5. A consulta (`sqlserver/18_avaliacao_vulnerabilidades.sql`) só lê; as correções estão em `19_correcoes_vulnerabilidades.sql` e `corrigir-vulnerabilidades.ps1` (reinicia o SQL Server para o TLS obrigatório e o acesso remoto valerem). A conexão da avaliação é a de um cliente de fora (sqlcmd do Windows, TCP, sem pedir criptografia): a regra V27 mostra se o servidor exige TLS.

| | Antes | Depois |
|---|---|---|
| Passaram | 21 | 25 |
| Riscos aceitos, com justificativa | 2 | 2 |
| Falharam | 4 | 0 |
| Execução (UTC) | 2026-11-25T11:11:56+00:00 | 2026-11-25T11:12:14+00:00 |

| Regra | Área | Referência | Antes | Depois | Detalhe depois |
|---|---|---|---|---|---|
| V01 xp_cmdshell desligado (executar comandos do sistema operacional a partir do SQL) | Superfície | CIS 2.15 · VA1008 | PASSOU (xp_cmdshell = 0) | PASSOU | xp_cmdshell = 0 |
| V02 CLR desligado (código .NET dentro do banco) | Superfície | CIS 2.2 · VA1102 | PASSOU (clr enabled = 0) | PASSOU | clr enabled = 0 |
| V03 Ole Automation Procedures desligado | Superfície | CIS 2.5 | PASSOU (Ole Automation Procedures = 0) | PASSOU | Ole Automation Procedures = 0 |
| V04 Consultas distribuídas ad hoc desligadas (OPENROWSET/OPENDATASOURCE) | Superfície | CIS 2.1 | PASSOU (Ad Hoc Distributed Queries = 0) | PASSOU | Ad Hoc Distributed Queries = 0 |
| V05 Encadeamento de propriedade entre bancos desligado | Superfície | CIS 2.3 | PASSOU (cross db ownership chaining = 0) | PASSOU | cross db ownership chaining = 0 |
| V06 Acesso remoto (RPC entre servidores) desligado | Superfície | CIS 2.6 | FALHOU (remote access = 1) | PASSOU **(corrigida)** | remote access = 0 |
| V07 Procedimentos automáticos na inicialização desligados | Superfície | CIS 2.12 | PASSOU (scan for startup procs = 0) | PASSOU | scan for startup procs = 0 |
| V08 Database Mail desligado (envio de e-mail pelo banco) | Superfície | CIS 2.4 | PASSOU (Database Mail XPs = 0) | PASSOU | Database Mail XPs = 0 |
| V09 Conexão de administrador dedicada (DAC) só local | Superfície | CIS 2.7 | PASSOU (remote admin connections = 0) | PASSOU | remote admin connections = 0 |
| V10 Login sa desativado | Autenticação | CIS 3.1 · VA1054 | ACEITO (sa ativo) | ACEITO | sa ativo |
| V11 Política de senha do sistema aplicada a todos os logins SQL ativos | Autenticação | CIS 4.3 · VA1048 | PASSOU (todos com CHECK_POLICY) | PASSOU | todos com CHECK_POLICY |
| V12 Só o sa (ou nenhum login de aplicação) no papel sysadmin | Autenticação | CIS 3.8 · VA1094 | FALHOU (sysadmin: BUILTIN\Administrators) | PASSOU **(corrigida)** | nenhum login além do sa |
| V13 Autenticação de banco contido desligada | Autenticação | CIS 2.16 | ACEITO (contained database authentication = 1) | ACEITO | contained database authentication = 1 |
| V14 Nenhum login com senha vazia ou igual ao nome | Autenticação | VA1043 · VA1044 | PASSOU (nenhum) | PASSOU | nenhum |
| V15 guest sem CONNECT no SIGpAcademic | Permissões | CIS 3.2 · VA1096 | PASSOU (guest sem acesso) | PASSOU | guest sem acesso |
| V16 Nenhuma permissão dada a public em objetos da aplicação | Permissões | VA1095 | PASSOU (nenhuma) | PASSOU | nenhuma |
| V17 Nenhum usuário órfão (usuário de banco sem login, fora os contidos) | Permissões | CIS 3.3 · VA1291 | PASSOU (nenhum) | PASSOU | nenhum |
| V18 db_owner só com o dono do banco (nenhum usuário de aplicação) | Permissões | VA1258 | PASSOU (nenhum membro al/m do dbo) | PASSOU | nenhum membro além do dbo |
| V19 Banco TRUSTWORTHY desligado | Permissões | CIS 2.9 · VA1102 | PASSOU (is_trustworthy_on = 0) | PASSOU | is_trustworthy_on = 0 |
| V20 Usuários da IA sem permissão direta em tabela (só EXECUTE no procedimento) | Permissões | Menor privilégio | PASSOU (nenhuma permiss/o de tabela) | PASSOU | nenhuma permissão de tabela |
| V21 Criptografia em repouso (TDE) ligada no SIGpAcademic | Dados | CIS 7.1 · VA1219 | PASSOU (TDE ligado (estado 3)) | PASSOU | TDE ligado (estado 3) |
| V22 Política de RLS ligada (cada credencial só vê o próprio local) | Dados | RLS | PASSOU (1 pol/tica(s) ligada(s)) | PASSOU | 1 política(s) ligada(s) |
| V23 Mascaramento dinâmico em colunas sensíveis | Dados | DDM | PASSOU (2 coluna(s) mascarada(s)) | PASSOU | 2 coluna(s) mascarada(s) |
| V24 Trilha de auditoria somente inclusão (tabela ledger) | Trilha | Ledger | PASSOU (1 tabela(s) ledger somente inclus/o) | PASSOU | 1 tabela(s) ledger somente inclusão |
| V25 SQL Server Audit ativo (logins e tentativas negadas) | Trilha | CIS 5.4 · VA1051 | PASSOU (1 auditoria(s) gravando) | PASSOU | 1 auditoria(s) gravando |
| V26 Falhas de login registradas | Trilha | CIS 5.3 | FALHOU (sem registro de falha de login) | PASSOU **(corrigida)** | FAILED_LOGIN_GROUP na especificação |
| V27 Esta conexão está criptografada (TLS) | Rede | VA2060 | FALHOU (encrypt_option = FALSE / TCP) | PASSOU **(corrigida)** | encrypt_option = TRUE · TCP |

## Riscos aceitos

- **V10 Login sa desativado.** O sa só é usado pelo instalador e pelos scripts de prova, com senha aleatória de 37 caracteres guardada no .env.academic (fora do Git), e a porta do SQL Server só abre em 127.0.0.1. A aplicação e a IA nunca usam o sa: cada uma tem usuário próprio, sem permissão direta em tabela (V20). Desativar o sa exige um login administrativo próprio em todos os scripts: fica como próximo passo.
- **V13 Autenticação de banco contido desligada.** Necessária por desenho: os usuários da IA existem só dentro do SIGpAcademic (banco contido), sem login na instância, então uma credencial vazada não abre nenhum outro banco nem a instância. Compensações: os usuários da IA só executam o procedimento (V20), a RLS limita ao próprio local (V22) e toda tentativa fica na auditoria (V25, V26).

## Falhas restantes

Nenhuma.
