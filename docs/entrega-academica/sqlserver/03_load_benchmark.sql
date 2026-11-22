USE SIGpAcademic;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @target_rows INT = 100000;

;WITH Numbers AS (
    SELECT TOP (@target_rows)
        ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n
    FROM sys.all_objects AS a
    CROSS JOIN sys.all_objects AS b
)
INSERT INTO app.Notas
    (local_id, provedor_id, chave_fiscal, numero, serie, valor_total,
     data_emissao, vencimento, origem, status)
SELECT
    CASE WHEN n % 3 = 1 THEN N'LOC-001' WHEN n % 3 = 2 THEN N'LOC-002' ELSE N'LOC-003' END,
    CASE WHEN n % 3 = 1 THEN N'PROV-001' WHEN n % 3 = 2 THEN N'PROV-002' ELSE N'PROV-003' END,
    CONCAT(N'CARGA-CHAVE-', RIGHT(CONCAT(N'000000', n), 6)),
    CONCAT(N'CARGA-', RIGHT(CONCAT(N'000000', n), 6)),
    N'LOAD',
    CAST(80 + (n % 9000) / 10.0 AS DECIMAL(12,2)),
    DATEADD(DAY, -(n % 730), CONVERT(date, GETDATE())),
    DATEADD(DAY, (n % 90) - 30, CONVERT(date, GETDATE())),
    N'carga_sintetica',
    CASE WHEN n % 4 = 0 THEN N'PENDENTE' ELSE N'RECEBIDA' END
FROM Numbers
WHERE NOT EXISTS (
    SELECT 1 FROM app.Notas AS existing
    WHERE existing.chave_fiscal = CONCAT(N'CARGA-CHAVE-', RIGHT(CONCAT(N'000000', n), 6))
);

INSERT INTO app.ItensNota (nota_id, descricao, valor, classificacao)
SELECT n.id, N'Item sintético de carga', n.valor_total, N'REVISAR'
FROM app.Notas AS n
WHERE n.origem = N'carga_sintetica'
  AND NOT EXISTS (SELECT 1 FROM app.ItensNota AS i WHERE i.nota_id = n.id);

INSERT INTO app.Pagamentos (nota_id, valor_pago, data_pagamento, referencia)
SELECT n.id, n.valor_total, DATEADD(DAY, 15, n.data_emissao), CONCAT(N'CARGA-PG-', n.id)
FROM app.Notas AS n
WHERE n.origem = N'carga_sintetica'
  AND n.id % 2 = 0
  AND NOT EXISTS (SELECT 1 FROM app.Pagamentos AS p WHERE p.nota_id = n.id);

INSERT INTO app.Conciliacoes (nota_id, status, justificativa)
SELECT n.id, N'PENDENTE', N'Linha sintética criada para benchmark.'
FROM app.Notas AS n
WHERE n.origem = N'carga_sintetica'
  AND NOT EXISTS (SELECT 1 FROM app.Conciliacoes AS c WHERE c.nota_id = n.id);

SELECT
    (SELECT COUNT_BIG(*) FROM app.Notas) AS notas,
    (SELECT COUNT_BIG(*) FROM app.ItensNota) AS itens,
    (SELECT COUNT_BIG(*) FROM app.Pagamentos) AS pagamentos,
    (SELECT COUNT_BIG(*) FROM app.Conciliacoes) AS conciliacoes;
GO
