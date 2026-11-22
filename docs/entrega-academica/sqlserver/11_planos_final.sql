/* Entrega final — leituras lógicas e plano real das consultas numa configuração (mesmas de 10_benchmark_final.sql).
   Variável sqlcmd: CFG = A | B | C | D. Em D só roda a consulta 1 sobre o resumo diário (os índices ficam como em C).
   Uso: sqlcmd ... -I -v CFG=A -i 11_planos_final.sql  (chamado por benchmark-final.ps1). */
USE SIGpAcademic;
SET NOCOUNT ON;
DECLARE @cfg CHAR(1) = '$(CFG)';
IF @cfg = 'A'
BEGIN
    ALTER INDEX IX_Notas_Local_Vencimento_Status ON app.Notas DISABLE;
    ALTER INDEX IX_Notas_Provedor_Emissao ON app.Notas DISABLE;
    ALTER INDEX IX_Conciliacoes_Nota_Status ON app.Conciliacoes DISABLE;
    IF INDEXPROPERTY(OBJECT_ID('app.Notas'), 'IX_Notas_Emissao_Cobertura', 'IndexID') IS NOT NULL DROP INDEX IX_Notas_Emissao_Cobertura ON app.Notas;
    IF INDEXPROPERTY(OBJECT_ID('app.Notas'), 'IX_Notas_Pendentes_Vencimento', 'IndexID') IS NOT NULL DROP INDEX IX_Notas_Pendentes_Vencimento ON app.Notas;
    IF INDEXPROPERTY(OBJECT_ID('app.Conciliacoes'), 'IX_Conciliacoes_Concluidas', 'IndexID') IS NOT NULL DROP INDEX IX_Conciliacoes_Concluidas ON app.Conciliacoes;
END;
IF @cfg IN ('B', 'C', 'D')
BEGIN
    ALTER INDEX IX_Notas_Local_Vencimento_Status ON app.Notas REBUILD;
    ALTER INDEX IX_Notas_Provedor_Emissao ON app.Notas REBUILD;
    ALTER INDEX IX_Conciliacoes_Nota_Status ON app.Conciliacoes REBUILD;
END;
IF @cfg = 'B'
BEGIN
    IF INDEXPROPERTY(OBJECT_ID('app.Notas'), 'IX_Notas_Emissao_Cobertura', 'IndexID') IS NOT NULL DROP INDEX IX_Notas_Emissao_Cobertura ON app.Notas;
    IF INDEXPROPERTY(OBJECT_ID('app.Notas'), 'IX_Notas_Pendentes_Vencimento', 'IndexID') IS NOT NULL DROP INDEX IX_Notas_Pendentes_Vencimento ON app.Notas;
    IF INDEXPROPERTY(OBJECT_ID('app.Conciliacoes'), 'IX_Conciliacoes_Concluidas', 'IndexID') IS NOT NULL DROP INDEX IX_Conciliacoes_Concluidas ON app.Conciliacoes;
END;
IF @cfg IN ('C', 'D')
BEGIN
    IF INDEXPROPERTY(OBJECT_ID('app.Notas'), 'IX_Notas_Emissao_Cobertura', 'IndexID') IS NULL
        CREATE INDEX IX_Notas_Emissao_Cobertura ON app.Notas (data_emissao) INCLUDE (local_id, provedor_id, valor_total);
    IF INDEXPROPERTY(OBJECT_ID('app.Notas'), 'IX_Notas_Pendentes_Vencimento', 'IndexID') IS NULL
        CREATE INDEX IX_Notas_Pendentes_Vencimento ON app.Notas (vencimento, id)
            INCLUDE (local_id, provedor_id, valor_total, status) WHERE status = N'PENDENTE';
    IF INDEXPROPERTY(OBJECT_ID('app.Conciliacoes'), 'IX_Conciliacoes_Concluidas', 'IndexID') IS NULL
        CREATE INDEX IX_Conciliacoes_Concluidas ON app.Conciliacoes (nota_id) WHERE status = N'CONCILIADA';
END;
UPDATE STATISTICS app.Notas;
UPDATE STATISTICS app.Conciliacoes;
UPDATE STATISTICS app.ResumoDiario;
PRINT '### CONFIGURACAO ' + @cfg;
SET STATISTICS IO ON;
SET STATISTICS XML ON;
IF @cfg = 'D'
BEGIN
    PRINT '### CONSULTA 1';
    SELECT r.local_id, p.nome AS provedor, YEAR(r.data_emissao) AS ano, MONTH(r.data_emissao) AS mes,
           SUM(r.quantidade) AS quantidade_notas, SUM(r.total) AS total_faturado
    FROM app.ResumoDiario AS r
    JOIN app.Provedores AS p ON p.id = r.provedor_id
    WHERE r.data_emissao >= DATEADD(MONTH, -12, CONVERT(date, GETDATE()))
    GROUP BY r.local_id, p.nome, YEAR(r.data_emissao), MONTH(r.data_emissao)
    ORDER BY ano, mes, r.local_id, provedor
    OPTION (RECOMPILE);
END
ELSE
BEGIN
    PRINT '### CONSULTA 1';
    SELECT n.local_id, p.nome AS provedor, YEAR(n.data_emissao) AS ano, MONTH(n.data_emissao) AS mes,
           COUNT_BIG(*) AS quantidade_notas, SUM(n.valor_total) AS total_faturado
    FROM app.Notas AS n
    JOIN app.Provedores AS p ON p.id = n.provedor_id
    WHERE n.data_emissao >= DATEADD(MONTH, -12, CONVERT(date, GETDATE()))
    GROUP BY n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao)
    ORDER BY ano, mes, n.local_id, provedor
    OPTION (RECOMPILE);
    PRINT '### CONSULTA 2';
    SELECT TOP (500) n.id, n.local_id, n.provedor_id, n.valor_total, n.vencimento, n.status
    FROM app.Notas AS n
    WHERE n.status = N'PENDENTE'
      AND n.vencimento < CONVERT(date, GETDATE())
      AND NOT EXISTS (SELECT 1 FROM app.Conciliacoes AS c WHERE c.nota_id = n.id AND c.status = N'CONCILIADA')
    ORDER BY n.vencimento, n.id
    OPTION (RECOMPILE);
END;
SET STATISTICS XML OFF;
SET STATISTICS IO OFF;
