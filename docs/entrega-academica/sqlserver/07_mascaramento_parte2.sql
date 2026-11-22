/* Parte 2 — Proteção de dado sensível: mascaramento dinâmico (Dynamic Data Masking) + UNMASK granular.
   Colunas sensíveis: app.Notas.chave_fiscal e app.Pagamentos.referencia.
   - sigp_api (aplicação) lê as linhas do seu escopo, mas a chave fiscal vem mascarada (não precisa dela).
   - sigp_fiscal (novo papel) tem UNMASK só nessas duas colunas: vê o valor real.
   - A IA nunca recebe a chave: ai.vw_contexto_minimo não tem a coluna e o usuário da IA não lê a tabela.
   O RLS continua valendo para todos. Limitação conhecida: mascaramento não é criptografia; quem tem SELECT
   pode inferir valores por filtros (WHERE chave_fiscal LIKE ...). Por isso a IA e os usuários sem necessidade
   não têm SELECT direto. Idempotente: pode ser executado de novo. Somente dados sintéticos. */
USE SIGpAcademic;
SET NOCOUNT ON;

IF NOT EXISTS (SELECT 1 FROM sys.masked_columns WHERE object_id = OBJECT_ID('app.Notas') AND name = 'chave_fiscal')
    ALTER TABLE app.Notas ALTER COLUMN chave_fiscal ADD MASKED WITH (FUNCTION = 'partial(4,"****************",4)');
IF NOT EXISTS (SELECT 1 FROM sys.masked_columns WHERE object_id = OBJECT_ID('app.Pagamentos') AND name = 'referencia')
    ALTER TABLE app.Pagamentos ALTER COLUMN referencia ADD MASKED WITH (FUNCTION = 'partial(3,"*****",0)');

IF DATABASE_PRINCIPAL_ID(N'sigp_fiscal') IS NULL CREATE ROLE sigp_fiscal;
GRANT SELECT ON OBJECT::app.Notas TO sigp_fiscal;
GRANT SELECT ON OBJECT::app.Pagamentos TO sigp_fiscal;
GRANT UNMASK ON app.Notas(chave_fiscal) TO sigp_fiscal;
GRANT UNMASK ON app.Pagamentos(referencia) TO sigp_fiscal;
IF DATABASE_PRINCIPAL_ID(N'sigp_fiscal_test') IS NULL CREATE USER sigp_fiscal_test WITHOUT LOGIN;
IF NOT EXISTS (SELECT 1 FROM sys.database_role_members WHERE role_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_fiscal')
               AND member_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_fiscal_test'))
    ALTER ROLE sigp_fiscal ADD MEMBER sigp_fiscal_test;
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_fiscal_test' AND local_id = N'LOC-001')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_fiscal_test', N'LOC-001');

PRINT '== Colunas mascaradas';
SELECT OBJECT_SCHEMA_NAME(c.object_id) + '.' + OBJECT_NAME(c.object_id) AS tabela, c.name AS coluna, c.masking_function
FROM sys.masked_columns AS c;

PRINT '== Teste 1: aplicação (sigp_api_test, sem UNMASK) -> chave mascarada';
EXECUTE AS USER = N'sigp_api_test';
SELECT TOP (3) USER_NAME() AS usuario, id, local_id, chave_fiscal FROM app.Notas ORDER BY id;
SELECT TOP (2) USER_NAME() AS usuario, nota_id, referencia FROM app.Pagamentos ORDER BY id;
REVERT;

PRINT '== Teste 2: fiscal (sigp_fiscal_test, com UNMASK; escopo só LOC-001) -> chave real';
EXECUTE AS USER = N'sigp_fiscal_test';
SELECT TOP (3) USER_NAME() AS usuario, id, local_id, chave_fiscal FROM app.Notas ORDER BY id;
SELECT USER_NAME() AS usuario, local_id, COUNT(*) AS linhas_visiveis FROM app.Notas GROUP BY local_id;
REVERT;

PRINT '== Teste 3: auditor (sigp_auditor_test) não lê a tabela de notas';
EXECUTE AS USER = N'sigp_auditor_test';
BEGIN TRY
    SELECT TOP (1) chave_fiscal FROM app.Notas;
END TRY
BEGIN CATCH
    PRINT 'NEGADO: ' + ERROR_MESSAGE();
END CATCH;
REVERT;

PRINT '== Teste 4: a view usada pela IA não expõe a chave fiscal';
SELECT COUNT(*) AS colunas_chave_na_view_da_ia
FROM sys.columns WHERE object_id = OBJECT_ID('ai.vw_contexto_minimo') AND name LIKE '%chave%';
