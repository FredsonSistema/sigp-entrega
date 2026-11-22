/* Reproduz a falha ANTES da ledger, numa cópia descartável restaurada do backup de antes da migração (nada muda no banco real).
   Antes: o sa reescrevia e apagava eventos de audit.Eventos sem erro. Depois: seguranca/verificar_ledger.py (37359 / 13545).
   Uso: docker cp <SIGp_n8n_backups\antes-ledger-*.bak> sigp_sqlserver_academic:/var/opt/mssql/data/ensaio.bak
        sqlcmd -S 127.0.0.1,14333 -U sa -d master -C -I -f 65001 -i docs/entrega-academica/sqlserver/16_ledger_antes.sql
   Saída registrada em evidence/parte3/ledger-antes.txt. */
SET NOCOUNT ON;
IF DB_ID(N'SIGpAcademic_antes') IS NOT NULL BEGIN ALTER DATABASE SIGpAcademic_antes SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE SIGpAcademic_antes; END;
RESTORE DATABASE SIGpAcademic_antes FROM DISK = N'/var/opt/mssql/data/ensaio.bak' WITH MOVE N'SIGpAcademic' TO N'/var/opt/mssql/data/antes.mdf', MOVE N'SIGpAcademic_log' TO N'/var/opt/mssql/data/antes_log.ldf', RECOVERY;
GO
USE SIGpAcademic_antes;
PRINT 'Banco restaurado do backup antes-ledger (copia descartavel). Tentativas do sa na trilha, antes da ledger:';
SELECT ledger_type_desc AS tipo_da_tabela FROM sys.tables WHERE object_id = OBJECT_ID(N'audit.Eventos');
DECLARE @antes BIGINT = (SELECT COUNT_BIG(*) FROM audit.Eventos);
BEGIN TRANSACTION;
BEGIN TRY EXEC sys.sp_executesql N'UPDATE audit.Eventos SET ator = N''ninguem'' WHERE acao = N''AI_RESPONSE'';'; PRINT CONCAT('UPDATE: PERMITIDO (', @@ROWCOUNT, ' eventos reescritos)'); END TRY BEGIN CATCH PRINT CONCAT('UPDATE: negado ', ERROR_NUMBER()); END CATCH;
BEGIN TRY EXEC sys.sp_executesql N'DELETE FROM audit.Eventos WHERE acao = N''AI_CONTEXT_DENIED'';'; PRINT CONCAT('DELETE: PERMITIDO (', @@ROWCOUNT, ' eventos apagados)'); END TRY BEGIN CATCH PRINT CONCAT('DELETE: negado ', ERROR_NUMBER()); END CATCH;
DECLARE @depois BIGINT; SELECT @depois = COUNT_BIG(*) FROM audit.Eventos; PRINT CONCAT('eventos antes: ', @antes, ' / depois: ', @depois, ' (a trilha da aplicacao nao guarda nada da alteracao; a auditoria nativa guardaria o comando, mas o sa pode desliga-la)');
ROLLBACK TRANSACTION;
GO
USE master;
ALTER DATABASE SIGpAcademic_antes SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE SIGpAcademic_antes;
PRINT 'copia apagada';