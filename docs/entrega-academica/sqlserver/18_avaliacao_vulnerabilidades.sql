-- Avaliação de vulnerabilidades do SQL Server acadêmico, no estilo do SQL Vulnerability Assessment (Microsoft) e do
-- CIS Microsoft SQL Server Benchmark. Só lê: nenhuma configuração é alterada aqui (as correções estão no
-- 19_correcoes_vulnerabilidades.sql). Devolve uma linha JSON com cada verificação: PASSOU ou FALHOU e o detalhe.
-- Quem decide o que é risco aceito, e por quê, é o seguranca/avaliar_vulnerabilidades.py (com a justificativa escrita).
-- O SIGpAcademic é um banco contido (outra collation no catálogo): os nomes vindos dele levam COLLATE DATABASE_DEFAULT.
-- Uso: sqlcmd ... -d master -i 18_avaliacao_vulnerabilidades.sql   (o avaliar_vulnerabilidades.py faz isso)
SET NOCOUNT ON;
DECLARE @r TABLE (id VARCHAR(8), area NVARCHAR(40), regra NVARCHAR(200), referencia NVARCHAR(80), passou BIT, detalhe NVARCHAR(400));
DECLARE @cfg TABLE (nome NVARCHAR(70), valor INT);
INSERT INTO @cfg SELECT name, CONVERT(INT, value_in_use) FROM sys.configurations;

-- ---------------------------------------------------------------- superfície de ataque da instância
INSERT INTO @r SELECT 'V01', N'Superfície', N'xp_cmdshell desligado (executar comandos do sistema operacional a partir do SQL)', N'CIS 2.15 · VA1008',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'xp_cmdshell = ', valor) FROM @cfg WHERE nome = N'xp_cmdshell';
INSERT INTO @r SELECT 'V02', N'Superfície', N'CLR desligado (código .NET dentro do banco)', N'CIS 2.2 · VA1102',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'clr enabled = ', valor) FROM @cfg WHERE nome = N'clr enabled';
INSERT INTO @r SELECT 'V03', N'Superfície', N'Ole Automation Procedures desligado', N'CIS 2.5',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'Ole Automation Procedures = ', valor) FROM @cfg WHERE nome = N'Ole Automation Procedures';
INSERT INTO @r SELECT 'V04', N'Superfície', N'Consultas distribuídas ad hoc desligadas (OPENROWSET/OPENDATASOURCE)', N'CIS 2.1',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'Ad Hoc Distributed Queries = ', valor) FROM @cfg WHERE nome = N'Ad Hoc Distributed Queries';
INSERT INTO @r SELECT 'V05', N'Superfície', N'Encadeamento de propriedade entre bancos desligado', N'CIS 2.3',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'cross db ownership chaining = ', valor) FROM @cfg WHERE nome = N'cross db ownership chaining';
INSERT INTO @r SELECT 'V06', N'Superfície', N'Acesso remoto (RPC entre servidores) desligado', N'CIS 2.6',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'remote access = ', valor) FROM @cfg WHERE nome = N'remote access';
INSERT INTO @r SELECT 'V07', N'Superfície', N'Procedimentos automáticos na inicialização desligados', N'CIS 2.12',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'scan for startup procs = ', valor) FROM @cfg WHERE nome = N'scan for startup procs';
INSERT INTO @r SELECT 'V08', N'Superfície', N'Database Mail desligado (envio de e-mail pelo banco)', N'CIS 2.4',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'Database Mail XPs = ', valor) FROM @cfg WHERE nome = N'Database Mail XPs';
INSERT INTO @r SELECT 'V09', N'Superfície', N'Conexão de administrador dedicada (DAC) só local', N'CIS 2.7',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'remote admin connections = ', valor) FROM @cfg WHERE nome = N'remote admin connections';

-- ---------------------------------------------------------------- logins e autenticação
INSERT INTO @r SELECT 'V10', N'Autenticação', N'Login sa desativado', N'CIS 3.1 · VA1054',
    CASE WHEN is_disabled = 1 THEN 1 ELSE 0 END, CASE WHEN is_disabled = 1 THEN N'sa desativado' ELSE N'sa ativo' END
    FROM sys.sql_logins WHERE principal_id = 1;
INSERT INTO @r SELECT 'V11', N'Autenticação', N'Política de senha do sistema aplicada a todos os logins SQL ativos', N'CIS 4.3 · VA1048',
    CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END,
    CASE WHEN COUNT(*) = 0 THEN N'todos com CHECK_POLICY' ELSE CONCAT(COUNT(*), N' login(s) sem CHECK_POLICY: ', STRING_AGG(name, N', ')) END
    FROM sys.sql_logins WHERE is_disabled = 0 AND is_policy_checked = 0 AND name NOT LIKE N'##%';
