"""Avaliação de vulnerabilidades do SQL Server acadêmico (estilo SQL Vulnerability Assessment e CIS Benchmark).

  python docs/entrega-academica/seguranca/avaliar_vulnerabilidades.py antes      # roda e grava ...-antes.json
  python docs/entrega-academica/seguranca/avaliar_vulnerabilidades.py depois     # depois do corrigir-vulnerabilidades.ps1
  python docs/entrega-academica/seguranca/avaliar_vulnerabilidades.py documento  # gera avaliacao-vulnerabilidades.md

O 18_avaliacao_vulnerabilidades.sql só lê (PASSOU/FALHOU e o detalhe de cada regra). Aqui ficam os riscos ACEITOS, cada
um com a justificativa e a compensação: aceitar é uma decisão escrita, não um teste que passou.
A conexão é feita como um cliente de fora (sqlcmd do Windows, TCP, sem pedir criptografia), para a regra V27 medir se o
servidor EXIGE TLS. A senha do sa vem do .env.academic e vai ao sqlcmd por variável de ambiente; nunca é gravada.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
SQL = ENTREGA / "sqlserver"
EV = SQL / "evidence" / "parte3"
DOC = Path(__file__).resolve().parent / "avaliacao-vulnerabilidades.md"
SERVIDOR = os.environ.get("SIGP_SQL_SERVIDOR", "127.0.0.1,14333")

ACEITOS = {
    "V10": ("O sa só é usado pelo instalador e pelos scripts de prova, com senha aleatória de 37 caracteres guardada no "
            ".env.academic (fora do Git), e a porta do SQL Server só abre em 127.0.0.1. A aplicação e a IA nunca usam o sa: "
            "cada uma tem usuário próprio, sem permissão direta em tabela (V20). Desativar o sa exige um login "
            "administrativo próprio em todos os scripts: fica como próximo passo."),
    "V13": ("Necessária por desenho: os usuários da IA existem só dentro do SIGpAcademic (banco contido), sem login na "
            "instância, então uma credencial vazada não abre nenhum outro banco nem a instância. Compensações: os usuários "
            "da IA só executam o procedimento (V20), a RLS limita ao próprio local (V22) e toda tentativa fica na auditoria "
            "(V25, V26)."),
}


def senha() -> str:
    for linha in (SQL / ".env.academic").read_text(encoding="utf-8").splitlines():
        if linha.startswith("MSSQL_SA_PASSWORD="):
            return linha.split("=", 1)[1].strip()
    raise SystemExit("MSSQL_SA_PASSWORD não está no .env.academic")


def avaliar() -> list[dict]:
    r = subprocess.run(["sqlcmd", "-S", SERVIDOR, "-U", "sa", "-d", "master", "-C", "-I", "-f", "65001", "-y", "0",
                        "-i", str(SQL / "18_avaliacao_vulnerabilidades.sql")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "SQLCMDPASSWORD": os.environ.get("SIGP_SQL_SENHA_SA") or senha()}, timeout=120)
    linha = next((l.strip() for l in r.stdout.splitlines() if l.strip().startswith("[")), "")
    if r.returncode or not linha:
        raise SystemExit("a avaliação não devolveu o resultado:\n" + (r.stdout + r.stderr)[:800])
    regras = json.loads(linha)
    for x in regras:
        x["passou"] = bool(x["passou"])
        if x["passou"]:
            x["resultado"] = "PASSOU"
        elif x["id"] in ACEITOS:
            x["resultado"], x["justificativa"] = "ACEITO", ACEITOS[x["id"]]
        else:
            x["resultado"] = "FALHOU"
    return regras


def gravar(rotulo: str) -> None:
    regras = avaliar()
    contagem = {k: sum(1 for x in regras if x["resultado"] == k) for k in ("PASSOU", "ACEITO", "FALHOU")}
    saida = {"executado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rotulo": rotulo,
             "servidor": SERVIDOR, "versao_sql_server": regras[0].get("versao") if regras else "",
             "resumo": contagem, "regras": [{k: v for k, v in x.items() if k != "versao"} for x in regras]}
    destino = EV / f"vulnerabilidades-{rotulo}.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for x in regras:
        print(f"  {x['id']} {x['resultado']:<6} {x['regra'][:70]} · {x['detalhe']}")
    print(f"{rotulo}: {contagem['PASSOU']} passaram, {contagem['ACEITO']} aceitos com justificativa, {contagem['FALHOU']} falharam -> {destino.name}")


def documento() -> None:
    antes = json.loads((EV / "vulnerabilidades-antes.json").read_text(encoding="utf-8"))
    depois = json.loads((EV / "vulnerabilidades-depois.json").read_text(encoding="utf-8"))
    por_id = {x["id"]: x for x in antes["regras"]}
    linhas = [
        "# Avaliação de vulnerabilidades do SQL Server acadêmico",
        "",
        "Gerado por `seguranca/avaliar_vulnerabilidades.py` a partir de `sqlserver/evidence/parte3/vulnerabilidades-antes.json` e "
        "`vulnerabilidades-depois.json`; nenhum número foi digitado à mão.",
        "",
        f"Regras no estilo do **SQL Vulnerability Assessment** (Microsoft, códigos VA) e do **CIS Microsoft SQL Server Benchmark** "
        f"(códigos CIS), mais as proteções próprias do projeto (RLS, mascaramento, ledger, TDE). SQL Server {depois['versao_sql_server']}. "
        "A consulta (`sqlserver/18_avaliacao_vulnerabilidades.sql`) só lê; as correções estão em `19_correcoes_vulnerabilidades.sql` e "
        "`corrigir-vulnerabilidades.ps1` (reinicia o SQL Server para o TLS obrigatório e o acesso remoto valerem). "
        "A conexão da avaliação é a de um cliente de fora (sqlcmd do Windows, TCP, sem pedir criptografia): a regra V27 mostra se o "
        "servidor exige TLS.",
        "",
        "| | Antes | Depois |",
        "|---|---|---|",
        f"| Passaram | {antes['resumo']['PASSOU']} | {depois['resumo']['PASSOU']} |",
        f"| Riscos aceitos, com justificativa | {antes['resumo']['ACEITO']} | {depois['resumo']['ACEITO']} |",
        f"| Falharam | {antes['resumo']['FALHOU']} | {depois['resumo']['FALHOU']} |",
        f"| Execução (UTC) | {antes['executado_em_utc']} | {depois['executado_em_utc']} |",
        "",
        "| Regra | Área | Referência | Antes | Depois | Detalhe depois |",
        "|---|---|---|---|---|---|",
    ]
    for x in depois["regras"]:
        a = por_id.get(x["id"], {})
        # A 1ª rodada (sem TLS) perdeu o separador "·" na leitura do sqlcmd (virou U+FFFD); só a exibição troca por "/".
        a = {**a, "detalhe": str(a.get("detalhe", "")).replace("\ufffd", "/")}
        marca = " **(corrigida)**" if a.get("resultado") == "FALHOU" and x["resultado"] == "PASSOU" else ""
        linhas.append(f"| {x['id']} {x['regra']} | {x['area']} | {x['referencia']} | {a.get('resultado', '—')} ({a.get('detalhe', '')}) | "
                      f"{x['resultado']}{marca} | {x['detalhe']} |")
    linhas += ["", "## Riscos aceitos", ""]
    for x in depois["regras"]:
        if x["resultado"] == "ACEITO":
            linhas.append(f"- **{x['id']} {x['regra']}.** {x['justificativa']}")
    falhas = [x for x in depois["regras"] if x["resultado"] == "FALHOU"]
    linhas += ["", "## Falhas restantes", "", "Nenhuma." if not falhas else
               "\n".join(f"- **{x['id']} {x['regra']}:** {x['detalhe']}" for x in falhas), ""]
    DOC.write_text("\n".join(linhas), encoding="utf-8")
    print(f"ok: {DOC}")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "antes"
    documento() if modo == "documento" else gravar(modo)
