/* TDE (Transparent Data Encryption): o arquivo do banco, o log e os backups do SIGpAcademic ficam criptografados (AES-256).
   Protege contra quem leva o arquivo ou um backup (antes, um backup sem compressão tinha a chave fiscal em texto puro).
   NÃO muda quem vê o quê numa consulta: isso continua com RLS, DENY e mascaramento.

   As senhas NÃO ficam aqui: vêm de variáveis do sqlcmd, que o chamador grava num arquivo temporário (nunca na linha de comando):
     :setvar TDE_MASTER_KEY_PASSWORD "..."      senha da chave mestra do master
     :setvar TDE_CERT_BACKUP_PASSWORD "..."     senha que protege a chave privada do certificado exportado
   Chamado por seguranca/ativar_tde.py e pelo instalar.ps1 do pacote. Idempotente.

   O certificado exportado (SIGpTDE.cer + SIGpTDE.pvk) é a ÚNICA forma de restaurar um backup em outro servidor: o chamador
   copia os dois arquivos para fora do container e do Git (SIGp_n8n_backups) e apaga a cópia do volume do banco. */
USE master;
GO
IF NOT EXISTS (SELECT 1 FROM sys.symmetric_keys WHERE name = N'##MS_DatabaseMasterKey##')
    CREATE MASTER KEY ENCRYPTION BY PASSWORD = N'$(TDE_MASTER_KEY_PASSWORD)';
GO
IF NOT EXISTS (SELECT 1 FROM sys.certificates WHERE name = N'SIGpTDE')
BEGIN
    CREATE CERTIFICATE SIGpTDE WITH SUBJECT = N'SIGp academico - TDE', EXPIRY_DATE = '20361231';
    BACKUP CERTIFICATE SIGpTDE TO FILE = N'/var/opt/mssql/data/SIGpTDE.cer'
        WITH PRIVATE KEY (FILE = N'/var/opt/mssql/data/SIGpTDE.pvk', ENCRYPTION BY PASSWORD = N'$(TDE_CERT_BACKUP_PASSWORD)');
    PRINT 'certificado criado e exportado';
END;
GO
USE SIGpAcademic;
GO
IF NOT EXISTS (SELECT 1 FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID())
    CREATE DATABASE ENCRYPTION KEY WITH ALGORITHM = AES_256 ENCRYPTION BY SERVER CERTIFICATE SIGpTDE;
GO
IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = N'SIGpAcademic' AND is_encrypted = 1)
    ALTER DATABASE SIGpAcademic SET ENCRYPTION ON;
GO
-- A criptografia roda em segundo plano: espera terminar (estado 3) por até 5 minutos.
DECLARE @i INT = 0;
WHILE @i < 150 AND NOT EXISTS (SELECT 1 FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'SIGpAcademic') AND encryption_state = 3)
BEGIN
    WAITFOR DELAY '00:00:02';
    SET @i += 1;
END;
SELECT DB_NAME(database_id) AS banco, encryption_state, encryption_state_desc, key_algorithm, key_length, percent_complete
FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID(N'SIGpAcademic');
GO
