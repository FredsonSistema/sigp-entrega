/* Ataque de escalonamento de privilégio (vertical e horizontal) contra o SQL Server acadêmico.

   Fase 1 (antes): reproduz a falha encontrada. Dentro de uma transação, a política de RLS volta a ter só o
   predicado FILTER (como estava até 20/11/2026) e o operador regional, com escopo só no LOC-001, tenta gravar no
   LOC-002. Esperado: o ataque PASSA (falha reproduzida). O ROLLBACK devolve a política corrigida.
   Fase 2 (depois): os mesmos ataques e outros seis contra a política corrigida (FILTER + BLOCK). Esperado: todos
   BARRADOS, e o controle positivo (gravar no próprio local) continua PERMITIDO.

   Só os erros de permissão esperados contam como BARRADO: 229/230 (sem permissão), 15151 (papel), 15517
   (personificação), 33504 (predicado BLOCK da RLS), 37359 (a trilha é ledger "somente inclusão": ninguém altera nem
   apaga, nem o sa; a recusa vem antes da checagem de permissão) e 51001 (escopo negado pelo procedimento). Qualquer outro erro
   reprova o teste, para não haver falso positivo. Nada muda no banco: tudo termina em ROLLBACK.

   Uso (raiz do projeto, senha só em variável de ambiente):
     $env:SQLCMDPASSWORD = '<MSSQL_SA_PASSWORD do .env.academic>'
     sqlcmd -S 127.0.0.1,14333 -U sa -d SIGpAcademic -C -I -W -s "|" -f 65001 -i docs/entrega-academica/sqlserver/08_ataque_escalonamento.sql
   (-I liga QUOTED_IDENTIFIER, exigido pelos índices filtrados das tabelas.) */
USE SIGpAcademic;
SET NOCOUNT ON;

DECLARE @r TABLE (fase NVARCHAR(7), id NVARCHAR(4), tipo NVARCHAR(12), quem SYSNAME, ataque NVARCHAR(90), esperado NVARCHAR(9), obtido NVARCHAR(40));
DECLARE @n INT, @cid UNIQUEIDENTIFIER = NEWID(), @u NVARCHAR(12) = LEFT(CONVERT(NVARCHAR(36), NEWID()), 8);

IF DATABASE_PRINCIPAL_ID(N'sigp_operador_loc001') IS NULL
    THROW 51090, 'Falta o usuário de teste sigp_operador_loc001: rode antes o 01_schema_seed.sql atualizado.', 1;
IF (SELECT COUNT(*) FROM security.LocalScope WHERE principal_name = N'sigp_operador_loc001') <> 1
   OR NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_operador_loc001' AND local_id = N'LOC-001')
    THROW 51091, 'O operador de teste precisa ter escopo só no LOC-001.', 1;
IF NOT EXISTS (SELECT 1 FROM sys.security_predicates WHERE object_id = OBJECT_ID(N'security.LocalScopePolicy') AND predicate_type_desc = N'BLOCK')
    THROW 51092, 'A política security.LocalScopePolicy ainda não tem os predicados BLOCK: rode o 01_schema_seed.sql atualizado.', 1;

/* ------------------------------------------------------------------ Fase 1: reprodução da falha (antes) */
BEGIN TRANSACTION;
ALTER SECURITY POLICY security.LocalScopePolicy
    DROP BLOCK PREDICATE ON app.Notas AFTER INSERT,
    DROP BLOCK PREDICATE ON app.Notas BEFORE UPDATE,
    DROP BLOCK PREDICATE ON app.Notas AFTER UPDATE,
    DROP BLOCK PREDICATE ON app.Notas BEFORE DELETE;

EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
    VALUES (N'LOC-002', N'PROV-002', CONCAT(N'ATAQUE-', @u), CONCAT(N'ATQ-', @u), N'A', 1.00, '20261001', '20261101', N'teste', N'RECEBIDA');
    INSERT @r VALUES (N'antes', N'E6', N'horizontal', USER_NAME(), N'Nota gravada em local fora do escopo (INSERT no LOC-002)', N'PASSA', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'antes', N'E6', N'horizontal', USER_NAME(), N'Nota gravada em local fora do escopo (INSERT no LOC-002)', N'PASSA', CONCAT(N'erro ', ERROR_NUMBER())); END CATCH;
BEGIN TRY
    UPDATE TOP (1) app.Notas SET local_id = N'LOC-002' WHERE local_id = N'LOC-001';
    SET @n = @@ROWCOUNT;
    INSERT @r VALUES (N'antes', N'E7', N'horizontal', USER_NAME(), N'Nota movida para outro local (UPDATE local_id)', N'PASSA', CASE WHEN @n > 0 THEN N'PERMITIDO' ELSE N'0 linhas' END);