INSERT INTO @r SELECT 'V12', N'Autenticação', N'Só o sa (ou nenhum login de aplicação) no papel sysadmin', N'CIS 3.8 · VA1094',
    CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END,
    CASE WHEN COUNT(*) = 0 THEN N'nenhum login além do sa' ELSE CONCAT(N'sysadmin: ', STRING_AGG(p.name, N', ')) END
    FROM sys.server_role_members m JOIN sys.server_principals p ON p.principal_id = m.member_principal_id
    WHERE m.role_principal_id = SUSER_ID(N'sysadmin') AND p.principal_id <> 1 AND p.name NOT LIKE N'NT %' AND p.name NOT LIKE N'##%';
INSERT INTO @r SELECT 'V13', N'Autenticação', N'Autenticação de banco contido desligada', N'CIS 2.16',
    CASE WHEN valor = 0 THEN 1 ELSE 0 END, CONCAT(N'contained database authentication = ', valor) FROM @cfg WHERE nome = N'contained database authentication';
INSERT INTO @r SELECT 'V14', N'Autenticação', N'Nenhum login com senha vazia ou igual ao nome', N'VA1043 · VA1044',
    CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END,
    CASE WHEN COUNT(*) = 0 THEN N'nenhum' ELSE STRING_AGG(name, N', ') END
    FROM sys.sql_logins WHERE PWDCOMPARE(N'', password_hash) = 1 OR PWDCOMPARE(name, password_hash) = 1;

-- ---------------------------------------------------------------- permissões no banco da aplicação
INSERT INTO @r SELECT 'V15', N'Permissões', N'guest sem CONNECT no SIGpAcademic', N'CIS 3.2 · VA1096',
    CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END, CASE WHEN COUNT(*) = 0 THEN N'guest sem acesso' ELSE N'guest com CONNECT' END
    FROM SIGpAcademic.sys.database_permissions WHERE grantee_principal_id = 2  -- guest
      AND permission_name = N'CONNECT' AND state IN ('G', 'W');
INSERT INTO @r SELECT 'V16', N'Permissões', N'Nenhuma permissão dada a public em objetos da aplicação', N'VA1095',
    CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END,
    CASE WHEN COUNT(*) = 0 THEN N'nenhuma' ELSE CONCAT(COUNT(*), N': ', STRING_AGG(CAST(CONCAT(dp.permission_name, N' em ', s.name, N'.', o.name) AS NVARCHAR(400)) COLLATE DATABASE_DEFAULT, N', ')) END
    FROM SIGpAcademic.sys.database_permissions dp
    JOIN SIGpAcademic.sys.objects o ON o.object_id = dp.major_id
    JOIN SIGpAcademic.sys.schemas s ON s.schema_id = o.schema_id
    WHERE dp.grantee_principal_id = 0 AND dp.class = 1 AND dp.state IN ('G', 'W') AND s.name NOT IN (N'sys', N'INFORMATION_SCHEMA');
INSERT INTO @r SELECT 'V17', N'Permissões', N'Nenhum usuário órfão (usuário de banco sem login, fora os contidos)', N'CIS 3.3 · VA1291',
    CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END, CASE WHEN COUNT(*) = 0 THEN N'nenhum' ELSE STRING_AGG(dp.name COLLATE DATABASE_DEFAULT, N', ') END
    FROM SIGpAcademic.sys.database_principals dp
    LEFT JOIN sys.server_principals sp ON sp.sid = dp.sid
    WHERE dp.type IN ('S', 'U') AND dp.authentication_type = 1 AND dp.principal_id > 4 AND sp.sid IS NULL;  -- 1 = login da instância
INSERT INTO @r SELECT 'V18', N'Permissões', N'db_owner só com o dono do banco (nenhum usuário de aplicação)', N'VA1258',
    CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END, CASE WHEN COUNT(*) = 0 THEN N'nenhum membro além do dbo' ELSE STRING_AGG(u.name COLLATE DATABASE_DEFAULT, N', ') END
    FROM SIGpAcademic.sys.database_role_members m JOIN SIGpAcademic.sys.database_principals u ON u.principal_id = m.member_principal_id
    WHERE m.role_principal_id = (SELECT principal_id FROM SIGpAcademic.sys.database_principals WHERE name = N'db_owner') AND u.name <> N'dbo';
