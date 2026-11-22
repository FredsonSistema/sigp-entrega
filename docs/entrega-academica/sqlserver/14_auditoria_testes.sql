/* Trilha de auditoria: quem fez o quê no banco.
   T1. Gravações em app.Notas viram eventos com o usuário real, o que mudou e quando (gatilho app.trg_Notas_Auditoria).
   T2. A trilha não pode ser forjada, apagada, lida por quem não é auditor, nem desligada.
   T3. Tentativas NEGADAS ficam registradas (SQL Server Audit, 13_sql_server_audit.sql).
   Tudo que grava dados roda em transação com ROLLBACK. Os eventos de T1 são mostrados antes do ROLLBACK.
   Uso (raiz do projeto, senha só em variável de ambiente):
     sqlcmd -S 127.0.0.1,14333 -U sa -d SIGpAcademic -C -I -W -s "|" -f 65001 -i docs/entrega-academica/sqlserver/14_auditoria_testes.sql */
USE SIGpAcademic;
SET NOCOUNT ON;

DECLARE @r TABLE (id NVARCHAR(4), teste NVARCHAR(120), esperado NVARCHAR(120), obtido NVARCHAR(120));
DECLARE @u NVARCHAR(8) = LEFT(CONVERT(NVARCHAR(36), NEWID()), 8);
DECLARE @inicio DATETIME2 = SYSUTCDATETIME();
DECLARE @erro INT, @n INT, @id1 BIGINT, @id2 BIGINT;

/* ------------------------------------------------------------ T1. gravações viram eventos */
BEGIN TRANSACTION;
EXECUTE AS USER = N'sigp_operador_loc001';
INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
VALUES (N'LOC-001', N'PROV-001', CONCAT(N'AUD-', @u, N'-1'), N'AUD1', N'A', 11.00, '20261101', '20261201', N'teste', N'PENDENTE'),
       (N'LOC-001', N'PROV-001', CONCAT(N'AUD-', @u, N'-2'), N'AUD2', N'A', 22.00, '20261102', '20261202', N'teste', N'PENDENTE');
SELECT @id1 = MIN(id), @id2 = MAX(id) FROM app.Notas WHERE chave_fiscal LIKE CONCAT(N'AUD-', @u, N'-%');
UPDATE app.Notas SET valor_total = 12.50, status = N'RECEBIDA' WHERE id = @id1;
UPDATE app.Notas SET chave_fiscal = CONCAT(N'AUD-', @u, N'-NOVA-CHAVE-SECRETA') WHERE id = @id2;
REVERT;
DELETE FROM app.Notas WHERE id = @id2;  -- a API tem DENY DELETE: quem apaga é o dono
;WITH s(k) AS (SELECT 1 UNION ALL SELECT k + 1 FROM s WHERE k < 150)
INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
SELECT N'LOC-002', N'PROV-002', CONCAT(N'AUDL-', @u, N'-', k), CONCAT(N'L', k), N'A', 5.00, '20261103', '20261203', N'teste', N'PENDENTE'
FROM s OPTION (MAXRECURSION 150);

DECLARE @ev TABLE (ator NVARCHAR(80), acao NVARCHAR(40), detalhe NVARCHAR(500));
INSERT INTO @ev SELECT ator, acao, detalhe_redigido FROM audit.Eventos WHERE objeto = N'app.Notas' AND criado_em >= @inicio;

SELECT N'eventos gravados nesta transação (antes do ROLLBACK)' AS trilha, ator, acao, detalhe FROM @ev ORDER BY acao, detalhe;

INSERT @r SELECT N'T1a', N'Inserção do operador registrada com o usuário real', N'2 eventos (sigp_operador_loc001)',
    CONCAT(COUNT(*), N' eventos (', COALESCE(MIN(ator), N'-'), N')') FROM @ev WHERE acao = N'NOTA_INSERIDA';
