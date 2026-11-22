/* Matriz final de papéis e permissões, tirada do próprio banco (não digitada).
   Parte 1: para cada usuário de teste, as permissões EFETIVAS em cada objeto (HAS_PERMS_BY_NAME como aquele usuário:
            considera GRANT, DENY, papéis e herança do schema) e o escopo de RLS.
   Parte 2: por que DENY e não só "sem GRANT". Dentro de uma transação desfeita, a API ganha o papel db_datawriter
            (DELETE em tudo): o DENY DELETE no schema app tem de continuar valendo; como controle, o mesmo papel apaga
            numa tabela de fora do schema app (onde não há DENY).
   Saída em JSON (uma linha por bloco) para seguranca/gerar_matriz.py. Nada muda no banco.
   Uso: sqlcmd -S 127.0.0.1,14333 -U sa -d SIGpAcademic -C -I -f 65001 -y 0 -i docs/entrega-academica/sqlserver/15_matriz_permissoes.sql */
USE SIGpAcademic;
SET NOCOUNT ON;

DECLARE @principais TABLE (usuario SYSNAME, perfil NVARCHAR(60), ordem INT);
INSERT @principais VALUES
    (N'sigp_api_test', N'API do sistema (papel sigp_api)', 1),
    (N'sigp_operador_loc001', N'Operador regional do LOC-001 (papel sigp_api)', 2),
    (N'sigp_auditor_test', N'Auditor (papel sigp_auditor)', 3),
    (N'sigp_fiscal_test', N'Fiscal (papel sigp_fiscal)', 4),
    (N'sigp_ia_loc001', N'IA do LOC-001 (papel sigp_ia)', 5),
    (N'sigp_denied_test', N'Sem papel', 6);

DECLARE @alvos TABLE (objeto NVARCHAR(80), classe NVARCHAR(20), permissao NVARCHAR(20), sub NVARCHAR(40), ordem INT);
INSERT @alvos
SELECT o.objeto, N'OBJECT', p.permissao, NULL, o.ordem
FROM (VALUES (N'app.Notas', 10), (N'app.ItensNota', 11), (N'app.Pagamentos', 12), (N'app.Conciliacoes', 13), (N'app.Locais', 14),
             (N'app.Provedores', 15), (N'app.ResumoDiario', 16), (N'security.LocalScope', 20), (N'audit.Eventos', 30),
             (N'ai.vw_contexto_minimo', 40)) AS o(objeto, ordem)
CROSS JOIN (VALUES (N'SELECT'), (N'INSERT'), (N'UPDATE'), (N'DELETE')) AS p(permissao);
INSERT @alvos VALUES
    (N'ai.usp_get_context', N'OBJECT', N'EXECUTE', NULL, 50),
    (N'ai.usp_log_sources', N'OBJECT', N'EXECUTE', NULL, 51),
    (N'ai.usp_log_response', N'OBJECT', N'EXECUTE', NULL, 52),
    (N'app.Notas', N'OBJECT', N'UNMASK', N'chave_fiscal', 60),
    (N'app.Pagamentos', N'OBJECT', N'UNMASK', N'referencia', 61),
    (N'sigp_auditor', N'ROLE', N'ALTER', NULL, 70),
    (N'sigp_ia_loc002', N'USER', N'IMPERSONATE', NULL, 71);

DECLARE @r TABLE (usuario SYSNAME, objeto NVARCHAR(80), permissao NVARCHAR(20), sub NVARCHAR(40), efetiva BIT, ordem INT);
DECLARE @u SYSNAME;
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT usuario FROM @principais ORDER BY ordem;
OPEN c;
FETCH NEXT FROM c INTO @u;
WHILE @@FETCH_STATUS = 0
BEGIN
    EXECUTE AS USER = @u;
    INSERT @r
    SELECT @u, a.objeto, a.permissao, a.sub,
           CASE WHEN a.sub IS NULL THEN HAS_PERMS_BY_NAME(a.objeto, a.classe, a.permissao)
                ELSE HAS_PERMS_BY_NAME(a.objeto, a.classe, a.permissao, a.sub, N'COLUMN') END,
           a.ordem
    FROM @alvos AS a;
    REVERT;
    FETCH NEXT FROM c INTO @u;
