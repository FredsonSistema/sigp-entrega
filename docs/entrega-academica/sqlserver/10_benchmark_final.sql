/* Entrega final — Otimização: as duas consultas lentas, medidas em cada configuração.
   Consulta 1: total faturado por local, provedor e mês nos últimos 12 meses (soma ~47 mil das 100.020 notas).
   Consulta 2: as 500 notas pendentes vencidas mais antigas sem conciliação concluída.
     A = linha de base (só chaves primárias; índices candidatos desabilitados)
     B = índices candidatos de 02/11 (01_schema_seed.sql)
     C = índices ajustados: cobertura em data_emissao (consulta 1) e filtrados (consulta 2)
     D = consulta 1 sobre o resumo diário app.ResumoDiario (desnormalização mantida por gatilho)
   Antes de medir, confere que a consulta 1 no resumo devolve exatamente as mesmas linhas que nas notas.
   Cada consulta: 1 execução de aquecimento + @repeticoes medidas. Termina na configuração C (índices ajustados).
   Somente dados sintéticos. Uso: chamado por benchmark-final.ps1 (ou sqlcmd ... -I -i 10_benchmark_final.sql). */
USE SIGpAcademic;
SET NOCOUNT ON;
SET XACT_ABORT ON;
DECLARE @repeticoes INT = 30;

-- Mesma resposta: consulta 1 nas notas x no resumo (as duas diferenças precisam ser vazias).
DECLARE @inicio DATE = DATEADD(MONTH, -12, CONVERT(date, GETDATE()));
DECLARE @diferencas INT = (
    SELECT COUNT(*) FROM (
        (SELECT n.local_id, p.nome AS provedor, YEAR(n.data_emissao) AS ano, MONTH(n.data_emissao) AS mes, COUNT_BIG(*) AS q, SUM(n.valor_total) AS t
         FROM app.Notas AS n JOIN app.Provedores AS p ON p.id = n.provedor_id
         WHERE n.data_emissao >= @inicio GROUP BY n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao)
         EXCEPT
         SELECT r.local_id, p.nome, YEAR(r.data_emissao), MONTH(r.data_emissao), SUM(r.quantidade), SUM(r.total)
         FROM app.ResumoDiario AS r JOIN app.Provedores AS p ON p.id = r.provedor_id
         WHERE r.data_emissao >= @inicio GROUP BY r.local_id, p.nome, YEAR(r.data_emissao), MONTH(r.data_emissao))
        UNION ALL
        (SELECT r.local_id, p.nome, YEAR(r.data_emissao), MONTH(r.data_emissao), SUM(r.quantidade), SUM(r.total)
         FROM app.ResumoDiario AS r JOIN app.Provedores AS p ON p.id = r.provedor_id
         WHERE r.data_emissao >= @inicio GROUP BY r.local_id, p.nome, YEAR(r.data_emissao), MONTH(r.data_emissao)
         EXCEPT
         SELECT n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao), COUNT_BIG(*), SUM(n.valor_total)
         FROM app.Notas AS n JOIN app.Provedores AS p ON p.id = n.provedor_id
         WHERE n.data_emissao >= @inicio GROUP BY n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao))
    ) AS x);
SELECT N'mesma_resposta_consulta1_notas_x_resumo' AS verificacao, @diferencas AS linhas_diferentes,
       (SELECT COUNT(*) FROM (SELECT DISTINCT local_id, provedor_id, YEAR(data_emissao) a, MONTH(data_emissao) m FROM app.Notas WHERE data_emissao >= @inicio) AS g) AS linhas_do_resultado;
IF @diferencas <> 0
    THROW 51080, 'A consulta 1 no resumo não devolve o mesmo que nas notas: o benchmark não foi medido.', 1;