INSERT @r SELECT N'T1b', N'Alteração registra o antes e o depois', N'valor 11.00→12.50; status PENDENTE→RECEBIDA',
    COALESCE(MAX(CASE WHEN detalhe LIKE N'%valor 11.00→12.50%' AND detalhe LIKE N'%status PENDENTE→RECEBIDA%' THEN N'valor 11.00→12.50; status PENDENTE→RECEBIDA' END), N'não registrado')
    FROM @ev WHERE acao = N'NOTA_ALTERADA';
INSERT @r SELECT N'T1c', N'Troca de chave fiscal registrada sem o valor da chave', N'registrada, valor omitido',
    CASE WHEN EXISTS (SELECT 1 FROM @ev WHERE detalhe LIKE N'%chave_fiscal (valor omitido)%')
          AND NOT EXISTS (SELECT 1 FROM @ev WHERE detalhe LIKE N'%SECRETA%') THEN N'registrada, valor omitido'
         WHEN EXISTS (SELECT 1 FROM @ev WHERE detalhe LIKE N'%SECRETA%') THEN N'VALOR DA CHAVE NA TRILHA' ELSE N'não registrado' END;
INSERT @r SELECT N'T1d', N'Exclusão registrada com quem apagou', N'1 evento (dbo)',
    CONCAT(COUNT(*), N' evento (', COALESCE(MIN(ator), N'-'), N')') FROM @ev WHERE acao = N'NOTA_EXCLUIDA';
INSERT @r SELECT N'T1e', N'Lote de 150 notas vira um evento só', N'1 evento, linhas=150',
    CONCAT(COUNT(*), N' evento', CASE WHEN MAX(detalhe) LIKE N'linhas=150;%' THEN N', linhas=150' ELSE N'' END) FROM @ev WHERE acao = N'NOTA_INSERIDA_LOTE';
ROLLBACK TRANSACTION;

/* ------------------------------------------------------------ T2. a trilha não pode ser adulterada */
SET @erro = NULL;
BEGIN TRANSACTION;
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    EXEC sys.sp_executesql N'INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido) VALUES (N''sigp_auditor_test'', N''NOTA_EXCLUIDA'', N''app.Notas'', NEWID(), N''evento falso'');';
END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
REVERT;
INSERT @r VALUES (N'T2a', N'Operador forja um evento na trilha (INSERT direto)', N'negado', CASE WHEN @erro IS NULL THEN N'PERMITIDO' ELSE CONCAT(N'negado (', @erro, N')') END);

SET @erro = NULL;
BEGIN TRANSACTION;
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY EXEC sys.sp_executesql N'DELETE FROM audit.Eventos WHERE objeto = N''app.Notas'';'; END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
REVERT;
INSERT @r VALUES (N'T2b', N'Operador apaga a trilha', N'negado', CASE WHEN @erro IS NULL THEN N'PERMITIDO' ELSE CONCAT(N'negado (', @erro, N')') END);

SET @erro = NULL;
BEGIN TRANSACTION;
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY EXEC sys.sp_executesql N'DISABLE TRIGGER app.trg_Notas_Auditoria ON app.Notas;'; END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
REVERT;
-- 1088 também é o erro de "objeto não existe": sem o gatilho, o resultado não vale como negação.
INSERT @r VALUES (N'T2c', N'Operador desliga o gatilho de auditoria', N'negado',
    CASE WHEN OBJECT_ID(N'app.trg_Notas_Auditoria', N'TR') IS NULL THEN N'gatilho de auditoria não existe'
         WHEN @erro IS NULL THEN N'PERMITIDO' ELSE CONCAT(N'negado (', @erro, N')') END);

SET @erro = NULL;
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY EXEC sys.sp_executesql N'SELECT TOP (1) * FROM audit.Eventos;'; END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
REVERT;
INSERT @r VALUES (N'T2d', N'Operador lê a trilha', N'negado', CASE WHEN @erro IS NULL THEN N'PERMITIDO' ELSE CONCAT(N'negado (', @erro, N')') END);

SET @erro = NULL;
EXECUTE AS USER = N'sigp_auditor_test';
BEGIN TRY SELECT @n = COUNT(*) FROM audit.Eventos; END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
REVERT;
INSERT @r VALUES (N'T2e', N'Auditor lê a trilha', N'permitido', CASE WHEN @erro IS NULL THEN N'permitido' ELSE CONCAT(N'NEGADO (', @erro, N')') END);

