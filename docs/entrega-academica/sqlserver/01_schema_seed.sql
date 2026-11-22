/*
  SIGp acadêmico: esquema e carga estritamente fictícios para SQL Server.
  Executar apenas em instância local de desenvolvimento. Não usar dados reais.
*/
IF DB_ID(N'SIGpAcademic') IS NULL
    CREATE DATABASE SIGpAcademic;
GO

USE SIGpAcademic;
GO

IF SCHEMA_ID(N'app') IS NULL EXEC(N'CREATE SCHEMA app');
IF SCHEMA_ID(N'audit') IS NULL EXEC(N'CREATE SCHEMA audit');
IF SCHEMA_ID(N'ai') IS NULL EXEC(N'CREATE SCHEMA ai');
IF SCHEMA_ID(N'security') IS NULL EXEC(N'CREATE SCHEMA security');
GO

IF OBJECT_ID(N'app.Locais', N'U') IS NULL
BEGIN
    CREATE TABLE app.Locais (
        id NVARCHAR(40) NOT NULL PRIMARY KEY,
        tipo NVARCHAR(20) NOT NULL,
        nome NVARCHAR(100) NOT NULL,
        cidade NVARCHAR(80) NOT NULL,
        CONSTRAINT CK_Locais_Tipo CHECK (tipo IN (N'agencia', N'rodoviaria', N'garagem'))
    );
END;

IF OBJECT_ID(N'app.Provedores', N'U') IS NULL
BEGIN
    CREATE TABLE app.Provedores (
        id NVARCHAR(40) NOT NULL PRIMARY KEY,
        nome NVARCHAR(80) NOT NULL UNIQUE
    );
END;

IF OBJECT_ID(N'app.Notas', N'U') IS NULL
BEGIN
    CREATE TABLE app.Notas (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        local_id NVARCHAR(40) NOT NULL REFERENCES app.Locais(id),
        provedor_id NVARCHAR(40) NOT NULL REFERENCES app.Provedores(id),
        chave_fiscal NVARCHAR(80) NOT NULL,
        numero NVARCHAR(30) NOT NULL,
        serie NVARCHAR(20) NOT NULL,
        valor_total DECIMAL(12,2) NOT NULL,
        data_emissao DATE NOT NULL,
        vencimento DATE NOT NULL,
        origem NVARCHAR(20) NOT NULL DEFAULT N'manual',
        status NVARCHAR(24) NOT NULL DEFAULT N'PENDENTE',
        CONSTRAINT UQ_Notas_Chave UNIQUE (chave_fiscal),
        CONSTRAINT CK_Notas_Valor CHECK (valor_total > 0)
    );
END;

IF OBJECT_ID(N'app.ItensNota', N'U') IS NULL
BEGIN
    CREATE TABLE app.ItensNota (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        nota_id BIGINT NOT NULL REFERENCES app.Notas(id),
        descricao NVARCHAR(160) NOT NULL,
        valor DECIMAL(12,2) NOT NULL,
        classificacao NVARCHAR(20) NOT NULL DEFAULT N'REVISAR',
        CONSTRAINT CK_Itens_Valor CHECK (valor >= 0),
        CONSTRAINT CK_Itens_Classificacao CHECK (classificacao IN (N'CONTRATADO', N'DIVERGENTE', N'REVISAR'))
    );
END;

IF OBJECT_ID(N'app.Pagamentos', N'U') IS NULL
BEGIN
    CREATE TABLE app.Pagamentos (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        nota_id BIGINT NOT NULL REFERENCES app.Notas(id),
        valor_pago DECIMAL(12,2) NOT NULL,
        data_pagamento DATE NOT NULL,
        referencia NVARCHAR(40) NOT NULL UNIQUE,
        CONSTRAINT CK_Pagamentos_Valor CHECK (valor_pago > 0)
    );
END;

