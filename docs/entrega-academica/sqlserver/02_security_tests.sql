USE SIGpAcademic;
GO

SET NOCOUNT ON;

DECLARE @allowed TABLE (
    nota_id BIGINT,
    local_id NVARCHAR(40),
    provider_id NVARCHAR(40),
    provedor NVARCHAR(80),
    tipo_local NVARCHAR(20),
    descricao NVARCHAR(160),
    valor DECIMAL(12,2),
    classificacao NVARCHAR(20),
    vencimento DATE,
    status NVARCHAR(24)
);
DECLARE @denied_direct_read BIT = 0;
DECLARE @denied_cross_local BIT = 0;
DECLARE @denied_api_delete BIT = 0;
DECLARE @denied_unassigned_role BIT = 0;
DECLARE @correlation_id UNIQUEIDENTIFIER = NEWID();

EXECUTE AS USER = N'sigp_ia_loc001';
BEGIN TRY
    INSERT INTO @allowed
    EXEC ai.usp_get_context
        @local_id = N'LOC-001',
        @correlation_id = @correlation_id,
        @provider_id = N'PROV-001',
        @take = 50,
        @requested_by = N'operador-sintetico';

    IF NOT EXISTS (SELECT 1 FROM @allowed)
        THROW 51010, 'Esperava pelo menos um registro permitido para LOC-001.', 1;
    IF EXISTS (SELECT 1 FROM @allowed WHERE local_id <> N'LOC-001')
        THROW 51011, 'O filtro RLS retornou dados de outro local.', 1;
    IF EXISTS (SELECT 1 FROM @allowed WHERE provider_id <> N'PROV-001')
        THROW 51016, 'O filtro por provedor retornou dados fora do escopo da consulta.', 1;

    EXEC ai.usp_log_sources
        @local_id = N'LOC-001',
        @correlation_id = @correlation_id,
        @source_ids = N'DOC-ALFA-01,DOC-POLITICA-02',
        @requested_by = N'operador-sintetico';
END TRY
BEGIN CATCH
    REVERT;
    THROW;
END CATCH;

BEGIN TRY
    EXEC sys.sp_executesql N'SELECT TOP (1) * FROM app.Notas;';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() IN (229, 230) SET @denied_direct_read = 1;
END CATCH;

IF @denied_direct_read = 0
BEGIN
    REVERT;
    THROW 51012, 'A leitura direta da tabela app.Notas deveria ser negada à IA.', 1;
END;

BEGIN TRY
    EXEC ai.usp_get_context @local_id = N'LOC-002', @correlation_id = @correlation_id;
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() = 51001 SET @denied_cross_local = 1;
END CATCH;
REVERT;

IF @denied_cross_local = 0
    THROW 51013, 'A consulta cruzada de local deveria ser negada.', 1;

EXECUTE AS USER = N'sigp_api_test';
BEGIN TRANSACTION;
BEGIN TRY
    EXEC sys.sp_executesql N'DELETE TOP (1) FROM app.Notas;';
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() IN (229, 230) SET @denied_api_delete = 1;
END CATCH;
ROLLBACK TRANSACTION;
REVERT;

IF @denied_api_delete = 0
    THROW 51014, 'DELETE deveria ser negado ao papel da API.', 1;

EXECUTE AS USER = N'sigp_denied_test';
BEGIN TRY
    EXEC ai.usp_get_context @local_id = N'LOC-001', @correlation_id = @correlation_id;
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() IN (229, 230) SET @denied_unassigned_role = 1;
END CATCH;
REVERT;

IF @denied_unassigned_role = 0
    THROW 51015, 'O principal sem papel não deveria executar o procedimento da IA.', 1;

EXECUTE AS USER = N'sigp_auditor_test';
SELECT ator, acao, objeto, correlation_id, detalhe_redigido, criado_em
FROM audit.Eventos
WHERE correlation_id = @correlation_id
  AND acao IN (N'AI_CONTEXT_READ', N'AI_CONTEXT_DENIED', N'AI_RAG_SOURCES')
ORDER BY criado_em;
REVERT;

SELECT
    N'PASS' AS resultado,
    (SELECT COUNT_BIG(*) FROM @allowed) AS registros_loc001_permitidos,
    @denied_direct_read AS leitura_direta_negada,
    @denied_cross_local AS acesso_outro_local_negado,
    @denied_api_delete AS delete_api_negado,
    @denied_unassigned_role AS principal_sem_role_negado,
    @correlation_id AS correlation_id;
GO