/* ------------------------------------------------------------ T3. tentativas negadas ficam registradas */
DECLARE @marca DATETIME2 = SYSUTCDATETIME();
SET @erro = NULL;
BEGIN TRANSACTION;
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
    VALUES (N'LOC-002', N'PROV-002', CONCAT(N'AUDX-', @u), N'X', N'A', 1.00, '20261101', '20261201', N'teste', N'RECEBIDA');
END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
REVERT;
DECLARE @erro2 INT = NULL;
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY EXEC sys.sp_executesql N'ALTER ROLE sigp_auditor ADD MEMBER sigp_operador_loc001;'; END TRY
BEGIN CATCH SET @erro2 = ERROR_NUMBER(); END CATCH;
REVERT;

IF EXISTS (SELECT 1 FROM sys.server_audits WHERE name = N'SIGpAcademicAudit' AND is_state_enabled = 1)
BEGIN
    DECLARE @caminho NVARCHAR(400) = (SELECT log_file_path + N'SIGpAcademicAudit*.sqlaudit' FROM sys.server_file_audits WHERE name = N'SIGpAcademicAudit');
    DECLARE @a TABLE (acao NVARCHAR(10), sucesso BIT, quem SYSNAME, objeto SYSNAME, comando NVARCHAR(4000));
    -- O SQL Server grava o arquivo de auditoria de forma assíncrona: espera um pouco antes de ler.
    WAITFOR DELAY '00:00:02';
    INSERT INTO @a
    SELECT action_id, succeeded, database_principal_name, object_name, LEFT(statement, 4000)
    FROM sys.fn_get_audit_file(@caminho, DEFAULT, DEFAULT)
    WHERE event_time >= DATEADD(SECOND, -1, @marca) AND database_principal_name = N'sigp_operador_loc001';
    SELECT N'SQL Server Audit: o que o operador tentou (desde o início de T3)' AS trilha_nativa, acao, sucesso, quem, objeto, LEFT(REPLACE(REPLACE(comando, CHAR(13), N' '), CHAR(10), N' '), 140) AS comando FROM @a;
    INSERT @r SELECT N'T3a', N'Tentativa de gravar no LOC-002 (barrada pela RLS) fica registrada', N'registrada (operador, app.Notas)',
        CASE WHEN EXISTS (SELECT 1 FROM @a WHERE acao = N'IN' AND objeto = N'Notas' AND comando LIKE N'%LOC-002%') THEN N'registrada (operador, app.Notas)' ELSE N'não registrada' END;
    INSERT @r SELECT N'T3b', N'Tentativa de entrar no papel de auditor (negada) fica registrada', N'registrada, sucesso=0',
        CASE WHEN EXISTS (SELECT 1 FROM @a WHERE comando LIKE N'%ALTER ROLE%sigp_auditor%' AND sucesso = 0) THEN N'registrada, sucesso=0' ELSE N'não registrada' END;
END
ELSE
BEGIN
    INSERT @r VALUES (N'T3a', N'Tentativa de gravar no LOC-002 (barrada pela RLS) fica registrada', N'registrada (operador, app.Notas)', N'não registrada (sem SQL Server Audit)');
    INSERT @r VALUES (N'T3b', N'Tentativa de entrar no papel de auditor (negada) fica registrada', N'registrada, sucesso=0', N'não registrada (sem SQL Server Audit)');
END;

SELECT id, teste, esperado, obtido,
       CASE WHEN obtido = esperado OR (esperado = N'negado' AND obtido LIKE N'negado (%') THEN N'OK' ELSE N'FALHA' END AS veredito
FROM @r ORDER BY id;
SELECT CASE WHEN EXISTS (SELECT 1 FROM @r WHERE NOT (obtido = esperado OR (esperado = N'negado' AND obtido LIKE N'negado (%')))
            THEN N'REPROVADO' ELSE N'APROVADO' END AS resultado_final;
