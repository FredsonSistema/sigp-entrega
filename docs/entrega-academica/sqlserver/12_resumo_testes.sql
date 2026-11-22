/* Testes do resumo diário (app.ResumoDiario), a desnormalização da consulta 1.
   1. Consistência: inserir, alterar valor, mudar o dia e apagar notas; o resumo tem de ficar igual ao total recalculado.
   2. Segurança: o operador do LOC-001 só lê o resumo do LOC-001; a IA não lê o resumo; a API não grava nele.
   3. Custo: tempo de gravação com e sem o gatilho (lote de 1.000 notas e 200 notas uma a uma).
   Tudo em transação com ROLLBACK: o banco não muda.
   Uso (raiz do projeto, senha só em variável de ambiente):
     sqlcmd -S 127.0.0.1,14333 -U sa -d SIGpAcademic -C -I -W -s "|" -f 65001 -i docs/entrega-academica/sqlserver/12_resumo_testes.sql */
USE SIGpAcademic;
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @u NVARCHAR(8) = LEFT(CONVERT(NVARCHAR(36), NEWID()), 8);
DECLARE @r TABLE (teste NVARCHAR(90), esperado NVARCHAR(40), obtido NVARCHAR(60));

/* ------------------------------------------------------------ 1. consistência */
BEGIN TRANSACTION;
EXECUTE AS USER = N'sigp_operador_loc001';
-- 50 notas novas no LOC-001, em 10 dias (um deles sem nenhuma nota até agora)
;WITH s(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM s WHERE n < 50)
INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
SELECT N'LOC-001', N'PROV-001', CONCAT(N'RES-', @u, N'-', n), CONCAT(N'R', n), N'A', 10.00 + n,
       DATEADD(DAY, n % 10, CONVERT(date, '20270115')), CONVERT(date, '20270215'), N'teste', N'PENDENTE'
FROM s OPTION (MAXRECURSION 50);
-- valor alterado em 10 notas antigas e dia trocado em 5
UPDATE TOP (10) app.Notas SET valor_total = valor_total + 1.25 WHERE local_id = N'LOC-001' AND chave_fiscal NOT LIKE N'RES-%';
UPDATE TOP (5) app.Notas SET data_emissao = DATEADD(DAY, 3, data_emissao) WHERE local_id = N'LOC-001' AND chave_fiscal LIKE N'RES-%';
REVERT;
-- exclusão (a API tem DENY DELETE; quem apaga é o dono)
DELETE TOP (7) FROM app.Notas WHERE chave_fiscal LIKE CONCAT(N'RES-', @u, N'-%');

DECLARE @dif INT = (
    SELECT COUNT(*) FROM (
        (SELECT data_emissao, local_id, provedor_id, COUNT_BIG(*) AS q, SUM(valor_total) AS t FROM app.Notas GROUP BY data_emissao, local_id, provedor_id
         EXCEPT SELECT data_emissao, local_id, provedor_id, quantidade, total FROM app.ResumoDiario)
        UNION ALL
        (SELECT data_emissao, local_id, provedor_id, quantidade, total FROM app.ResumoDiario
         EXCEPT SELECT data_emissao, local_id, provedor_id, COUNT_BIG(*), SUM(valor_total) FROM app.Notas GROUP BY data_emissao, local_id, provedor_id)
    ) AS x);
INSERT @r VALUES (N'Resumo igual ao total recalculado depois de 50 INSERT, 15 UPDATE e 7 DELETE', N'0 linhas diferentes', CONCAT(@dif, N' linhas diferentes'));
ROLLBACK TRANSACTION;

/* ------------------------------------------------------------ 2. segurança */
DECLARE @locais NVARCHAR(200);
EXECUTE AS USER = N'sigp_operador_loc001';
SELECT @locais = STRING_AGG(local_id, N',') WITHIN GROUP (ORDER BY local_id) FROM (SELECT DISTINCT local_id FROM app.ResumoDiario) AS d;
REVERT;
INSERT @r VALUES (N'Operador do LOC-001 lê o resumo (só o próprio local)', N'LOC-001', COALESCE(@locais, N'nada'));

EXECUTE AS USER = N'sigp_api_test';
SELECT @locais = STRING_AGG(local_id, N',') WITHIN GROUP (ORDER BY local_id) FROM (SELECT DISTINCT local_id FROM app.ResumoDiario) AS d;
REVERT;
INSERT @r VALUES (N'API com escopo nos três locais lê o resumo', N'LOC-001,LOC-002,LOC-003', COALESCE(@locais, N'nada'));

EXECUTE AS USER = N'sigp_ia_loc001';
BEGIN TRY
    EXEC sys.sp_executesql N'SELECT TOP (1) * FROM app.ResumoDiario;';
    INSERT @r VALUES (N'IA lê o resumo direto', N'negado', N'PERMITIDO');
