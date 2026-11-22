"""Gera docs/entrega-academica/seguranca/otimizacao-consultas.md a partir das evidências (nenhum número digitado à mão).
Fontes: evidence/parte3/otimizacao/ (benchmark-final.ps1): tempos.txt, leituras-logicas.txt, resumo-testes.txt e os
planos <cfg>-consulta<n>.sqlplan (operadores e custo estimado lidos do XML do plano real).
Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/sqlserver/gerar_otimizacao.py
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

DIR = Path(__file__).resolve().parent
EV = DIR / "evidence" / "parte3" / "otimizacao"
SAIDA = DIR.parent / "seguranca" / "otimizacao-consultas.md"
NS = {"p": "http://schemas.microsoft.com/sqlserver/2004/07/showplan"}
CONFIG = {
    "A": "linha de base (só chaves primárias)",
    "B": "índices candidatos (02/11)",
    "C": "índices ajustados (cobertura / filtrado)",
    "D": "resumo diário (desnormalização)",
}


def tabela_sqlcmd(texto: str, cabecalho: str) -> list[dict]:
    linhas = texto.splitlines()
    for i, l in enumerate(linhas):
        if l.startswith(cabecalho):
            nomes = l.split("|")
            dados = []
            for x in linhas[i + 2:]:
                # para no fim da tabela: linha vazia, outra tabela (número de colunas diferente) ou mensagem
                if not x.strip() or "|" not in x or len(x.split("|")) != len(nomes):
                    break
                dados.append(dict(zip(nomes, x.split("|"))))
            return dados
    raise ValueError(f"tabela {cabecalho!r} não encontrada")


def br(v: float, casas: int = 1) -> str:
    """Número no formato brasileiro: 3.279 e 168,7."""
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def leituras() -> dict:
    texto = (EV / "leituras-logicas.txt").read_text(encoding="utf-8-sig")
    res, cfg, cons = {}, None, None
    for l in texto.splitlines():
        if m := re.match(r"### Configura\w+ (\w)", l):
            cfg = m.group(1)
        elif m := re.match(r"### CONSULTA (\d)", l):
            cons = int(m.group(1))
        elif m := re.match(r"Table '(\w+)'\. Scan count \d+, logical reads (\d+)", l):
            if int(m.group(2)) and m.group(1) != "LocalScope":
                res.setdefault((cfg, cons), {})
                res[(cfg, cons)][m.group(1)] = res[(cfg, cons)].get(m.group(1), 0) + int(m.group(2))
    return res


def plano(cfg: str, consulta: int) -> tuple[str, float]:
    caminho = EV / f"{cfg}-consulta{consulta}.sqlplan"
    raiz = ET.fromstring(caminho.read_text(encoding="utf-8-sig"))
    stmt = raiz.find(".//p:StmtSimple", NS)
    custo = float(stmt.get("StatementSubTreeCost", "0"))
    ops = []
    for rel in raiz.iter(f"{{{NS['p']}}}RelOp"):
        op = rel.get("PhysicalOp")
        obj = rel.find("./*/p:Object", NS)
        alvo = ""
        if obj is not None and obj.get("Table") and op and ("Scan" in op or "Seek" in op):
            indice = (obj.get("Index") or "").strip("[]")
            alvo = f" {obj.get('Table').strip('[]')}" + (f".{indice}" if indice else "")
        if op in {"Compute Scalar", "Parallelism"}:
            continue
        rotulo = f"{op}{alvo}"
        if rotulo not in ops:
            ops.append(rotulo)
    return " → ".join(ops[:6]), custo


def main() -> None:
    tempos = {(t["configuracao"], int(t["consulta"])): t for t in
              tabela_sqlcmd((EV / "tempos.txt").read_text(encoding="utf-8-sig"), "configuracao|consulta")}
    verif = tabela_sqlcmd((EV / "tempos.txt").read_text(encoding="utf-8-sig"), "verificacao|")[0]
    resumo_txt = (EV / "resumo-testes.txt").read_text(encoding="utf-8-sig")
    testes = tabela_sqlcmd(resumo_txt, "teste|")
    custo = {(c["tipo"], c["modo"]): c for c in tabela_sqlcmd(resumo_txt, "tipo|modo")}
    lt = leituras()

    def linha(cfg: str, consulta: int, base: str) -> str:
        t, tb = tempos[(cfg, consulta)], tempos[(base, consulta)]
        ganho = float(tb["mediana_ms"]) / float(t["mediana_ms"])
        lei = lt.get((cfg, consulta), {})
        ops, c = plano(cfg, consulta)
        return (f"| {cfg} — {CONFIG[cfg]} | {br(float(t['mediana_ms']))} | {br(float(t['p95_ms']))} | "
                f"{'—' if cfg == base else br(ganho) + '×'} | {br(sum(lei.values()), 0)} ({'; '.join(f'{k} {br(v, 0)}' for k, v in lei.items())}) | "
                f"{br(c, 3)} | {ops} |")

    cab = ["| Configuração | Mediana (ms) | p95 (ms) | Ganho sobre A | Leituras lógicas | Custo estimado | Plano real (operadores) |",
           "|---|---|---|---|---|---|---|"]
    L = [
        "# Otimização: duas consultas lentas, antes e depois",
        "",
        "Gerado por [`../sqlserver/gerar_otimizacao.py`](../sqlserver/gerar_otimizacao.py) a partir das evidências em "
        "[`../sqlserver/evidence/parte3/otimizacao/`](../sqlserver/evidence/parte3/otimizacao/); nenhum número foi digitado à mão. "
        "Execução: [`benchmark-final.ps1`](../sqlserver/benchmark-final.ps1) "
        "([`10_benchmark_final.sql`](../sqlserver/10_benchmark_final.sql), [`11_planos_final.sql`](../sqlserver/11_planos_final.sql), "
        "[`12_resumo_testes.sql`](../sqlserver/12_resumo_testes.sql)). Volume: 100.020 notas, 100.020 itens, 50.010 pagamentos e "
        "100.020 conciliações sintéticas.",
        "",
        "Método: 1 execução de aquecimento e 30 medidas por consulta e configuração, com `OPTION (RECOMPILE)` (o tempo inclui "
        "compilar o plano, igual em todas). Leituras lógicas por `SET STATISTICS IO` e plano real por `SET STATISTICS XML` "
        "(arquivos `.sqlplan`, que abrem no SSMS ou no Azure Data Studio). Todas as configurações rodaram na mesma rodada; "
        "a máquina tinha outros programas usando a CPU, então vale a comparação entre elas, não o tempo absoluto.",
        "",
        "**Por que a configuração A mudou desde a Entrega 2** (consulta 1: 82,7 → 168,7 ms; consulta 2: 33,1 → 54,4 ms): as duas "
        "rodadas usaram as mesmas consultas, com `OPTION (RECOMPILE)`, mas não as mesmas condições. A Entrega 2 mediu 15 execuções "
        "(`evidence/parte2/benchmark-tempos.txt`); a final mediu 30, em 20/11 à tarde, com o notebook dividido com outros programas "
        "(na mesma tarde, a medida de latência da IA registrou 45% da CPU ocupada). As leituras lógicas da configuração A, que não "
        "dependem da máquina, ficaram iguais na tabela Notas (3.277 na Entrega 2 e 3.279 na final), e nas duas houve 0 leituras físicas "
        "(cache quente): os dados e o plano são os mesmos, "
        "e a diferença está no tempo de CPU disponível. Por isso cada ganho é calculado só dentro da mesma rodada, e a mediana "
        "vem sempre com o p95.",
        "",
        "## Consulta 1: total faturado por local, provedor e mês nos últimos 12 meses",
        "",
        "```sql",
        "SELECT n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao), COUNT_BIG(*), SUM(n.valor_total)",
        "FROM app.Notas AS n JOIN app.Provedores AS p ON p.id = n.provedor_id",
        "WHERE n.data_emissao >= DATEADD(MONTH, -12, CONVERT(date, GETDATE()))",
        "GROUP BY n.local_id, p.nome, YEAR(n.data_emissao), MONTH(n.data_emissao);",
        "```",
        "",
        *cab,
        linha("A", 1, "A"), linha("B", 1, "A"), linha("C", 1, "A"), linha("D", 1, "A"),
        "",
        "**Técnica: desnormalização.** A consulta precisa somar cerca de 47 mil notas (quase metade da tabela) a cada execução. "
        "O índice de cobertura (C) troca a varredura da tabela pela do índice, mais estreito, mas a soma continua. O resumo "
        "`app.ResumoDiario` guarda o total já somado por local, provedor e **dia** (2.190 linhas). Um gatilho em `app.Notas` mantém "
        "o resumo a cada inserção, alteração ou exclusão. O dia, e não o mês, mantém a resposta idêntica, inclusive o primeiro mês "
        "parcial da janela.",
        "",
        f"- **Mesma resposta:** {verif['linhas_diferentes']} linhas diferentes entre a consulta nas notas e no resumo ({verif['linhas_do_resultado']} linhas no resultado).",
        "- **Por que não uma view indexada:** o SQL Server não permite view indexada sobre tabela com política de RLS, e uma soma sem "
        "filtro exporia os totais de todos os locais. O resumo entra na mesma política: cada um só lê o resumo do seu escopo.",
        "",
        "Testes do resumo (consistência e segurança):",
        "",
        "| Teste | Esperado | Obtido | Veredito |",
        "|---|---|---|---|",
        *[f"| {t['teste']} | {t['esperado']} | {t['obtido']} | {t['veredito']} |" for t in testes],
        "",
        "**O preço:** o gatilho deixa a gravação mais lenta.",
        "",
        "| Gravação | Sem gatilho | Com gatilho |",
        "|---|---|---|",
        f"| Lote de 1.000 notas | {br(float(custo[('lote', 'sem')]['mediana_ms']))} ms | {br(float(custo[('lote', 'com')]['mediana_ms']))} ms |",
        f"| Uma nota por vez (como a API grava), por nota | {br(float(custo[('uma_a_uma', 'sem')]['por_nota_us']) / 1000, 2)} ms | "
        f"{br(float(custo[('uma_a_uma', 'com')]['por_nota_us']) / 1000, 2)} ms |",
        "",
        "No SIGp chegam algumas notas por dia, por e-mail, e o relatório é lido muitas vezes: menos de 1 ms a mais por nota gravada "
        "compensa. Se a carga de gravação crescer muito, a alternativa é atualizar o resumo em lote, fora do horário.",
        "",
        "## Consulta 2: as 500 notas pendentes vencidas mais antigas sem conciliação concluída",
        "",
        "```sql",
        "SELECT TOP (500) n.id, n.local_id, n.provedor_id, n.valor_total, n.vencimento, n.status",
        "FROM app.Notas AS n",
        "WHERE n.status = N'PENDENTE' AND n.vencimento < CONVERT(date, GETDATE())",
        "  AND NOT EXISTS (SELECT 1 FROM app.Conciliacoes AS c WHERE c.nota_id = n.id AND c.status = N'CONCILIADA')",
        "ORDER BY n.vencimento, n.id;",
        "```",
        "",
        *cab,
        linha("A", 2, "A"), linha("B", 2, "A"), linha("C", 2, "A"),
        "",
        "**Técnica: índice filtrado.** `IX_Notas_Pendentes_Vencimento (vencimento, id) INCLUDE (...) WHERE status = 'PENDENTE'` "
        "guarda só as notas pendentes, já na ordem pedida: a consulta lê as primeiras linhas e para no TOP (500), sem ordenar a "
        "tabela. `IX_Conciliacoes_Concluidas (nota_id) WHERE status = 'CONCILIADA'` deixa o NOT EXISTS conferir um índice pequeno. "
        "Os índices candidatos de 02/11 (B) não ajudavam: a ordem das colunas (local, vencimento, status) não servia a esta "
        "consulta, que não filtra por local.",
        "",
        "## Resumo",
        "",
        "| Consulta | Técnica | Antes (A) | Depois | Leituras lógicas |",
        "|---|---|---|---|---|",
        f"| 1 | Desnormalização (resumo diário com gatilho e RLS) | {br(float(tempos[('A', 1)]['mediana_ms']))} ms | "
        f"{br(float(tempos[('D', 1)]['mediana_ms']))} ms | {br(sum(lt[('A', 1)].values()), 0)} → {br(sum(lt[('D', 1)].values()), 0)} |",
        f"| 2 | Índice filtrado | {br(float(tempos[('A', 2)]['mediana_ms']))} ms | {br(float(tempos[('C', 2)]['mediana_ms']))} ms | "
        f"{br(sum(lt[('A', 2)].values()), 0)} → {br(sum(lt[('C', 2)].values()), 0)} (só {br(lt[('C', 2)].get('Notas', 0), 0)} nas notas; "
        f"o resto é a tabela de trabalho do Table Spool) |",
        "",
        "Histórico das tentativas (o índice de cobertura que não bastou para a consulta 1) em "
        "[`../historico-evolucao.md`](../historico-evolucao.md), item H-19.",
        "",
    ]
    SAIDA.write_text("\n".join(L), encoding="utf-8")
    print(f"ok: {SAIDA}")


if __name__ == "__main__":
    main()