END;
CLOSE c;
DEALLOCATE c;

SELECT (SELECT p.usuario, p.perfil, p.ordem,
               (SELECT STRING_AGG(r.name, N',') FROM sys.database_role_members AS m
                JOIN sys.database_principals AS r ON r.principal_id = m.role_principal_id
                WHERE m.member_principal_id = DATABASE_PRINCIPAL_ID(p.usuario)) AS papeis,
               (SELECT STRING_AGG(s.local_id, N',') WITHIN GROUP (ORDER BY s.local_id) FROM security.LocalScope AS s
                WHERE s.principal_name = p.usuario) AS escopo_rls
        FROM @principais AS p ORDER BY p.ordem FOR JSON PATH) AS principais_json;

SELECT (SELECT usuario, objeto, permissao, sub, efetiva, ordem FROM @r ORDER BY ordem, objeto, permissao, usuario FOR JSON PATH) AS matriz_json;

-- Todos os DENY explícitos, com o alvo legível (schema ou objeto).
SELECT (SELECT USER_NAME(dp.grantee_principal_id) AS papel, dp.permission_name AS permissao,
               CASE dp.class WHEN 3 THEN CONCAT(N'SCHEMA::', SCHEMA_NAME(dp.major_id))
                             WHEN 1 THEN CONCAT(OBJECT_SCHEMA_NAME(dp.major_id), N'.', OBJECT_NAME(dp.major_id)) END AS alvo
        FROM sys.database_permissions AS dp
        WHERE dp.state = 'D' AND USER_NAME(dp.grantee_principal_id) LIKE N'sigp%'
        ORDER BY 1, 3, 2 FOR JSON PATH) AS denys_json;

/* Parte 2: prova do DENY */
DECLARE @prova TABLE (teste NVARCHAR(120), esperado NVARCHAR(40), obtido NVARCHAR(60));
DECLARE @erro INT, @linhas INT;
BEGIN TRANSACTION;
ALTER ROLE db_datawriter ADD MEMBER sigp_api_test;
INSERT @prova VALUES (N'API no papel db_datawriter (DELETE em tudo)', N'membro', CASE WHEN IS_ROLEMEMBER(N'db_datawriter', N'sigp_api_test') = 1 THEN N'membro' ELSE N'não' END);
EXECUTE AS USER = N'sigp_api_test';
SET @erro = NULL; SET @linhas = NULL;
BEGIN TRY DELETE TOP (1) FROM app.Notas; SET @linhas = @@ROWCOUNT; END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
INSERT @prova VALUES (N'Com db_datawriter, apagar uma nota (schema app, DENY DELETE)', N'negado (229)',
    CASE WHEN @erro IS NULL THEN CONCAT(N'PERMITIDO (', @linhas, N' linha)') ELSE CONCAT(N'negado (', @erro, N')') END);
SET @erro = NULL; SET @linhas = NULL;
-- Sem WHERE: um WHERE exigiria também permissão de leitura, que o db_datawriter não dá (o ROLLBACK desfaz a exclusão).
BEGIN TRY DELETE TOP (1) FROM security.LocalScope; SET @linhas = @@ROWCOUNT; END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
INSERT @prova VALUES (N'Controle: com db_datawriter, apagar em security.LocalScope (sem DENY)', N'permitido',
    CASE WHEN @erro IS NULL THEN N'permitido' ELSE CONCAT(N'negado (', @erro, N')') END);
REVERT;
ROLLBACK TRANSACTION;
INSERT @prova VALUES (N'Depois do ROLLBACK, o escopo de RLS continua com todas as linhas', N'13 linhas',
    CONCAT((SELECT COUNT(*) FROM security.LocalScope), N' linhas'));
INSERT @prova VALUES (N'Depois do ROLLBACK, a API voltou a não ter db_datawriter', N'não',
    CASE WHEN IS_ROLEMEMBER(N'db_datawriter', N'sigp_api_test') = 1 THEN N'membro' ELSE N'não' END);

SELECT (SELECT teste, esperado, obtido,
               CASE WHEN obtido = esperado OR (esperado LIKE N'negado%' AND obtido LIKE N'negado%') THEN N'OK' ELSE N'FALHA' END AS veredito
        FROM @prova FOR JSON PATH) AS prova_deny_json;
