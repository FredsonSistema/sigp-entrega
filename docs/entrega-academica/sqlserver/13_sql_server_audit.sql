/* Auditoria nativa do SQL Server (SQL Server Audit), complementar à trilha da aplicação (audit.Eventos).
   O gatilho de auditoria registra o que FOI gravado; um gatilho não vê o que foi NEGADO (a instrução é desfeita).
   O SQL Server Audit registra também as tentativas: gravações nos schemas app, audit e security (com sucesso ou não),
   mudanças de papel e de permissão e personificação (EXECUTE AS), com o principal real e o comando.
   Leituras não são auditadas aqui (as da IA já estão em audit.Eventos; auditar toda leitura encheria o arquivo).
   O arquivo fica no volume do banco e só o administrador do servidor o lê (sys.fn_get_audit_file).
   Idempotente: pode rodar de novo. Uso (raiz do projeto, senha só em variável de ambiente):
     sqlcmd -S 127.0.0.1,14333 -U sa -d master -C -I -b -i docs/entrega-academica/sqlserver/13_sql_server_audit.sql */
USE master;
SET NOCOUNT ON;
IF NOT EXISTS (SELECT 1 FROM sys.server_audits WHERE name = N'SIGpAcademicAudit')
    CREATE SERVER AUDIT SIGpAcademicAudit
        TO FILE (FILEPATH = N'/var/opt/mssql/data/', MAXSIZE = 50 MB, MAX_ROLLOVER_FILES = 10, RESERVE_DISK_SPACE = OFF)
        WITH (QUEUE_DELAY = 1000, ON_FAILURE = CONTINUE);
IF EXISTS (SELECT 1 FROM sys.server_audits WHERE name = N'SIGpAcademicAudit' AND is_state_enabled = 0)
    ALTER SERVER AUDIT SIGpAcademicAudit WITH (STATE = ON);
GO

USE SIGpAcademic;
GO
IF EXISTS (SELECT 1 FROM sys.database_audit_specifications WHERE name = N'SIGpAcademicDados')
BEGIN
    ALTER DATABASE AUDIT SPECIFICATION SIGpAcademicDados WITH (STATE = OFF);
    DROP DATABASE AUDIT SPECIFICATION SIGpAcademicDados;
END;
GO
CREATE DATABASE AUDIT SPECIFICATION SIGpAcademicDados
FOR SERVER AUDIT SIGpAcademicAudit
    ADD (INSERT, UPDATE, DELETE ON SCHEMA::app BY public),
    ADD (INSERT, UPDATE, DELETE ON SCHEMA::audit BY public),
    ADD (INSERT, UPDATE, DELETE ON SCHEMA::security BY public),
    ADD (DATABASE_ROLE_MEMBER_CHANGE_GROUP),
    ADD (DATABASE_PRINCIPAL_IMPERSONATION_GROUP),
    ADD (DATABASE_PERMISSION_CHANGE_GROUP),
    ADD (SCHEMA_OBJECT_PERMISSION_CHANGE_GROUP),
    ADD (DATABASE_OBJECT_CHANGE_GROUP)
WITH (STATE = ON);
GO
SELECT a.name AS auditoria, a.is_state_enabled AS ligada, f.log_file_path AS pasta,
       s.name AS especificacao, s.is_state_enabled AS especificacao_ligada
FROM sys.server_audits AS a
JOIN sys.server_file_audits AS f ON f.audit_guid = a.audit_guid
LEFT JOIN sys.database_audit_specifications AS s ON s.audit_guid = a.audit_guid
WHERE a.name = N'SIGpAcademicAudit';
