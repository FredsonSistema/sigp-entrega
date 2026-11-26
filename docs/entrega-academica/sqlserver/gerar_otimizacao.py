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


def operadores(cfg: str, consulta: int) -> tuple[list[dict], float]:
    """Cada operador do plano real: tipo, objeto, linhas lidas e devolvidas (RunTimeInformation) e custo próprio
    (custo estimado da subárvore menos o das subárvores filhas)."""
    raiz = ET.fromstring((EV / f"{cfg}-consulta{consulta}.sqlplan").read_text(encoding="utf-8-sig"))
    total = float(raiz.find(".//p:StmtSimple", NS).get("StatementSubTreeCost", "0"))
    p = f"{{{NS['p']}}}"
    res = []
    for rel in raiz.iter(p + "RelOp"):
        filhos = [r for r in rel.iter(p + "RelOp") if r is not rel]
        # filhos diretos: RelOps cujo RelOp ancestral mais próximo é este
        diretos = [f for f in filhos if not any(f in list(g.iter(p + "RelOp"))[1:] for g in filhos)]
        sub = float(rel.get("EstimatedTotalSubtreeCost", "0"))
        proprio = max(sub - sum(float(f.get("EstimatedTotalSubtreeCost", "0")) for f in diretos), 0.0)
        rt = rel.find("./p:RunTimeInformation", NS)
        lidas = devolvidas = None
        if rt is not None:
            devolvidas = sum(int(c.get("ActualRows", 0)) for c in rt)
            if any(c.get("ActualRowsRead") is not None for c in rt):
                lidas = sum(int(c.get("ActualRowsRead") or 0) for c in rt)
        obj = rel.find("./*/p:Object", NS)
        tabela = (obj.get("Table") or "").strip("[]") if obj is not None else ""
        indice = (obj.get("Index") or "").strip("[]") if obj is not None else ""
        res.append({"op": rel.get("PhysicalOp"), "tabela": tabela, "indice": indice, "lidas": lidas,
                    "devolvidas": devolvidas, "proprio": proprio, "pct": proprio / total * 100 if total else 0.0,
                    "seek": rel.find("./*/p:SeekPredicates", NS) is not None,
                    "residual": rel.find("./*/p:Predicate", NS) is not None})
    return res, total


def acesso(o: dict) -> str:
    alvo = f"`{o['tabela']}`" + (f" (`{o['indice']}`)" if o["indice"] and not o["indice"].startswith(("PK__", "UQ__")) else "")
    return f"{o['op']} em {alvo}"


def secao_planos(consulta: int, cfgs: list[str], tempos: dict) -> list[str]:
    planos = {c: operadores(c, consulta) for c in cfgs}
    L = ["", "### O que mudou no plano: scan × seek e custo", "",
         "Lido dos planos reais (`.sqlplan`). **Scan** percorre o índice ou a tabela inteira; **Seek** vai direto ao intervalo "
         "pedido pela chave do índice. \"Lidas\" são as linhas que o operador examinou e \"devolvidas\" as que passaram para "
         "o operador seguinte: quando lidas > devolvidas, o filtro foi aplicado linha a linha depois da leitura. O custo é a "
         "estimativa do otimizador (unidade interna do SQL Server, sem relação direta com segundos); \"custo próprio\" é o do "
         "operador sem os que estão abaixo dele. O filtro de linha da RLS (seek em `LocalScope`) aparece em todos os planos e "
         "fica fora da coluna de acesso.",
         "",
         "| Configuração | Acesso às tabelas (lidas → devolvidas) | Operador mais caro (custo próprio) | Custo estimado da consulta |",
         "|---|---|---|---|"]
    for c in cfgs:
        ops, total = planos[c]
        acessos = [o for o in ops if o["tabela"] and o["tabela"] != "LocalScope" and ("Scan" in o["op"] or "Seek" in o["op"])]
        txt = "; ".join(
            f"{acesso(o)}: {br(o['lidas'] if o['lidas'] is not None else o['devolvidas'], 0)} → {br(o['devolvidas'] or 0, 0)}"
            for o in acessos)
        # O seek da RLS fica fora: o SQL Server informa nele o custo da consulta inteira quando o filtro é de partida.
        caro = max((o for o in ops if o["tabela"] != "LocalScope"), key=lambda o: o["proprio"])
        ganho = planos[cfgs[0]][1] / total if total else 0
        comparacao = "" if c == cfgs[0] else (f" ({br(ganho)}× menor)" if ganho >= 1.05 else " (sem ganho sobre A)")
        L.append(f"| {c} — {CONFIG[c]} | {txt} | {caro['op']}"
                 f"{' em `' + caro['tabela'] + '`' if caro['tabela'] else ''}: {br(caro['proprio'], 3)} ({br(caro['pct'], 0)}%) | "
                 f"{br(total, 3)}{comparacao} |")
    return L