END TRY
BEGIN CATCH INSERT @r VALUES (N'IA lê o resumo direto', N'negado', CONCAT(N'negado (', ERROR_NUMBER(), N')')); END CATCH;
REVERT;

-- Em transação (se passasse, o ROLLBACK desfaria). A negação inutiliza a transação: só guarda o erro e anota depois.
DECLARE @erro INT = NULL;
BEGIN TRANSACTION;
EXECUTE AS USER = N'sigp_operador_loc001';
BEGIN TRY
    EXEC sys.sp_executesql N'UPDATE app.ResumoDiario SET total = total + 1000 WHERE local_id = N''LOC-001'';';
END TRY
BEGIN CATCH SET @erro = ERROR_NUMBER(); END CATCH;
IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
REVERT;
INSERT @r VALUES (N'Operador altera o resumo direto (forjar total)', N'negado',
                  CASE WHEN @erro IS NULL THEN N'PERMITIDO' ELSE CONCAT(N'negado (', @erro, N')') END);

/* ------------------------------------------------------------ 3. custo de gravação */
DECLARE @t TABLE (modo NVARCHAR(10), tipo NVARCHAR(10), rodada INT, micros BIGINT);
DECLARE @k INT = 0, @j INT, @t0 DATETIME2(7), @modo NVARCHAR(10);
WHILE @k < 10
BEGIN
    -- alterna a ordem (com/sem) a cada rodada para a carga da máquina pesar igual
    DECLARE @m INT = 0;
    WHILE @m < 2
    BEGIN
        SET @modo = CASE WHEN (@k + @m) % 2 = 0 THEN N'com' ELSE N'sem' END;
        BEGIN TRANSACTION;
        IF @modo = N'sem' DISABLE TRIGGER app.trg_Notas_ResumoDiario ON app.Notas;
        -- lote: 1.000 notas numa instrução
        SET @t0 = SYSDATETIME();
        ;WITH s(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM s WHERE n < 1000)
        INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
        SELECT CASE n % 3 WHEN 0 THEN N'LOC-001' WHEN 1 THEN N'LOC-002' ELSE N'LOC-003' END,
               CASE n % 3 WHEN 0 THEN N'PROV-001' WHEN 1 THEN N'PROV-002' ELSE N'PROV-003' END,
               CONCAT(N'CUSTO-', @u, N'-', @k, @m, N'-', n), CONCAT(N'C', n), N'A', 50.00 + n % 7,
               DATEADD(DAY, n % 60, CONVERT(date, '20260801')), CONVERT(date, '20261001'), N'teste', N'PENDENTE'
        FROM s OPTION (MAXRECURSION 1000);
        INSERT @t VALUES (@modo, N'lote', @k, DATEDIFF_BIG(MICROSECOND, @t0, SYSDATETIME()));
        -- uma a uma: 200 notas, como a API grava
        SET @j = 0;
        SET @t0 = SYSDATETIME();
        WHILE @j < 200
        BEGIN
            INSERT INTO app.Notas (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
            VALUES (N'LOC-001', N'PROV-001', CONCAT(N'CUSTO1-', @u, N'-', @k, @m, N'-', @j), CONCAT(N'U', @j), N'A', 80.00,
                    DATEADD(DAY, @j % 30, CONVERT(date, '20260901')), CONVERT(date, '20261001'), N'teste', N'PENDENTE');
            SET @j += 1;
        END;
        INSERT @t VALUES (@modo, N'uma_a_uma', @k, DATEDIFF_BIG(MICROSECOND, @t0, SYSDATETIME()));
        ROLLBACK TRANSACTION;
        SET @m += 1;
    END;
    SET @k += 1;
END;

SELECT teste, esperado, obtido,
       CASE WHEN obtido = esperado OR (esperado = N'negado' AND obtido LIKE N'negado%') THEN N'OK' ELSE N'FALHA' END AS veredito
FROM @r;

SELECT DISTINCT tipo, modo,
    COUNT(*) OVER (PARTITION BY tipo, modo) AS rodadas,
    CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY micros) OVER (PARTITION BY tipo, modo) / 1000.0 AS DECIMAL(10,2)) AS mediana_ms,
    CAST(CASE tipo WHEN N'lote' THEN PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY micros) OVER (PARTITION BY tipo, modo) / 1000.0
                   ELSE PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY micros) OVER (PARTITION BY tipo, modo) / 200.0 END AS DECIMAL(10,1)) AS por_nota_us
FROM @t
ORDER BY tipo, modo;

SELECT CASE WHEN EXISTS (SELECT 1 FROM @r WHERE NOT (obtido = esperado OR (esperado = N'negado' AND obtido LIKE N'negado%')))
            THEN N'REPROVADO' ELSE N'APROVADO' END AS resultado_final;
