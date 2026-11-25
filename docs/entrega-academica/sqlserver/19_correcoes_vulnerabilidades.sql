-- Correções da avaliação de vulnerabilidades (18_avaliacao_vulnerabilidades.sql). Idempotente: pode rodar de novo.
-- O que precisa reiniciar o SQL Server (acesso remoto e criptografia obrigatória da conexão) é feito pelo
-- corrigir-vulnerabilidades.ps1, que roda este arquivo, liga o TLS obrigatório (mssql-conf) e reinicia o container.
-- Riscos aceitos, com justificativa, ficam no avaliar_vulnerabilidades.py (V10 sa ativo, V13 banco contido).
SET NOCOUNT ON;
USE master;

-- V06: acesso remoto (RPC entre servidores). Nada no SIGp usa servidor vinculado nem procedimento remoto.
IF EXISTS (SELECT 1 FROM sys.configurations WHERE name = N'remote access' AND CONVERT(INT, value) <> 0)
BEGIN
    EXEC sp_configure 'show advanced options', 1; RECONFIGURE;
    EXEC sp_configure 'remote access', 0; RECONFIGURE;
    EXEC sp_configure 'show advanced options', 0; RECONFIGURE;
    PRINT N'V06: remote access desligado (vale depois de reiniciar o SQL Server).';
END;

-- V12: BUILTIN\Administrators no papel sysadmin. No SQL Server em Linux não existe login do Windows: o grupo não serve
-- para nada e só ampliaria quem é sysadmin se a autenticação do Windows fosse ligada um dia.
IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'BUILTIN\Administrators')
BEGIN
    DROP LOGIN [BUILTIN\Administrators];
    PRINT N'V12: login BUILTIN\Administrators removido.';
END;

-- V26: falhas e sucessos de login no SQL Server Audit (a mesma auditoria das tentativas negadas nos dados).
IF NOT EXISTS (SELECT 1 FROM sys.server_audit_specifications WHERE name = N'SIGpAcademicLogins')
   AND EXISTS (SELECT 1 FROM sys.server_audits WHERE name = N'SIGpAcademicAudit')
BEGIN
    CREATE SERVER AUDIT SPECIFICATION SIGpAcademicLogins
    FOR SERVER AUDIT SIGpAcademicAudit
        ADD (FAILED_LOGIN_GROUP),
        ADD (SUCCESSFUL_LOGIN_GROUP),
        ADD (SERVER_ROLE_MEMBER_CHANGE_GROUP),
        ADD (SERVER_PRINCIPAL_CHANGE_GROUP),
        ADD (AUDIT_CHANGE_GROUP)
    WITH (STATE = ON);
    PRINT N'V26: logins (falhas e sucessos), mudanças de logins e de papéis do servidor e mudanças na própria auditoria registrados.';
END;

SELECT name, CONVERT(INT, value) AS configurado, CONVERT(INT, value_in_use) AS em_uso
FROM sys.configurations WHERE name IN (N'remote access');