IF OBJECT_ID(N'app.Conciliacoes', N'U') IS NULL
BEGIN
    CREATE TABLE app.Conciliacoes (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        nota_id BIGINT NOT NULL REFERENCES app.Notas(id),
        status NVARCHAR(24) NOT NULL,
        justificativa NVARCHAR(500) NOT NULL,
        revisado_por NVARCHAR(80) NULL,
        atualizado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

-- Trilha à prova de adulteração: tabela LEDGER "somente inclusão" (SQL Server 2022). Ninguém altera nem apaga um
-- evento, nem o sa ou o db_owner (erro 37359; TRUNCATE dá 13545). Um DROP guarda a tabela como "dropped ledger table".
-- Cada transação entra numa cadeia de hashes; o digest (sp_generate_database_ledger_digest) é guardado FORA do banco
-- (seguranca/verificar_ledger.py grava em evidence/parte3/ledger-digests.json, no Git) e sp_verify_database_ledger
-- confere que nada mudou desde cada digest. A verificação exige ALLOW_SNAPSHOT_ISOLATION.
ALTER DATABASE CURRENT SET ALLOW_SNAPSHOT_ISOLATION ON;
GO
IF OBJECT_ID(N'audit.Eventos', N'U') IS NULL
BEGIN
    CREATE TABLE audit.Eventos (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ator NVARCHAR(80) NOT NULL,
        acao NVARCHAR(40) NOT NULL,
        objeto NVARCHAR(80) NOT NULL,
        correlation_id UNIQUEIDENTIFIER NOT NULL,
        detalhe_redigido NVARCHAR(500) NOT NULL DEFAULT N'',
        criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    ) WITH (LEDGER = ON (APPEND_ONLY = ON));
END;
GO
-- Migração de um banco anterior (tabela comum): copia os eventos para a ledger com os mesmos números e registra
-- quantos foram copiados e o SHA-256 do conteúdo antigo. Alterações feitas ANTES desta cópia não são detectáveis.
-- Uma transação só: se algo falhar, nada muda.
IF EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID(N'audit.Eventos') AND ledger_type = 0)
BEGIN
    SET XACT_ABORT ON;
    DECLARE @n BIGINT, @h VARBINARY(32);
    SELECT @n = COUNT_BIG(*),
           @h = HASHBYTES('SHA2_256', STRING_AGG(CONVERT(NVARCHAR(MAX), CONCAT(id, N'|', ator, N'|', acao, N'|', objeto, N'|',
                correlation_id, N'|', detalhe_redigido, N'|', CONVERT(CHAR(27), criado_em, 126))), NCHAR(10)) WITHIN GROUP (ORDER BY id))
    FROM audit.Eventos;
    DECLARE @detalhe NVARCHAR(500) = CONCAT(N'eventos_copiados=', @n, N'; sha256_antes=', CONVERT(CHAR(66), @h, 1),
        N'; daqui em diante nenhum evento pode ser alterado nem apagado; o que mudou antes desta cópia não é detectável');
    BEGIN TRANSACTION;
    EXEC sys.sp_rename N'audit.Eventos', N'Eventos_pre_ledger';
    EXEC sys.sp_executesql N'CREATE TABLE audit.Eventos (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ator NVARCHAR(80) NOT NULL,
        acao NVARCHAR(40) NOT NULL,
        objeto NVARCHAR(80) NOT NULL,
        correlation_id UNIQUEIDENTIFIER NOT NULL,
        detalhe_redigido NVARCHAR(500) NOT NULL DEFAULT N'''',
        criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    ) WITH (LEDGER = ON (APPEND_ONLY = ON));';
    EXEC sys.sp_executesql N'SET IDENTITY_INSERT audit.Eventos ON;
        INSERT INTO audit.Eventos (id, ator, acao, objeto, correlation_id, detalhe_redigido, criado_em)
        SELECT id, ator, acao, objeto, correlation_id, detalhe_redigido, criado_em FROM audit.Eventos_pre_ledger ORDER BY id;
        SET IDENTITY_INSERT audit.Eventos OFF;';
    EXEC sys.sp_executesql N'INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido) VALUES
        (N''migracao_ledger'', N''LEDGER_ATIVADA'', N''audit.Eventos'', NEWID(), @detalhe);',
        N'@detalhe NVARCHAR(500)',
        @detalhe = @detalhe;
    DROP TABLE audit.Eventos_pre_ledger;
    COMMIT TRANSACTION;
    PRINT CONCAT(N'audit.Eventos migrada para ledger: ', @n, N' eventos copiados');
END;
GO

IF OBJECT_ID(N'security.LocalScope', N'U') IS NULL
BEGIN
    CREATE TABLE security.LocalScope (
        principal_name SYSNAME NOT NULL,
        local_id NVARCHAR(40) NOT NULL REFERENCES app.Locais(id),
        CONSTRAINT PK_LocalScope PRIMARY KEY (principal_name, local_id)
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM app.Locais)
BEGIN
    INSERT INTO app.Locais (id, tipo, nome, cidade) VALUES
      (N'LOC-001', N'agencia', N'Agência Centro Fictícia', N'Cidade Alfa'),
      (N'LOC-002', N'rodoviaria', N'Rodoviária Norte Fictícia', N'Cidade Beta'),
      (N'LOC-003', N'garagem', N'Garagem Sul Fictícia', N'Cidade Gama');
END;

IF NOT EXISTS (SELECT 1 FROM app.Provedores)
BEGIN
    INSERT INTO app.Provedores (id, nome) VALUES
      (N'PROV-001', N'Conecta Alfa Fictícia'),
      (N'PROV-002', N'Rede Beta Fictícia'),
      (N'PROV-003', N'Link Gama Fictícia');
END;
GO

IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'dbo' AND local_id = N'LOC-001')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'dbo', N'LOC-001');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'dbo' AND local_id = N'LOC-002')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'dbo', N'LOC-002');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'dbo' AND local_id = N'LOC-003')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'dbo', N'LOC-003');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_ia_loc001' AND local_id = N'LOC-001')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_ia_loc001', N'LOC-001');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_ia_loc002' AND local_id = N'LOC-002')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_ia_loc002', N'LOC-002');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_api_test' AND local_id = N'LOC-001')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_api_test', N'LOC-001');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_api_test' AND local_id = N'LOC-002')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_api_test', N'LOC-002');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_api_test' AND local_id = N'LOC-003')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_api_test', N'LOC-003');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_auditor_test' AND local_id = N'LOC-001')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_auditor_test', N'LOC-001');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_auditor_test' AND local_id = N'LOC-002')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_auditor_test', N'LOC-002');
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_auditor_test' AND local_id = N'LOC-003')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_auditor_test', N'LOC-003');
GO

IF NOT EXISTS (SELECT 1 FROM app.Notas)
BEGIN
    ;WITH Serie(n) AS (
        SELECT 1 UNION ALL SELECT n + 1 FROM Serie WHERE n < 20
    )
    INSERT INTO app.Notas
        (local_id, provedor_id, chave_fiscal, numero, serie, valor_total, data_emissao, vencimento, origem, status)
    SELECT
        CASE WHEN n % 3 = 1 THEN N'LOC-001' WHEN n % 3 = 2 THEN N'LOC-002' ELSE N'LOC-003' END,
        CASE WHEN n % 3 = 1 THEN N'PROV-001' WHEN n % 3 = 2 THEN N'PROV-002' ELSE N'PROV-003' END,
        CONCAT(N'SINTETICA-CHAVE-', RIGHT(CONCAT(N'000', n), 3)),
        CONCAT(N'SINT-', RIGHT(CONCAT(N'000', n), 3)),
        N'A',
        CAST(100 + n * 7.25 AS DECIMAL(12,2)),
        DATEADD(DAY, -n, CONVERT(date, '20261001')),
        DATEADD(DAY, 15 + n, CONVERT(date, '20261001')),
        N'teste',
        CASE WHEN n % 4 = 0 THEN N'PENDENTE' ELSE N'RECEBIDA' END
    FROM Serie
    OPTION (MAXRECURSION 20);
END;
GO

IF NOT EXISTS (SELECT 1 FROM app.ItensNota)
BEGIN
    INSERT INTO app.ItensNota (nota_id, descricao, valor, classificacao)
    SELECT id, N'Link principal sintético', valor_total, N'CONTRATADO'
    FROM app.Notas;
END;
GO

IF NOT EXISTS (SELECT 1 FROM app.Pagamentos)
BEGIN
    INSERT INTO app.Pagamentos (nota_id, valor_pago, data_pagamento, referencia)
    SELECT id, valor_total, DATEADD(DAY, 10, data_emissao), CONCAT(N'SIM-PG-', id)
    FROM app.Notas
    WHERE id % 2 = 0;
END;
GO

IF NOT EXISTS (SELECT 1 FROM app.Conciliacoes)
BEGIN
    INSERT INTO app.Conciliacoes (nota_id, status, justificativa)
    SELECT n.id,
           CASE WHEN p.nota_id IS NULL THEN N'PENDENTE' ELSE N'AGUARDANDO_FATURA' END,
           N'Dado sintético para teste; requer conferência.'
    FROM app.Notas AS n
    LEFT JOIN app.Pagamentos AS p ON p.nota_id = n.id;
END;
GO

-- Otimização da consulta 1 (total faturado por local, provedor e mês): DESNORMALIZAÇÃO. A consulta soma ~47 mil notas
-- a cada execução e nenhum índice evita essa soma. O resumo guarda o total já somado por local, provedor e DIA (2.190
-- linhas para 100.020 notas); o dia mantém o resultado idêntico ao da consulta original, inclusive o primeiro mês parcial
-- da janela. Uma view indexada não serve: o SQL Server não a permite sobre tabela com RLS e, sem filtro, ela exporia os
-- totais de todos os locais. O resumo entra na mesma política de RLS (ver a política abaixo).
IF OBJECT_ID(N'app.ResumoDiario', N'U') IS NULL
BEGIN
    CREATE TABLE app.ResumoDiario (
        data_emissao DATE NOT NULL,
        local_id NVARCHAR(40) NOT NULL REFERENCES app.Locais(id),
        provedor_id NVARCHAR(40) NOT NULL REFERENCES app.Provedores(id),
        quantidade BIGINT NOT NULL,
        total DECIMAL(18,2) NOT NULL,
        CONSTRAINT PK_ResumoDiario PRIMARY KEY CLUSTERED (data_emissao, local_id, provedor_id),
        CONSTRAINT CK_ResumoDiario_Quantidade CHECK (quantidade > 0)
    );
END;
GO

-- Mantém o resumo a cada INSERT, UPDATE e DELETE em app.Notas (por instrução, não por linha). Roda como o dono da
-- tabela (EXECUTE AS OWNER) para enxergar e atualizar o resumo de todos os locais; quem grava continua sujeito aos
-- predicados BLOCK de app.Notas, então só altera o resumo dos locais do próprio escopo.
CREATE OR ALTER TRIGGER app.trg_Notas_ResumoDiario
ON app.Notas
WITH EXECUTE AS OWNER
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    IF NOT EXISTS (SELECT 1 FROM inserted) AND NOT EXISTS (SELECT 1 FROM deleted)
        RETURN;

    DECLARE @delta TABLE (
        data_emissao DATE NOT NULL, local_id NVARCHAR(40) NOT NULL, provedor_id NVARCHAR(40) NOT NULL,
        quantidade BIGINT NOT NULL, total DECIMAL(18,2) NOT NULL,
        PRIMARY KEY (data_emissao, local_id, provedor_id)
    );
    INSERT INTO @delta (data_emissao, local_id, provedor_id, quantidade, total)
    SELECT data_emissao, local_id, provedor_id, SUM(q), SUM(t)
    FROM (
        SELECT data_emissao, local_id, provedor_id, COUNT_BIG(*) AS q, SUM(valor_total) AS t
        FROM inserted GROUP BY data_emissao, local_id, provedor_id
        UNION ALL
        SELECT data_emissao, local_id, provedor_id, -COUNT_BIG(*), -SUM(valor_total)
        FROM deleted GROUP BY data_emissao, local_id, provedor_id
    ) AS m
    GROUP BY data_emissao, local_id, provedor_id
    HAVING SUM(q) <> 0 OR SUM(t) <> 0;

    UPDATE r
    SET r.quantidade = r.quantidade + d.quantidade, r.total = r.total + d.total
    FROM app.ResumoDiario AS r WITH (UPDLOCK, HOLDLOCK)
    JOIN @delta AS d
      ON d.data_emissao = r.data_emissao AND d.local_id = r.local_id AND d.provedor_id = r.provedor_id
    WHERE r.quantidade + d.quantidade > 0;

    DELETE r
    FROM app.ResumoDiario AS r
    JOIN @delta AS d
      ON d.data_emissao = r.data_emissao AND d.local_id = r.local_id AND d.provedor_id = r.provedor_id
    WHERE r.quantidade + d.quantidade <= 0;

    INSERT INTO app.ResumoDiario (data_emissao, local_id, provedor_id, quantidade, total)
    SELECT d.data_emissao, d.local_id, d.provedor_id, d.quantidade, d.total
    FROM @delta AS d
    WHERE d.quantidade > 0
      AND NOT EXISTS (
        SELECT 1 FROM app.ResumoDiario AS r
        WHERE r.data_emissao = d.data_emissao AND r.local_id = d.local_id AND r.provedor_id = d.provedor_id
      );
END;
GO

-- Trilha de auditoria das gravações em app.Notas: quem inseriu, alterou ou apagou, o que mudou e quando.
-- SEM "EXECUTE AS": USER_NAME() é o principal real de quem gravou. O gatilho e audit.Eventos têm o mesmo dono, então a
-- gravação na trilha passa pelo encadeamento de propriedade, mesmo com o DENY INSERT direto do papel da API.
-- A chave fiscal (dado sensível) nunca entra no texto: só o aviso de que mudou. Mais de 100 linhas viram um evento só.
CREATE OR ALTER TRIGGER app.trg_Notas_Auditoria
ON app.Notas
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ins INT = (SELECT COUNT(*) FROM inserted);
    DECLARE @del INT = (SELECT COUNT(*) FROM deleted);
    IF @ins = 0 AND @del = 0
        RETURN;
    DECLARE @acao NVARCHAR(40) = CASE WHEN @ins > 0 AND @del > 0 THEN N'NOTA_ALTERADA'
                                      WHEN @ins > 0 THEN N'NOTA_INSERIDA' ELSE N'NOTA_EXCLUIDA' END;
    DECLARE @ator NVARCHAR(80) = LEFT(USER_NAME(), 80);
    DECLARE @quem NVARCHAR(200) = CONCAT(N'db_principal=', USER_NAME(), N'; login=', ORIGINAL_LOGIN(), N'; app=', LEFT(APP_NAME(), 40));
    DECLARE @cid UNIQUEIDENTIFIER = NEWID();

    IF @ins > 100 OR @del > 100
    BEGIN
        INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido)
        SELECT @ator, CONCAT(@acao, N'_LOTE'), N'app.Notas', @cid,
               LEFT(CONCAT(N'linhas=', CASE WHEN @ins > @del THEN @ins ELSE @del END,
                           N'; ids=', MIN(id), N'..', MAX(id),
                           N'; locais=', (SELECT STRING_AGG(local_id, N',') WITHIN GROUP (ORDER BY local_id)
                                          FROM (SELECT local_id FROM inserted UNION SELECT local_id FROM deleted) AS l),
                           N'; ', @quem), 500)
        FROM (SELECT id FROM inserted UNION ALL SELECT id FROM deleted) AS x;
        RETURN;
    END;

    INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido)
    SELECT @ator, @acao, N'app.Notas', @cid,
           LEFT(CONCAT(
               N'nota_id=', COALESCE(i.id, d.id), N'; local_id=', COALESCE(i.local_id, d.local_id),
               CASE
                   WHEN d.id IS NULL THEN CONCAT(N'; provedor_id=', i.provedor_id, N'; valor=', i.valor_total,
                                                 N'; emissao=', i.data_emissao, N'; vencimento=', i.vencimento, N'; status=', i.status)
                   WHEN i.id IS NULL THEN CONCAT(N'; provedor_id=', d.provedor_id, N'; valor=', d.valor_total,
                                                 N'; vencimento=', d.vencimento, N'; status=', d.status)
                   ELSE CONCAT(N'; mudou:',
                       CASE WHEN i.local_id <> d.local_id THEN CONCAT(N' local ', d.local_id, N'→', i.local_id, N';') ELSE N'' END,
                       CASE WHEN i.provedor_id <> d.provedor_id THEN CONCAT(N' provedor ', d.provedor_id, N'→', i.provedor_id, N';') ELSE N'' END,
                       CASE WHEN i.valor_total <> d.valor_total THEN CONCAT(N' valor ', d.valor_total, N'→', i.valor_total, N';') ELSE N'' END,
                       CASE WHEN i.data_emissao <> d.data_emissao THEN CONCAT(N' emissao ', d.data_emissao, N'→', i.data_emissao, N';') ELSE N'' END,
                       CASE WHEN i.vencimento <> d.vencimento THEN CONCAT(N' vencimento ', d.vencimento, N'→', i.vencimento, N';') ELSE N'' END,
                       CASE WHEN i.status <> d.status THEN CONCAT(N' status ', d.status, N'→', i.status, N';') ELSE N'' END,
                       CASE WHEN i.numero <> d.numero OR i.serie <> d.serie THEN N' numero/serie;' ELSE N'' END,
                       CASE WHEN i.chave_fiscal <> d.chave_fiscal THEN N' chave_fiscal (valor omitido);' ELSE N'' END)
               END,
               N'; ', @quem), 500)
    FROM inserted AS i
    FULL OUTER JOIN deleted AS d ON d.id = i.id;
END;
GO

-- Preenche (ou refaz) o resumo a partir das notas quando os totais não batem: carga inicial e banco antigo.
-- Roda antes da política ser recriada; o dono do banco vê todas as notas.
IF EXISTS (
    SELECT 1
    FROM (SELECT COUNT_BIG(*) AS q, COALESCE(SUM(valor_total), 0) AS t FROM app.Notas) AS n
    CROSS JOIN (SELECT COALESCE(SUM(quantidade), 0) AS q, COALESCE(SUM(total), 0) AS t FROM app.ResumoDiario) AS r
    WHERE n.q <> r.q OR n.t <> r.t
)
BEGIN
    DELETE FROM app.ResumoDiario;
    INSERT INTO app.ResumoDiario (data_emissao, local_id, provedor_id, quantidade, total)
    SELECT data_emissao, local_id, provedor_id, COUNT_BIG(*), SUM(valor_total)
    FROM app.Notas
    GROUP BY data_emissao, local_id, provedor_id;
END;
GO

-- Reparo de acentos. Até 20/11/2026 os scripts não tinham a marca UTF-8 (BOM) e o sqlcmd sem "-f 65001" os lia na
-- página de código do Windows: "Fictícia" virava "FictÃ­cia" nos nomes, itens, conciliações e mensagens dos
-- procedimentos. Os scripts agora têm a marca e o setup passa "-f 65001"; este bloco conserta o que já foi gravado.
-- Só age onde há o sinal da leitura errada (idempotente).
CREATE OR ALTER FUNCTION dbo.fn_reparar_utf8_lido_como_1252 (@t NVARCHAR(4000))
RETURNS NVARCHAR(4000)
WITH SCHEMABINDING
AS
BEGIN
    IF @t IS NULL OR @t NOT LIKE N'%Ã%'
        RETURN @t;
    RETURN REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
           REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(@t COLLATE Latin1_General_100_BIN2,
           NCHAR(195) + NCHAR(161), N'á'), NCHAR(195) + NCHAR(160), N'à'), NCHAR(195) + NCHAR(162), N'â'), NCHAR(195) + NCHAR(163), N'ã'),
           NCHAR(195) + NCHAR(167), N'ç'), NCHAR(195) + NCHAR(169), N'é'), NCHAR(195) + NCHAR(170), N'ê'), NCHAR(195) + NCHAR(173), N'í'),
           NCHAR(195) + NCHAR(179), N'ó'), NCHAR(195) + NCHAR(180), N'ô'), NCHAR(195) + NCHAR(181), N'õ'), NCHAR(195) + NCHAR(186), N'ú'),
           NCHAR(195) + NCHAR(8240), N'É'), NCHAR(195) + NCHAR(8225), N'Ç'), NCHAR(195) + NCHAR(402), N'Ã'), NCHAR(195) + NCHAR(8220), N'Ó'),
           NCHAR(195) + NCHAR(353), N'Ú'), NCHAR(195) + NCHAR(129), N'Á'), NCHAR(195) + NCHAR(141), N'Í'), NCHAR(195) + NCHAR(8226), N'Õ');
END;
GO
UPDATE app.Locais SET nome = dbo.fn_reparar_utf8_lido_como_1252(nome) WHERE nome LIKE N'%Ã%';
UPDATE app.Provedores SET nome = dbo.fn_reparar_utf8_lido_como_1252(nome) WHERE nome LIKE N'%Ã%';
UPDATE app.ItensNota SET descricao = dbo.fn_reparar_utf8_lido_como_1252(descricao) WHERE descricao LIKE N'%Ã%';
UPDATE app.Conciliacoes SET justificativa = dbo.fn_reparar_utf8_lido_como_1252(justificativa) WHERE justificativa LIKE N'%Ã%';
GO

IF EXISTS (
    SELECT 1 FROM sys.security_policies
    WHERE object_id = OBJECT_ID(N'security.LocalScopePolicy')
)
    DROP SECURITY POLICY security.LocalScopePolicy;
GO

CREATE OR ALTER FUNCTION security.fn_local_scope(@local_id NVARCHAR(40))
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
    SELECT 1 AS permitido
    FROM security.LocalScope AS s
    WHERE s.principal_name COLLATE DATABASE_DEFAULT = USER_NAME() COLLATE DATABASE_DEFAULT
      AND s.local_id = @local_id;
GO

-- Predicado de ESCRITA (BLOCK). O FILTER só esconde linhas na leitura; sem BLOCK, quem tem escopo só no LOC-001
-- consegue gravar uma nota no LOC-002 ou mover uma nota para outro local (escalonamento horizontal, ataques E6 e E7
-- de 08_ataque_escalonamento.sql). db_owner passa porque já pode alterar a própria política (e a carga de volume
-- 03_load_benchmark.sql grava como dono do banco); os demais só gravam no local do seu escopo.
CREATE OR ALTER FUNCTION security.fn_local_scope_escrita(@local_id NVARCHAR(40))
RETURNS TABLE
WITH SCHEMABINDING
AS
    RETURN
    SELECT 1 AS permitido
    WHERE IS_MEMBER(N'db_owner') = 1
       OR EXISTS (
            SELECT 1
            FROM security.LocalScope AS s
            WHERE s.principal_name COLLATE DATABASE_DEFAULT = USER_NAME() COLLATE DATABASE_DEFAULT
              AND s.local_id = @local_id
       );
GO

CREATE SECURITY POLICY security.LocalScopePolicy
    ADD FILTER PREDICATE security.fn_local_scope(local_id) ON app.Notas,
    ADD BLOCK PREDICATE security.fn_local_scope_escrita(local_id) ON app.Notas AFTER INSERT,
    ADD BLOCK PREDICATE security.fn_local_scope_escrita(local_id) ON app.Notas BEFORE UPDATE,
    ADD BLOCK PREDICATE security.fn_local_scope_escrita(local_id) ON app.Notas AFTER UPDATE,
    ADD BLOCK PREDICATE security.fn_local_scope_escrita(local_id) ON app.Notas BEFORE DELETE,
    -- Resumo da consulta 1: cada principal só lê o resumo dos locais do seu escopo. Usa a função de escrita, que libera
    -- o dono do banco, porque o gatilho que mantém o resumo roda como dono e precisa ver todas as linhas.
    ADD FILTER PREDICATE security.fn_local_scope_escrita(local_id) ON app.ResumoDiario
    WITH (STATE = ON);
GO

CREATE OR ALTER VIEW ai.vw_contexto_minimo
AS
    SELECT n.id AS nota_id, n.local_id, n.provedor_id AS provider_id,
           p.nome AS provedor, l.tipo AS tipo_local,
           i.descricao, i.valor, i.classificacao, n.vencimento, n.status
    FROM app.Notas AS n
    JOIN app.Provedores AS p ON p.id = n.provedor_id
    JOIN app.Locais AS l ON l.id = n.local_id
    JOIN app.ItensNota AS i ON i.nota_id = n.id;
GO

CREATE OR ALTER PROCEDURE ai.usp_get_context
    @local_id NVARCHAR(40),
    @correlation_id UNIQUEIDENTIFIER,
    @provider_id NVARCHAR(40) = NULL,
    @take INT = 20,
    @return_json BIT = 0,
    @requested_by NVARCHAR(80) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @db_actor SYSNAME = USER_NAME();
    DECLARE @actor NVARCHAR(80) = COALESCE(NULLIF(LTRIM(RTRIM(@requested_by)), N''), USER_NAME());
    DECLARE @row_count INT;
    DECLARE @context_json NVARCHAR(MAX);
    DECLARE @context TABLE (
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

    IF @take IS NULL OR @take < 1 OR @take > 50
        THROW 51003, 'O limite de contexto deve estar entre 1 e 50.', 1;

    IF NOT EXISTS (
        SELECT 1
        FROM security.LocalScope
        WHERE principal_name COLLATE DATABASE_DEFAULT = @db_actor COLLATE DATABASE_DEFAULT
          AND local_id = @local_id
    )
    BEGIN
        INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido)
        VALUES (
            @actor, N'AI_CONTEXT_DENIED', N'ai.vw_contexto_minimo', @correlation_id,
            CONCAT(N'local_id=', @local_id, N'; db_principal=', @db_actor, N'; reason=scope_denied')
        );
        THROW 51001, 'Acesso ao local solicitado não autorizado.', 1;
    END;

    INSERT INTO @context
    SELECT TOP (@take)
        nota_id, local_id, provider_id, provedor, tipo_local, descricao, valor, classificacao, vencimento, status
    FROM ai.vw_contexto_minimo
    WHERE local_id = @local_id
      AND (@provider_id IS NULL OR provider_id = @provider_id)
    ORDER BY vencimento DESC, nota_id DESC;

    SET @row_count = @@ROWCOUNT;

    INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido)
    VALUES (
        @actor, N'AI_CONTEXT_READ', N'ai.vw_contexto_minimo', @correlation_id,
        CONCAT(N'local_id=', @local_id, N'; provider_id=', COALESCE(@provider_id, N'*'),
               N'; db_principal=', @db_actor, N'; rows=', @row_count)
    );

    IF @return_json = 1
    BEGIN
        SET @context_json = (
            SELECT nota_id, local_id, provider_id, provedor, tipo_local, descricao, valor,
                   classificacao, vencimento, status
            FROM @context
            FOR JSON PATH
        );
        SELECT COALESCE(@context_json, N'[]') AS context_json;
        RETURN;
    END;

    SELECT nota_id, local_id, provider_id, provedor, tipo_local, descricao, valor,
           classificacao, vencimento, status
    FROM @context;
END;
GO

CREATE OR ALTER PROCEDURE ai.usp_log_sources
    @local_id NVARCHAR(40),
    @correlation_id UNIQUEIDENTIFIER,
    @source_ids NVARCHAR(350),
    @requested_by NVARCHAR(80) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @db_actor SYSNAME = USER_NAME();
    DECLARE @actor NVARCHAR(80) = COALESCE(NULLIF(LTRIM(RTRIM(@requested_by)), N''), USER_NAME());

    IF NOT EXISTS (
        SELECT 1
        FROM security.LocalScope
        WHERE principal_name COLLATE DATABASE_DEFAULT = @db_actor COLLATE DATABASE_DEFAULT
          AND local_id = @local_id
    )
    BEGIN
        INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido)
        VALUES (
            @actor, N'AI_SOURCES_DENIED', N'ai.rag_documents', @correlation_id,
            CONCAT(N'local_id=', @local_id, N'; db_principal=', @db_actor, N'; reason=scope_denied')
        );
        THROW 51002, 'Registro das fontes para o local solicitado não autorizado.', 1;
    END;

    INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido)
    VALUES (
        @actor, N'AI_RAG_SOURCES', N'ai.rag_documents', @correlation_id,
        CONCAT(N'local_id=', @local_id, N'; db_principal=', @db_actor, N'; source_ids=', @source_ids)
    );
END;
GO

-- O que a IA respondeu, ligado ao mesmo correlation_id da leitura do contexto e das fontes.
-- Campos estruturados (não texto livre): a decisão e a sugestão do modelo só podem ser uma das classificações
-- permitidas; o pedido entra resumido (provedor, valor e o hash da descrição, que pode trazer texto malicioso).
CREATE OR ALTER PROCEDURE ai.usp_log_response
    @local_id NVARCHAR(40),
    @correlation_id UNIQUEIDENTIFIER,
    @status NVARCHAR(10),
    @provider_id NVARCHAR(40),
    @amount DECIMAL(12,2) = NULL,
    @description_sha256 CHAR(64) = NULL,
    @injection_detected BIT = 0,
    @classification NVARCHAR(20) = NULL,
    @model_classification NVARCHAR(20) = NULL,
    @model_name NVARCHAR(60) = NULL,
    @prompt_version NVARCHAR(10) = NULL,
    @reason NVARCHAR(160) = NULL,
    @source_ids NVARCHAR(200) = NULL,
    @context_rows INT = NULL,
    @response_sha256 CHAR(64) = NULL,
    @requested_by NVARCHAR(80) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @db_actor SYSNAME = USER_NAME();
    DECLARE @actor NVARCHAR(80) = COALESCE(NULLIF(LTRIM(RTRIM(@requested_by)), N''), USER_NAME());

    IF @status NOT IN (N'OK', N'ERRO')
        THROW 51004, 'status deve ser OK ou ERRO.', 1;
    IF @classification IS NOT NULL AND @classification NOT IN (N'CONTRATADO', N'DIVERGENTE', N'REVISAR')
        THROW 51005, 'Classificação fora do conjunto permitido.', 1;
    IF @model_classification IS NOT NULL AND @model_classification NOT IN (N'CONTRATADO', N'DIVERGENTE', N'REVISAR')
        THROW 51005, 'Classificação do modelo fora do conjunto permitido.', 1;
    IF @status = N'OK' AND (@classification IS NULL OR @response_sha256 IS NULL)
        THROW 51006, 'Resposta OK exige a classificação e o hash da resposta.', 1;

    IF NOT EXISTS (
        SELECT 1
        FROM security.LocalScope
        WHERE principal_name COLLATE DATABASE_DEFAULT = @db_actor COLLATE DATABASE_DEFAULT
          AND local_id = @local_id
    )
    BEGIN
        INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido)
        VALUES (
            @actor, N'AI_RESPONSE_DENIED', N'ai.analise', @correlation_id,
            CONCAT(N'local_id=', @local_id, N'; db_principal=', @db_actor, N'; reason=scope_denied')
        );
        THROW 51007, 'Registro da resposta para o local solicitado não autorizado.', 1;
    END;

    INSERT INTO audit.Eventos (ator, acao, objeto, correlation_id, detalhe_redigido)
    VALUES (
        @actor,
        CASE WHEN @status = N'OK' THEN N'AI_RESPONSE' ELSE N'AI_RESPONSE_FAILED' END,
        N'ai.analise',
        @correlation_id,
        LEFT(CONCAT(
            N'local_id=', @local_id, N'; db_principal=', @db_actor,
            N'; pedido=', @provider_id, N' ', COALESCE(CONVERT(NVARCHAR(20), @amount), N'?'),
            N' desc_sha256=', COALESCE(LEFT(@description_sha256, 16), N'-'),
            N'; injecao=', @injection_detected,
            N'; decisao=', COALESCE(@classification, N'-'),
            N'; modelo=', COALESCE(@model_classification, N'-'), N' (', COALESCE(@model_name, N'-'), N', prompt ', COALESCE(@prompt_version, N'-'), N')',
            N'; motivo=', COALESCE(@reason, N'-'),
            N'; fontes=', COALESCE(@source_ids, N'-'),
            N'; linhas=', COALESCE(CONVERT(NVARCHAR(10), @context_rows), N'-'),
            N'; resposta_sha256=', COALESCE(@response_sha256, N'-'),
            N'; pagamento_automatico=0'
        ), 500)
    );
END;
GO

IF DATABASE_PRINCIPAL_ID(N'sigp_api') IS NULL CREATE ROLE sigp_api;
IF DATABASE_PRINCIPAL_ID(N'sigp_auditor') IS NULL CREATE ROLE sigp_auditor;
IF DATABASE_PRINCIPAL_ID(N'sigp_ia') IS NULL CREATE ROLE sigp_ia;
GO

GRANT SELECT, INSERT, UPDATE ON OBJECT::app.Notas TO sigp_api;
GRANT SELECT, INSERT, UPDATE ON OBJECT::app.ItensNota TO sigp_api;
GRANT SELECT, INSERT, UPDATE ON OBJECT::app.Pagamentos TO sigp_api;
GRANT SELECT, INSERT, UPDATE ON OBJECT::app.Conciliacoes TO sigp_api;
GRANT SELECT, INSERT, UPDATE ON OBJECT::app.Locais TO sigp_api;
GRANT SELECT, INSERT, UPDATE ON OBJECT::app.Provedores TO sigp_api;
GRANT SELECT ON OBJECT::app.ResumoDiario TO sigp_api;
DENY INSERT, UPDATE, DELETE ON OBJECT::app.ResumoDiario TO sigp_api;
DENY DELETE ON SCHEMA::app TO sigp_api;
-- A trilha só recebe eventos pelos procedimentos da IA e pelo gatilho de auditoria (encadeamento de propriedade).
-- O INSERT direto do papel da API permitia forjar eventos (teste T2a de 14_auditoria_testes.sql) e não era usado.
REVOKE INSERT ON OBJECT::audit.Eventos FROM sigp_api;
DENY INSERT, SELECT, UPDATE, DELETE ON OBJECT::audit.Eventos TO sigp_api;
GRANT SELECT ON OBJECT::ai.vw_contexto_minimo TO sigp_auditor;
GRANT SELECT ON OBJECT::audit.Eventos TO sigp_auditor;
GRANT EXECUTE ON OBJECT::ai.usp_get_context TO sigp_ia;
GRANT EXECUTE ON OBJECT::ai.usp_log_sources TO sigp_ia;
GRANT EXECUTE ON OBJECT::ai.usp_log_response TO sigp_ia;
DENY SELECT, INSERT, UPDATE, DELETE ON SCHEMA::app TO sigp_ia;
DENY SELECT, INSERT, UPDATE, DELETE ON SCHEMA::audit TO sigp_ia;
DENY SELECT, INSERT, UPDATE, DELETE ON OBJECT::ai.vw_contexto_minimo TO sigp_ia;
DENY INSERT, UPDATE, DELETE ON SCHEMA::ai TO sigp_ia;
GO

IF DATABASE_PRINCIPAL_ID(N'sigp_ia_loc001') IS NULL CREATE USER sigp_ia_loc001 WITHOUT LOGIN;
IF DATABASE_PRINCIPAL_ID(N'sigp_ia_loc002') IS NULL CREATE USER sigp_ia_loc002 WITHOUT LOGIN;
IF DATABASE_PRINCIPAL_ID(N'sigp_api_test') IS NULL CREATE USER sigp_api_test WITHOUT LOGIN;
IF DATABASE_PRINCIPAL_ID(N'sigp_auditor_test') IS NULL CREATE USER sigp_auditor_test WITHOUT LOGIN;
IF DATABASE_PRINCIPAL_ID(N'sigp_denied_test') IS NULL CREATE USER sigp_denied_test WITHOUT LOGIN;
IF DATABASE_PRINCIPAL_ID(N'sigp_operador_loc001') IS NULL CREATE USER sigp_operador_loc001 WITHOUT LOGIN;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_role_members WHERE role_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_ia') AND member_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_ia_loc001'))
    ALTER ROLE sigp_ia ADD MEMBER sigp_ia_loc001;
IF NOT EXISTS (SELECT 1 FROM sys.database_role_members WHERE role_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_ia') AND member_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_ia_loc002'))
    ALTER ROLE sigp_ia ADD MEMBER sigp_ia_loc002;
IF NOT EXISTS (SELECT 1 FROM sys.database_role_members WHERE role_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_api') AND member_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_api_test'))
    ALTER ROLE sigp_api ADD MEMBER sigp_api_test;
IF NOT EXISTS (SELECT 1 FROM sys.database_role_members WHERE role_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_auditor') AND member_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_auditor_test'))
    ALTER ROLE sigp_auditor ADD MEMBER sigp_auditor_test;
-- Operador regional: grava como a API, mas o escopo é só o LOC-001 (alvo do teste de escalonamento horizontal).
IF NOT EXISTS (SELECT 1 FROM sys.database_role_members WHERE role_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_api') AND member_principal_id = DATABASE_PRINCIPAL_ID(N'sigp_operador_loc001'))
    ALTER ROLE sigp_api ADD MEMBER sigp_operador_loc001;
IF NOT EXISTS (SELECT 1 FROM security.LocalScope WHERE principal_name = N'sigp_operador_loc001' AND local_id = N'LOC-001')
    INSERT INTO security.LocalScope (principal_name, local_id) VALUES (N'sigp_operador_loc001', N'LOC-001');
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'app.Notas') AND name = N'IX_Notas_Local_Vencimento_Status')
    CREATE INDEX IX_Notas_Local_Vencimento_Status ON app.Notas (local_id, vencimento, status);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'app.Notas') AND name = N'IX_Notas_Provedor_Emissao')
    CREATE INDEX IX_Notas_Provedor_Emissao ON app.Notas (provedor_id, data_emissao);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'app.Pagamentos') AND name = N'IX_Pagamentos_Nota_Data')
    CREATE INDEX IX_Pagamentos_Nota_Data ON app.Pagamentos (nota_id, data_pagamento);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'app.Conciliacoes') AND name = N'IX_Conciliacoes_Nota_Status')
    CREATE INDEX IX_Conciliacoes_Nota_Status ON app.Conciliacoes (nota_id, status);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'audit.Eventos') AND name = N'IX_Auditoria_Data_Correlation')
    CREATE INDEX IX_Auditoria_Data_Correlation ON audit.Eventos (criado_em, correlation_id);
GO

SELECT
    (SELECT COUNT(*) FROM app.Locais) AS locais_sinteticos,
    (SELECT COUNT(*) FROM app.Provedores) AS provedores_sinteticos,
    (SELECT COUNT(*) FROM app.Notas) AS notas_sinteticas,
    (SELECT COUNT(*) FROM app.ItensNota) AS itens_sinteticos,
    (SELECT COUNT(*) FROM app.Pagamentos) AS pagamentos_sinteticos,
    (SELECT COUNT(*) FROM app.Conciliacoes) AS conciliacoes_sinteticas,
    (SELECT COUNT(*) FROM security.LocalScope) AS escopos_sinteticos;