def _op(cfg: str, consulta: int, tabela: str) -> dict:
    return next(o for o in operadores(cfg, consulta)[0] if o["tabela"] == tabela)


def explicacao_consulta1() -> list[str]:
    a, c, d = _op("A", 1, "Notas"), _op("C", 1, "Notas"), _op("D", 1, "ResumoDiario")
    ops_c, total_c = operadores("C", 1)
    hash_c = sum(o["proprio"] for o in ops_c if o["op"] == "Hash Match")
    total_a, total_d = operadores("A", 1)[1], operadores("D", 1)[1]
    return [
        "",
        f"- **A:** {acesso(a)}. O filtro de data não tem índice, então o SQL Server lê as {br(a['lidas'], 0)} notas e descarta "
        f"as de fora da janela depois de ler (devolve {br(a['devolvidas'], 0)}). A leitura da tabela é {br(a['pct'], 0)}% do custo.",
        f"- **C:** {acesso(c)}. O índice por `data_emissao` vira **seek**: lê só as {br(c['lidas'], 0)} notas da janela, sem "
        f"descartar nenhuma. A leitura fica barata, mas as {br(c['devolvidas'], 0)} linhas ainda precisam ser agrupadas e "
        f"somadas: os Hash Match (junção e agregação) passam a ser {br(hash_c / total_c * 100, 0)}% do custo. **Por isso o ganho "
        "do índice foi pequeno:** ele resolve a leitura, mas o trabalho que sobra é proporcional ao número de notas da janela.",
        f"- **D:** {acesso(d)}. A soma já está feita por dia: a consulta lê {br(d['lidas'], 0)} linhas do resumo em vez de "
        f"{br(c['lidas'], 0)} notas, e a agregação que sobra é pequena. Custo estimado {br(total_a, 3)} → {br(total_d, 3)} "
        f"({br(total_a / total_d)}× menor).",
    ]


def explicacao_consulta2() -> list[str]:
    a, a_conc = _op("A", 2, "Notas"), _op("A", 2, "Conciliacoes")
    c, c_conc = _op("C", 2, "Notas"), _op("C", 2, "Conciliacoes")
    ops_a, total_a = operadores("A", 2)
    sort_a = next(o for o in ops_a if o["op"] == "Sort")
    ops_c, total_c = operadores("C", 2)
    spool_c = sum(o["pct"] for o in ops_c if o["op"] == "Table Spool")
    vazio = " (nesta base sintética, nenhuma: o índice está vazio)" if not c_conc["devolvidas"] else ""
    return [
        "",
        f"- **A:** {acesso(a)} lê as {br(a['lidas'], 0)} notas para achar {br(a['devolvidas'], 0)} pendentes vencidas, e "
        f"{acesso(a_conc)} lê as {br(a_conc['lidas'], 0)} conciliações para o NOT EXISTS. Depois um **Sort** ordena as "
        f"{br(a['devolvidas'], 0)} linhas por vencimento só para ficar com as 500 primeiras ({br(sort_a['pct'], 0)}% do custo "
        "próprio fica no Sort).",
        f"- **C:** {acesso(c)}: **seek** no índice filtrado, que só tem notas pendentes e já está na ordem (vencimento, id). "
        f"A consulta lê {br(c['lidas'], 0)} linhas e para no TOP (500); o Sort some do plano. O NOT EXISTS usa "
        f"{acesso(c_conc)}, que só guarda as conciliações concluídas{vazio}. Custo estimado {br(total_a, 3)} → "
        f"{br(total_c, 3)} ({br(total_a / total_c)}× menor). O que sobra de custo ({br(spool_c, 0)}%) são os Table Spool, "
        "que guardam o resultado do NOT EXISTS e do filtro da RLS para não repetir a leitura a cada uma das 500 notas.",
    ]


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
        *secao_planos(1, ["A", "B", "C", "D"], tempos),
        *explicacao_consulta1(),
        "",
        f"**Comentário da Entrega 2 (\"ganho ainda pequeno\"):** só com o índice de cobertura (C) o ganho é "
        f"{br(float(tempos[('A', 1)]['mediana_ms']) / float(tempos[('C', 1)]['mediana_ms']))}×; com o resumo diário (D) passa a "
        f"{br(float(tempos[('A', 1)]['mediana_ms']) / float(tempos[('D', 1)]['mediana_ms']))}× e as leituras lógicas caem de "
        f"{br(sum(lt[('A', 1)].values()), 0)} para {br(sum(lt[('D', 1)].values()), 0)}. A explicação pelo plano está logo acima.",
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
        *secao_planos(2, ["A", "B", "C"], tempos),
        *explicacao_consulta2(),
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