INSERT INTO @r SELECT 'V19', N'Permissões', N'Banco TRUSTWORTHY desligado', N'CIS 2.9 · VA1102',
    CASE WHEN is_trustworthy_on = 0 THEN 1 ELSE 0 END, CONCAT(N'is_trustworthy_on = ', is_trustworthy_on) FROM sys.databases WHERE name = N'SIGpAcademic';
INSERT INTO @r SELECT 'V20', N'Permissões', N'Usuários da IA sem permissão direta em tabela (só EXECUTE no procedimento)', N'Menor privilégio',
    CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END,
    CASE WHEN COUNT(*) = 0 THEN N'nenhuma permissão de tabela' ELSE STRING_AGG(CAST(CONCAT(u.name, N': ', dp.permission_name, N' em ', o.name) AS NVARCHAR(400)) COLLATE DATABASE_DEFAULT, N', ') END
    FROM SIGpAcademic.sys.database_permissions dp
    JOIN SIGpAcademic.sys.database_principals u ON u.principal_id = dp.grantee_principal_id
    JOIN SIGpAcademic.sys.objects o ON o.object_id = dp.major_id
    WHERE u.name LIKE N'sigp_ia%' AND dp.class = 1 AND o.type = 'U' AND dp.state IN ('G', 'W');

-- ---------------------------------------------------------------- proteção dos dados e trilha
INSERT INTO @r SELECT 'V21', N'Dados', N'Criptografia em repouso (TDE) ligada no SIGpAcademic', N'CIS 7.1 · VA1219',
    CASE WHEN COUNT(*) = 1 THEN 1 ELSE 0 END,
    CASE WHEN COUNT(*) = 1 THEN N'TDE ligado (estado 3)' ELSE N'TDE desligado' END
    FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'SIGpAcademic') AND encryption_state = 3;
INSERT INTO @r SELECT 'V22', N'Dados', N'Política de RLS ligada (cada credencial só vê o próprio local)', N'RLS',
    CASE WHEN COUNT(*) >= 1 THEN 1 ELSE 0 END, CONCAT(COUNT(*), N' política(s) ligada(s)')
    FROM SIGpAcademic.sys.security_policies WHERE is_enabled = 1;
INSERT INTO @r SELECT 'V23', N'Dados', N'Mascaramento dinâmico em colunas sensíveis', N'DDM',
    CASE WHEN COUNT(*) >= 1 THEN 1 ELSE 0 END, CONCAT(COUNT(*), N' coluna(s) mascarada(s)')
    FROM SIGpAcademic.sys.masked_columns;
INSERT INTO @r SELECT 'V24', N'Trilha', N'Trilha de auditoria somente inclusão (tabela ledger)', N'Ledger',
    CASE WHEN COUNT(*) >= 1 THEN 1 ELSE 0 END, CONCAT(COUNT(*), N' tabela(s) ledger somente inclusão')
    FROM SIGpAcademic.sys.tables WHERE ledger_type = 3;  -- 3 = APPEND_ONLY_LEDGER_TABLE
INSERT INTO @r SELECT 'V25', N'Trilha', N'SQL Server Audit ativo (logins e tentativas negadas)', N'CIS 5.4 · VA1051',
    CASE WHEN COUNT(*) >= 1 THEN 1 ELSE 0 END, CONCAT(COUNT(*), N' auditoria(s) gravando')
    FROM sys.dm_server_audit_status WHERE status_desc = N'STARTED';
INSERT INTO @r SELECT 'V26', N'Trilha', N'Falhas de login registradas', N'CIS 5.3',
    CASE WHEN COUNT(*) >= 1 THEN 1 ELSE 0 END, CASE WHEN COUNT(*) >= 1 THEN N'FAILED_LOGIN_GROUP na especificação' ELSE N'sem registro de falha de login' END
    FROM sys.server_audit_specification_details WHERE audit_action_name = N'FAILED_LOGIN_GROUP';
INSERT INTO @r SELECT 'V27', N'Rede', N'Esta conexão está criptografada (TLS)', N'VA2060',
    CASE WHEN encrypt_option = 'TRUE' THEN 1 ELSE 0 END, CONCAT(N'encrypt_option = ', encrypt_option, N' / ', net_transport)
    FROM sys.dm_exec_connections WHERE session_id = @@SPID;

SELECT (SELECT id, area, regra, referencia, CAST(passou AS BIT) AS passou, detalhe,
               CONVERT(NVARCHAR(20), SERVERPROPERTY('ProductVersion')) AS versao
        FROM @r ORDER BY id FOR JSON PATH) AS j;