END TRY
BEGIN CATCH INSERT @r VALUES (N'antes', N'E7', N'horizontal', USER_NAME(), N'Nota movida para outro local (UPDATE local_id)', N'PASSA', CONCAT(N'erro ', ERROR_NUMBER())); END CATCH;
REVERT;
ROLLBACK TRANSACTION;

/* ------------------------------------------------------------------ Fase 2: ataques contra a correção (depois) */
-- E2 fica fora da transação: o erro 15517 (personificação negada) inutiliza a transação aberta.
EXECUTE AS USER = N'sigp_ia_loc001';
BEGIN TRY
    EXECUTE AS USER = N'sigp_ia_loc002';
    INSERT @r VALUES (N'depois', N'E2', N'horizontal', N'sigp_ia_loc001', N'IA personifica a identidade do LOC-002 (EXECUTE AS)', N'BARRADO', N'PERMITIDO');
    REVERT;
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'E2', N'horizontal', USER_NAME(), N'IA personifica a identidade do LOC-002 (EXECUTE AS)', N'BARRADO',
    CASE WHEN ERROR_NUMBER() IN (229, 230, 15151, 15517, 33504, 37359, 51001) THEN CONCAT(N'BARRADO (erro ', ERROR_NUMBER(), N')') ELSE CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER()) END); END CATCH;
REVERT;

BEGIN TRANSACTION;

-- E1 horizontal: a IA grava o próprio escopo para enxergar o LOC-002
EXECUTE AS USER = N'sigp_ia_loc001';
BEGIN TRY
    EXEC sys.sp_executesql N'INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N''sigp_ia_loc001'', N''LOC-002'');';
    INSERT @r VALUES (N'depois', N'E1', N'horizontal', USER_NAME(), N'IA grava o próprio escopo (security.LocalScope)', N'BARRADO', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'E1', N'horizontal', USER_NAME(), N'IA grava o próprio escopo (security.LocalScope)', N'BARRADO',
    CASE WHEN ERROR_NUMBER() IN (229, 230, 15151, 15517, 33504, 37359, 51001) THEN CONCAT(N'BARRADO (erro ', ERROR_NUMBER(), N')') ELSE CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER()) END); END CATCH;
REVERT;

-- E3 vertical: o operador se coloca no papel de auditor
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    EXEC sys.sp_executesql N'ALTER ROLE sigp_auditor ADD MEMBER sigp_operador_loc001;';
    INSERT @r VALUES (N'depois', N'E3', N'vertical', USER_NAME(), N'Operador entra no papel sigp_auditor (ALTER ROLE)', N'BARRADO', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'E3', N'vertical', USER_NAME(), N'Operador entra no papel sigp_auditor (ALTER ROLE)', N'BARRADO',
    CASE WHEN ERROR_NUMBER() IN (229, 230, 15151, 15517, 33504, 37359, 51001) THEN CONCAT(N'BARRADO (erro ', ERROR_NUMBER(), N')') ELSE CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER()) END); END CATCH;
REVERT;

-- E4 vertical: apagar a trilha de auditoria
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    EXEC sys.sp_executesql N'DELETE FROM audit.Eventos;';
    INSERT @r VALUES (N'depois', N'E4', N'vertical', USER_NAME(), N'Operador apaga a trilha de auditoria (DELETE)', N'BARRADO', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'E4', N'vertical', USER_NAME(), N'Operador apaga a trilha de auditoria (DELETE)', N'BARRADO',
    CASE WHEN ERROR_NUMBER() IN (229, 230, 15151, 15517, 33504, 37359, 51001) THEN CONCAT(N'BARRADO (erro ', ERROR_NUMBER(), N')') ELSE CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER()) END); END CATCH;
REVERT;

-- E5 vertical: reescrever a trilha de auditoria
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    EXEC sys.sp_executesql N'UPDATE audit.Eventos SET ator = N''ninguem'';';
    INSERT @r VALUES (N'depois', N'E5', N'vertical', USER_NAME(), N'Operador reescreve a trilha de auditoria (UPDATE)', N'BARRADO', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'E5', N'vertical', USER_NAME(), N'Operador reescreve a trilha de auditoria (UPDATE)', N'BARRADO',
    CASE WHEN ERROR_NUMBER() IN (229, 230, 15151, 15517, 33504, 37359, 51001) THEN CONCAT(N'BARRADO (erro ', ERROR_NUMBER(), N')') ELSE CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER()) END); END CATCH;
REVERT;

