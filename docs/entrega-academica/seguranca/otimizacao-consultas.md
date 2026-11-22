# Otimização: duas consultas lentas, antes e depois

Gerado por [`../sqlserver/gerar_otimizacao.py`](../sqlserver/gerar_otimizacao.py) a partir das evidências em [`../sqlserver/evidence/parte3/otimizacao/`](../sqlserver/evidence/parte3/otimizacao/); nenhum número foi digitado à mão. Execução: [`benchmark-final.ps1`](../sqlserver/benchmark-final.ps1) ([`10_benchmark_final.sql`](../sqlserver/10_benchmark_final.sql), [`11_planos_final.sql`](../sqlserver/11_planos_final.sql), [`12_resumo_testes.sql`](../sqlserver/12_resumo_testes.sql)). Volume: 100.020 notas, 100.020 itens, 50.010 pagamentos e 100.020 conciliações sintéticas.

Método: 1 execução de aquecimento e 30 medidas por consulta e configuração, com `OPTION (RECOMPILE)` (o tempo inclui compilar o plano, igual em todas). Leituras lógicas por `SET STATISTICS IO` e plano real por `SET STATISTICS XML` (arquivos `.sqlplan`, que abrem no SSMS ou no Azure Data Studio). Todas as configurações rodaram na mesma rodada; a máquina tinha outros programas usando a CPU, então vale a comparação entre elas, não o tempo absoluto.

**Por que a configuração A mudou desde a Entrega 2** (consulta 1: 82,7 → 168,7 ms; consulta 2: 33,1 → 54,4 ms): as duas rodadas usaram as mesmas consultas, com `OPTION (RECOMPILE)`, mas não as mesmas condições. A Entrega 2 mediu 15 execuções (`evidence/parte2/benchmark-tempos.txt`); a final mediu 30, em 20/11 à tarde, com o notebook dividido com outros programas (na mesma tarde, a medida de latência da IA registrou 45% da CPU ocupada). As leituras lógicas da configuração A, que não dependem da máquina, ficaram iguais na tabela Notas (3.277 na Entrega 2 e 3.279 na final), e nas duas houve 0 leituras físicas (cache quente): os dados e o plano são os mesmos, e a diferença está no tempo de CPU disponível. Por isso cada ganho é calculado só dentro da mesma rodada, e a mediana vem sempre com o p95.

## Consulta 1: total faturado por local, provedor e mês nos últimos 12 meses

```sql
SELECT n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao), COUNT_BIG(*), SUM(n.valor_total)
FROM app.Notas AS n JOIN app.Provedores AS p ON p.id = n.provedor_id
WHERE n.data_emissao >= DATEADD(MONTH, -12, CONVERT(date, GETDATE()))
GROUP BY n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao);
```

| Configuração | Mediana (ms) | p95 (ms) | Ganho sobre A | Leituras lógicas | Custo estimado | Plano real (operadores) |
|---|---|---|---|---|---|---|
| A — linha de base (só chaves primárias) | 168,7 | 207,6 | — | 3.281 (Notas 3.279; Provedores 2) | 2,998 | Sort → Hash Match → Clustered Index Seek LocalScope.PK_LocalScope → Index Scan Provedores.UQ__Provedor__6F71C0DC31513B8B → Clustered Index Scan Notas.PK__Notas__3213E83F3E0F0356 |
| B — índices candidatos (02/11) | 157,5 | 215,8 | 1,1× | 3.281 (Notas 3.279; Provedores 2) | 3,017 | Sort → Hash Match → Clustered Index Seek LocalScope.PK_LocalScope → Index Scan Provedores.UQ__Provedor__6F71C0DC31513B8B → Clustered Index Scan Notas.PK__Notas__3213E83F3E0F0356 |
| C — índices ajustados (cobertura / filtrado) | 121,0 | 152,3 | 1,4× | 376 (Notas 374; Provedores 2) | 1,199 | Sort → Hash Match → Index Scan Provedores.UQ__Provedor__6F71C0DC31513B8B → Clustered Index Seek LocalScope.PK_LocalScope → Index Seek Notas.IX_Notas_Emissao_Cobertura |
| D — resumo diário (desnormalização) | 25,3 | 35,6 | 6,7× | 13 (ResumoDiario 11; Provedores 2) | 0,068 | Sort → Merge Join → Clustered Index Scan Provedores.PK__Provedor__3213E83FDA038CAC → Stream Aggregate → Nested Loops → Clustered Index Seek ResumoDiario.PK_ResumoDiario |

**Técnica: desnormalização.** A consulta precisa somar cerca de 47 mil notas (quase metade da tabela) a cada execução. O índice de cobertura (C) troca a varredura da tabela pela do índice, mais estreito, mas a soma continua. O resumo `app.ResumoDiario` guarda o total já somado por local, provedor e **dia** (2.190 linhas). Um gatilho em `app.Notas` mantém o resumo a cada inserção, alteração ou exclusão. O dia, e não o mês, mantém a resposta idêntica, inclusive o primeiro mês parcial da janela.