IF OBJECT_ID('tempdb..#tempos') IS NOT NULL DROP TABLE #tempos;
CREATE TABLE #tempos (configuracao CHAR(1), consulta TINYINT, execucao INT, micros BIGINT);
IF OBJECT_ID('tempdb..#q1') IS NOT NULL DROP TABLE #q1;
CREATE TABLE #q1 (local_id NVARCHAR(40), provedor NVARCHAR(80), ano INT, mes INT, quantidade BIGINT, total DECIMAL(18,2));
IF OBJECT_ID('tempdb..#q2') IS NOT NULL DROP TABLE #q2;
CREATE TABLE #q2 (id BIGINT, local_id NVARCHAR(40), provedor_id NVARCHAR(40), valor_total DECIMAL(12,2), vencimento DATE, status NVARCHAR(24));
DECLARE @cfg CHAR(1), @i INT, @t0 DATETIME2(7);
DECLARE configs CURSOR LOCAL FAST_FORWARD FOR SELECT c FROM (VALUES ('A'), ('B'), ('C'), ('D')) AS v(c);
OPEN configs;
FETCH NEXT FROM configs INTO @cfg;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF @cfg = 'A'
    BEGIN
        ALTER INDEX IX_Notas_Local_Vencimento_Status ON app.Notas DISABLE;
        ALTER INDEX IX_Notas_Provedor_Emissao ON app.Notas DISABLE;
        ALTER INDEX IX_Conciliacoes_Nota_Status ON app.Conciliacoes DISABLE;
        IF INDEXPROPERTY(OBJECT_ID('app.Notas'), 'IX_Notas_Emissao_Cobertura', 'IndexID') IS NOT NULL DROP INDEX IX_Notas_Emissao_Cobertura ON app.Notas;
        IF INDEXPROPERTY(OBJECT_ID('app.Notas'), 'IX_Notas_Pendentes_Vencimento', 'IndexID') IS NOT NULL DROP INDEX IX_Notas_Pendentes_Vencimento ON app.Notas;
        IF INDEXPROPERTY(OBJECT_ID('app.Conciliacoes'), 'IX_Conciliacoes_Concluidas', 'IndexID') IS NOT NULL DROP INDEX IX_Conciliacoes_Concluidas ON app.Conciliacoes;
    END;
    IF @cfg = 'B'
    BEGIN
        ALTER INDEX IX_Notas_Local_Vencimento_Status ON app.Notas REBUILD;
        ALTER INDEX IX_Notas_Provedor_Emissao ON app.Notas REBUILD;
        ALTER INDEX IX_Conciliacoes_Nota_Status ON app.Conciliacoes REBUILD;
    END;
    IF @cfg = 'C'
    BEGIN
        CREATE INDEX IX_Notas_Emissao_Cobertura ON app.Notas (data_emissao) INCLUDE (local_id, provedor_id, valor_total);
        CREATE INDEX IX_Notas_Pendentes_Vencimento ON app.Notas (vencimento, id)
            INCLUDE (local_id, provedor_id, valor_total, status) WHERE status = N'PENDENTE';
        CREATE INDEX IX_Conciliacoes_Concluidas ON app.Conciliacoes (nota_id) WHERE status = N'CONCILIADA';
    END;
    UPDATE STATISTICS app.Notas;
    UPDATE STATISTICS app.Conciliacoes;
    UPDATE STATISTICS app.ResumoDiario;
    SET @i = 0;
    WHILE @i <= @repeticoes
    BEGIN
        TRUNCATE TABLE #q1;
        SET @t0 = SYSDATETIME();
        IF @cfg = 'D'
            INSERT INTO #q1
            SELECT r.local_id, p.nome, YEAR(r.data_emissao), MONTH(r.data_emissao), SUM(r.quantidade), SUM(r.total)
            FROM app.ResumoDiario AS r
            JOIN app.Provedores AS p ON p.id = r.provedor_id
            WHERE r.data_emissao >= DATEADD(MONTH, -12, CONVERT(date, GETDATE()))
            GROUP BY r.local_id, p.nome, YEAR(r.data_emissao), MONTH(r.data_emissao)
            OPTION (RECOMPILE);
        ELSE
            INSERT INTO #q1
            SELECT n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao), COUNT_BIG(*), SUM(n.valor_total)
            FROM app.Notas AS n
            JOIN app.Provedores AS p ON p.id = n.provedor_id
            WHERE n.data_emissao >= DATEADD(MONTH, -12, CONVERT(date, GETDATE()))
            GROUP BY n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao)
            OPTION (RECOMPILE);
        IF @i > 0 INSERT INTO #tempos VALUES (@cfg, 1, @i, DATEDIFF_BIG(MICROSECOND, @t0, SYSDATETIME()));
        IF @cfg <> 'D'
        BEGIN
            TRUNCATE TABLE #q2;
            SET @t0 = SYSDATETIME();
            INSERT INTO #q2
            SELECT TOP (500) n.id, n.local_id, n.provedor_id, n.valor_total, n.vencimento, n.status
            FROM app.Notas AS n
            WHERE n.status = N'PENDENTE'
              AND n.vencimento < CONVERT(date, GETDATE())
              AND NOT EXISTS (SELECT 1 FROM app.Conciliacoes AS c WHERE c.nota_id = n.id AND c.status = N'CONCILIADA')
            ORDER BY n.vencimento, n.id
            OPTION (RECOMPILE);
            IF @i > 0 INSERT INTO #tempos VALUES (@cfg, 2, @i, DATEDIFF_BIG(MICROSECOND, @t0, SYSDATETIME()));
        END;
        SET @i += 1;
    END;
    FETCH NEXT FROM configs INTO @cfg;
END;
CLOSE configs;
DEALLOCATE configs;

SELECT DISTINCT configuracao, consulta,
    COUNT(*) OVER (PARTITION BY configuracao, consulta) AS execucoes,
    CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY micros) OVER (PARTITION BY configuracao, consulta) / 1000.0 AS DECIMAL(10,3)) AS mediana_ms,
    CAST(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY micros) OVER (PARTITION BY configuracao, consulta) / 1000.0 AS DECIMAL(10,3)) AS p95_ms,
    CAST(AVG(micros * 1.0) OVER (PARTITION BY configuracao, consulta) / 1000.0 AS DECIMAL(10,3)) AS media_ms
FROM #tempos
ORDER BY consulta, configuracao;