-- E6 horizontal: gravar nota no LOC-002 tendo escopo só no LOC-001 (a falha da fase 1)
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
    VALUES (N'LOC-002', N'PROV-002', CONCAT(N'ATAQUE-', @u), CONCAT(N'ATQ-', @u), N'A', 1.00, '20261001', '20261101', N'teste', N'RECEBIDA');
    INSERT @r VALUES (N'depois', N'E6', N'horizontal', USER_NAME(), N'Nota gravada em local fora do escopo (INSERT no LOC-002)', N'BARRADO', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'E6', N'horizontal', USER_NAME(), N'Nota gravada em local fora do escopo (INSERT no LOC-002)', N'BARRADO',
    CASE WHEN ERROR_NUMBER() IN (229, 230, 15151, 15517, 33504, 37359, 51001) THEN CONCAT(N'BARRADO (erro ', ERROR_NUMBER(), N')') ELSE CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER()) END); END CATCH;
REVERT;

-- E7 horizontal: mover uma nota visível do LOC-001 para o LOC-002 (a falha da fase 1)
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    UPDATE TOP (1) app.Notas SET local_id = N'LOC-002' WHERE local_id = N'LOC-001';
    SET @n = @@ROWCOUNT;
    INSERT @r VALUES (N'depois', N'E7', N'horizontal', USER_NAME(), N'Nota movida para outro local (UPDATE local_id)', N'BARRADO', CASE WHEN @n > 0 THEN N'PERMITIDO' ELSE N'0 linhas' END);
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'E7', N'horizontal', USER_NAME(), N'Nota movida para outro local (UPDATE local_id)', N'BARRADO',
    CASE WHEN ERROR_NUMBER() IN (229, 230, 15151, 15517, 33504, 37359, 51001) THEN CONCAT(N'BARRADO (erro ', ERROR_NUMBER(), N')') ELSE CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER()) END); END CATCH;
REVERT;

-- E8 injeção SQL no parâmetro do procedimento da IA
EXECUTE AS USER = N'sigp_ia_loc001';
BEGIN TRY
    EXEC ai.usp_get_context @local_id = N'LOC-001'' OR 1=1 --', @correlation_id = @cid;
    INSERT @r VALUES (N'depois', N'E8', N'injeção', USER_NAME(), N'SQL Injection em @local_id do ai.usp_get_context', N'BARRADO', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'E8', N'injeção', USER_NAME(), N'SQL Injection em @local_id do ai.usp_get_context', N'BARRADO',
    CASE WHEN ERROR_NUMBER() IN (229, 230, 15151, 15517, 33504, 37359, 51001) THEN CONCAT(N'BARRADO (erro ', ERROR_NUMBER(), N')') ELSE CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER()) END); END CATCH;
REVERT;

-- C1 controle positivo: gravar e atualizar nota no próprio local (LOC-001) continua funcionando
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
    VALUES (N'LOC-001', N'PROV-001', CONCAT(N'LEGIT-', @u), CONCAT(N'LEG-', @u), N'A', 1.00, '20261001', '20261101', N'teste', N'RECEBIDA');
    UPDATE app.Notas SET valor_total = 2.00 WHERE chave_fiscal = CONCAT(N'LEGIT-', @u);
    INSERT @r VALUES (N'depois', N'C1', N'controle', USER_NAME(), N'Gravar e atualizar nota no PRÓPRIO local (LOC-001)', N'PERMITIDO', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'depois', N'C1', N'controle', USER_NAME(), N'Gravar e atualizar nota no PRÓPRIO local (LOC-001)', N'PERMITIDO', CONCAT(N'ERRO INESPERADO ', ERROR_NUMBER())); END CATCH;
REVERT;

ROLLBACK TRANSACTION;

SELECT fase, id, tipo, quem, ataque, esperado, obtido,
       CASE WHEN (esperado = N'BARRADO' AND obtido LIKE N'BARRADO%')
              OR (esperado IN (N'PERMITIDO', N'PASSA') AND obtido = N'PERMITIDO')
            THEN N'OK' ELSE N'FALHA' END AS veredito
FROM @r ORDER BY CASE fase WHEN N'antes' THEN 0 ELSE 1 END, id;

SELECT CASE WHEN EXISTS (
    SELECT 1 FROM @r WHERE NOT ((esperado = N'BARRADO' AND obtido LIKE N'BARRADO%') OR (esperado IN (N'PERMITIDO', N'PASSA') AND obtido = N'PERMITIDO'))
) THEN N'REPROVADO' ELSE N'APROVADO: falha reproduzida na fase 1; na fase 2 todos os ataques barrados e o controle positivo funciona' END AS resultado_final;