- **Mesma resposta:** 0 linhas diferentes entre a consulta nas notas e no resumo (36 linhas no resultado).
- **Por que não uma view indexada:** o SQL Server não permite view indexada sobre tabela com política de RLS, e uma soma sem filtro exporia os totais de todos os locais. O resumo entra na mesma política: cada um só lê o resumo do seu escopo.

Testes do resumo (consistência e segurança):

| Teste | Esperado | Obtido | Veredito |
|---|---|---|---|
| Resumo igual ao total recalculado depois de 50 INSERT, 15 UPDATE e 7 DELETE | 0 linhas diferentes | 0 linhas diferentes | OK |
| Operador do LOC-001 lê o resumo (só o próprio local) | LOC-001 | LOC-001 | OK |
| API com escopo nos três locais lê o resumo | LOC-001,LOC-002,LOC-003 | LOC-001,LOC-002,LOC-003 | OK |
| IA lê o resumo direto | negado | negado (229) | OK |
| Operador altera o resumo direto (forjar total) | negado | negado (229) | OK |

**O preço:** o gatilho deixa a gravação mais lenta.

| Gravação | Sem gatilho | Com gatilho |
|---|---|---|
| Lote de 1.000 notas | 55,0 ms | 128,8 ms |
| Uma nota por vez (como a API grava), por nota | 0,09 ms | 0,70 ms |

No SIGp chegam algumas notas por dia, por e-mail, e o relatório é lido muitas vezes: menos de 1 ms a mais por nota gravada compensa. Se a carga de gravação crescer muito, a alternativa é atualizar o resumo em lote, fora do horário.

## Consulta 2: as 500 notas pendentes vencidas mais antigas sem conciliação concluída

```sql
SELECT TOP (500) n.id, n.local_id, n.provedor_id, n.valor_total, n.vencimento, n.status
FROM app.Notas AS n
WHERE n.status = N'PENDENTE' AND n.vencimento < CONVERT(date, GETDATE())
  AND NOT EXISTS (SELECT 1 FROM app.Conciliacoes AS c WHERE c.nota_id = n.id AND c.status = N'CONCILIADA')
ORDER BY n.vencimento, n.id;
```

| Configuração | Mediana (ms) | p95 (ms) | Ganho sobre A | Leituras lógicas | Custo estimado | Plano real (operadores) |
|---|---|---|---|---|---|---|
| A — linha de base (só chaves primárias) | 54,4 | 73,8 | — | 4.956 (Conciliacoes 1.677; Notas 3.279) | 4,934 | Sort → Hash Match → Clustered Index Seek LocalScope.PK_LocalScope → Merge Join → Clustered Index Scan Notas.PK__Notas__3213E83F3E0F0356 → Clustered Index Scan Conciliacoes.PK__Concilia__3213E83F7D0B53F6 |
| B — índices candidatos (02/11) | 64,1 | 86,5 | 0,8× | 3.818 (Conciliacoes 539; Notas 3.279) | 4,159 | Sort → Hash Match → Clustered Index Seek LocalScope.PK_LocalScope → Merge Join → Clustered Index Scan Notas.PK__Notas__3213E83F3E0F0356 → Index Scan Conciliacoes.IX_Conciliacoes_Nota_Status |
| C — índices ajustados (cobertura / filtrado) | 10,7 | 16,8 | 5,1× | 1.012 (Worktable 1.005; Notas 7) | 0,206 | Top → Nested Loops → Index Seek Notas.IX_Notas_Pendentes_Vencimento → Table Spool → Index Scan Conciliacoes.IX_Conciliacoes_Concluidas → Clustered Index Seek LocalScope.PK_LocalScope |

**Técnica: índice filtrado.** `IX_Notas_Pendentes_Vencimento (vencimento, id) INCLUDE (...) WHERE status = 'PENDENTE'` guarda só as notas pendentes, já na ordem pedida: a consulta lê as primeiras linhas e para no TOP (500), sem ordenar a tabela. `IX_Conciliacoes_Concluidas (nota_id) WHERE status = 'CONCILIADA'` deixa o NOT EXISTS conferir um índice pequeno. Os índices candidatos de 02/11 (B) não ajudavam: a ordem das colunas (local, vencimento, status) não servia a esta consulta, que não filtra por local.

## Resumo

| Consulta | Técnica | Antes (A) | Depois | Leituras lógicas |
|---|---|---|---|---|
| 1 | Desnormalização (resumo diário com gatilho e RLS) | 168,7 ms | 25,3 ms | 3.281 → 13 |
| 2 | Índice filtrado | 54,4 ms | 10,7 ms | 4.956 → 1.012 (só 7 nas notas; o resto é a tabela de trabalho do Table Spool) |

Histórico das tentativas (o índice de cobertura que não bastou para a consulta 1) em [`../historico-evolucao.md`](../historico-evolucao.md), item H-19.
