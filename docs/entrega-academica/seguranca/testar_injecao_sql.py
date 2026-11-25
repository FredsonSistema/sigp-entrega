"""Injeção de SQL contra o SIGp acadêmico, em três níveis, com o banco conferido antes e depois de cada ataque.

1. API da IA (caixa preta): ataques clássicos de injeção, comandos empilhados, comentários, aspas Unicode, variáveis do
   sqlcmd ($(...)), quebra de linha com comando do sqlcmd (:!!), texto gigante e campos extras. Esperado: nenhum erro de
   SQL, nenhuma linha alterada, nenhuma senha na trilha, resposta só com as classificações permitidas (ou 400).
2. Procedimentos da IA, chamados direto com o usuário da IA (sigp_ia_loc001), com parâmetros maliciosos e o local de
   outro escopo. Esperado: nada executa além do procedimento, nada de outro local volta. E uma varredura: nenhum
   procedimento dos schemas ai e app monta SQL dinâmico (EXEC(@...) ou sp_executesql).
3. A primitiva que a API usa para falar com o banco (_sqlcmd): ela não pode trocar $(VARIÁVEL) pelo valor da variável de
   ambiente. Antes da correção, $(SIGP_AI_API_KEY) virava a chave da API da IA (64 caracteres) e $(HOME) a pasta do
   usuário; só o tamanho é medido, o valor nunca é lido. ($(SQLCMDPASSWORD) o próprio sqlcmd não troca.)

Saída: sqlserver/evidence/parte3/injecao-sql-<rótulo>.json (rótulo: 1º argumento, padrão "atual").
Uso, na raiz do projeto:  python docs/entrega-academica/seguranca/testar_injecao_sql.py antes|depois
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
SQL = ENTREGA / "sqlserver"
EV = SQL / "evidence" / "parte3"
API = "http://127.0.0.1:5010/api/analyze"
ENV = dict(l.split("=", 1) for l in (SQL / ".env.academic").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
ENV = {k.strip(): v.strip() for k, v in ENV.items()}
SENHAS = [v for k, v in ENV.items() if "PASSWORD" in k and v]
PERMITIDAS = {"CONTRATADO", "DIVERGENTE", "REVISAR"}


def sql_sa(consulta: str, banco: str = "SIGpAcademic") -> str:
    r = subprocess.run(["sqlcmd", "-S", "127.0.0.1,14333", "-U", "sa", "-d", banco, "-C", "-b", "-y", "0", "-x", "-Q", "SET NOCOUNT ON; " + consulta],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "SQLCMDPASSWORD": ENV["MSSQL_SA_PASSWORD"]}, timeout=120)
    if r.returncode:
        raise RuntimeError(r.stdout + r.stderr)
    return r.stdout


def retrato() -> dict:
    """O que um ataque bem-sucedido mudaria: linhas das tabelas, membros do sysadmin, permissões da IA, objetos."""
    txt = sql_sa(
        "SELECT n, c FROM (SELECT 'Notas' n, COUNT(*) c FROM app.Notas UNION ALL SELECT 'Pagamentos', COUNT(*) FROM app.Pagamentos "
        "UNION ALL SELECT 'Locais', COUNT(*) FROM app.Locais UNION ALL SELECT 'Provedores', COUNT(*) FROM app.Provedores "
        "UNION ALL SELECT 'Objetos', COUNT(*) FROM sys.objects WHERE is_ms_shipped = 0 "
        "UNION ALL SELECT 'PermissoesIA', COUNT(*) FROM sys.database_permissions p JOIN sys.database_principals u ON u.principal_id = p.grantee_principal_id WHERE u.name LIKE 'sigp_ia%' "
        "UNION ALL SELECT 'Sysadmin', COUNT(*) FROM sys.server_role_members WHERE role_principal_id = SUSER_ID('sysadmin')) x FOR JSON PATH;")
    linha = next(l for l in txt.splitlines() if l.strip().startswith("["))
    return {x["n"]: x["c"] for x in json.loads(linha)}


def eventos_desde(id_inicial: int) -> str:
    return sql_sa(f"SELECT ator, acao, objeto, detalhe_redigido FROM audit.Eventos WHERE id > {int(id_inicial)};")


def ultimo_evento() -> int:
    txt = sql_sa("SELECT MAX(id) FROM audit.Eventos;")
    return int(next(l for l in txt.splitlines() if l.strip().isdigit()).strip())


def analisar(invoice: dict) -> tuple[int, dict]:
    corpo = json.dumps({"invoice": invoice}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API, data=corpo, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "X-API-Key": ENV["SIGP_AI_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        corpo = e.read() or b"{}"
        try:
            return e.code, json.loads(corpo)
        except json.JSONDecodeError:  # ex.: 413 do servidor web, com página em HTML
            return e.code, {"error": corpo.decode("utf-8", "replace")[:160]}


ATAQUES_API = [
    ("aspas e comando empilhado", {"provider": "Conecta Alfa Fictícia'; DROP TABLE app.Notas; --", "description": "link principal fibra 300 Mbps", "amount": "450.00"}),
    ("escalar privilégio", {"provider": "Conecta Alfa Fictícia", "description": "x'; EXEC sp_addsrvrolemember 'sigp_ia_loc001','sysadmin'; --", "amount": "450.00"}),
    ("OR 1=1 com comentário", {"provider": "x'/**/OR/**/1=1--", "description": "link principal fibra 300 Mbps", "amount": "450.00"}),
    ("aspa Unicode (U+02BC) para contrabando", {"provider": "Conecta Alfa Fictíciaʼ; DELETE FROM app.Pagamentos; --", "description": "IP adicional mensal", "amount": "35.00"}),
    ("variável do sqlcmd com a senha", {"provider": "Conecta Alfa Fictícia", "description": "IP adicional $(SQLCMDPASSWORD) mensal", "amount": "35.00"}),
    ("comando do sistema pelo sqlcmd (:!!)", {"provider": "Conecta Alfa Fictícia", "description": "IP adicional\n:!! cat /etc/passwd\nGO", "amount": "35.00"}),
    ("UNION para ler outro local", {"provider": "Conecta Alfa Fictícia' UNION SELECT * FROM app.Notas WHERE local_id='LOC-002'--", "description": "link principal", "amount": "450.00"}),
    ("valor com SQL", {"provider": "Conecta Alfa Fictícia", "description": "link principal fibra 300 Mbps", "amount": "450.00; DROP TABLE app.Notas"}),
    ("texto gigante (100 mil caracteres)", {"provider": "Conecta Alfa Fictícia", "description": "A" * 100_000, "amount": "450.00"}),
    ("local de outro escopo no corpo", {"provider": "Conecta Alfa Fictícia", "description": "link principal", "amount": "450.00", "local_id": "LOC-002'; --"}),
]

ATAQUES_PROCEDIMENTO = [
    ("aspas no provedor", "EXEC ai.usp_get_context @local_id = N'LOC-001', @correlation_id = '{cid}', @provider_id = N'PROV-001''; DROP TABLE app.Notas; --', @take = 5, @return_json = 1, @requested_by = N'teste-injecao';"),
    ("local de outro escopo", "EXEC ai.usp_get_context @local_id = N'LOC-002', @correlation_id = '{cid}', @provider_id = N'PROV-001', @take = 5, @return_json = 1, @requested_by = N'teste-injecao';"),
    ("take gigante", "EXEC ai.usp_get_context @local_id = N'LOC-001', @correlation_id = '{cid}', @provider_id = N'PROV-001', @take = 2147483647, @return_json = 1, @requested_by = N'teste-injecao';"),
    ("ler a tabela direto", "SELECT TOP 1 chave_fiscal FROM app.Notas;"),
    ("apagar a trilha", "DELETE FROM audit.Eventos;"),
    ("SQL dinâmico para ler a tabela", "EXEC (N'SELECT TOP 1 chave_fiscal FROM app.Notas');"),
]


def como_ia(consulta: str) -> tuple[int, str]:
    """Roda como o usuário da IA, de dentro do container da IA (o mesmo caminho da API), com -x."""
    r = subprocess.run(["docker", "exec", "-e", "SQLCMDPASSWORD", "sigp_academic_ai", "sqlcmd", "-S", "sqlserver-academic,1433",
                        "-U", "sigp_ia_loc001", "-d", "SIGpAcademic", "-C", "-b", "-x", "-y", "0", "-Q", "SET NOCOUNT ON; " + consulta],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "SQLCMDPASSWORD": ENV["SIGP_AI_DB_PASSWORD_LOC001"]}, timeout=60)
    return r.returncode, r.stdout + r.stderr


def primitiva_da_api() -> dict:
    """A função _sqlcmd da própria API (app.py dentro do container) com $(SQLCMDPASSWORD) no texto da consulta."""
    sonda = ("import sys; sys.path.insert(0, '/app'); import app\n"
             "for nome in ('SIGP_AI_API_KEY', 'HOME'):\n"
             "    saida = app._sqlcmd(f\"SET NOCOUNT ON; SELECT LEN(N'$({nome})') AS n;\")\n"
             "    print(nome, [l.strip() for l in saida.splitlines() if l.strip().isdigit()][0])\n")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(sonda)
        caminho = f.name
    try:
        subprocess.run(["docker", "cp", caminho, "sigp_academic_ai:/tmp/sonda_sqlcmd.py"], check=True, capture_output=True)
        r = subprocess.run(["docker", "exec", "sigp_academic_ai", "python", "/tmp/sonda_sqlcmd.py"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        subprocess.run(["docker", "exec", "-u", "0", "sigp_academic_ai", "rm", "-f", "/tmp/sonda_sqlcmd.py"], capture_output=True)
    finally:
        os.unlink(caminho)
    if r.returncode:
        raise RuntimeError("a sonda da primitiva falhou:\n" + (r.stdout + r.stderr)[-500:])
    lidos = dict(l.split() for l in r.stdout.strip().splitlines() if len(l.split()) == 2)
    trocadas = [nome for nome, n in lidos.items() if int(n) != len(f"$({nome})")]
    return {"tamanho_lido": {k: int(v) for k, v in lidos.items()},
            "tamanho_do_texto_literal": {k: len(f"$({k})") for k in lidos},
            "substituiu_pela_senha": bool(trocadas),
            "detalhe": (f"o sqlcmd trocou {', '.join('$(' + t + ')' for t in trocadas)} pelo valor da variável de ambiente"
                        if trocadas else "$(SIGP_AI_API_KEY) e $(HOME) ficaram como texto")}


def main(rotulo: str) -> None:
    resultado = {"executado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rotulo": rotulo}
    antes = retrato()
    id0 = ultimo_evento()
    api = []
    for nome, invoice in ATAQUES_API:
        st, r = analisar(invoice)
        cls = r.get("classification")
        api.append({"ataque": nome, "http": st, "classificacao": cls,
                    # Recusado na entrada (400 validação, 413 tamanho) ou respondido só com o que é permitido.
                    "seguro": (st in (400, 413)) or (st == 200 and cls in PERMITIDAS and r.get("automatic_payment") is False),
                    "erro": str(r.get("error") or "")[:160]})
    depois_api = retrato()
    trilha = eventos_desde(id0)
    resultado["api"] = {"ataques": api, "banco_igual": antes == depois_api,
                        "senha_na_trilha": any(s in trilha for s in SENHAS), "variavel_na_trilha": "$(" in trilha}
    proc = []
    for nome, consulta in ATAQUES_PROCEDIMENTO:
        rc, txt = como_ia(consulta.replace("{cid}", "00000000-0000-0000-0000-000000000001"))
        negado = rc != 0
        proc.append({"ataque": nome, "negado_ou_vazio": negado or ("LOC-002" not in txt and "DROP" not in txt),
                     "rc": rc, "mensagem": next((l.strip() for l in txt.splitlines() if "Msg" in l or "permission" in l.lower() or "negad" in l.lower()), "")[:200]})
    depois_proc = retrato()
    dinamico = sql_sa("SELECT COUNT(*) FROM sys.sql_modules m JOIN sys.objects o ON o.object_id = m.object_id "
                      "WHERE SCHEMA_NAME(o.schema_id) IN ('ai', 'app') AND (m.definition LIKE '%sp_executesql%' OR m.definition LIKE '%EXEC(@%' OR m.definition LIKE '%EXEC (@%' OR m.definition LIKE '%EXECUTE(@%');")
    resultado["procedimentos"] = {"ataques": proc, "banco_igual": antes == depois_proc,
                                  "modulos_com_sql_dinamico": int(next(l for l in dinamico.splitlines() if l.strip().isdigit()).strip())}
    resultado["primitiva"] = primitiva_da_api()
    resultado["retrato_do_banco"] = antes
    ok = (all(a["seguro"] for a in api) and resultado["api"]["banco_igual"] and not resultado["api"]["senha_na_trilha"]
          and all(p["negado_ou_vazio"] for p in proc) and resultado["procedimentos"]["banco_igual"]
          and resultado["procedimentos"]["modulos_com_sql_dinamico"] == 0 and not resultado["primitiva"]["substituiu_pela_senha"])
    resultado["resultado"] = "APROVADO" if ok else "REPROVADO"
    saida = EV / f"injecao-sql-{rotulo}.json"
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for a in api:
        print(f"  API  {'ok  ' if a['seguro'] else 'FALHA'} {a['ataque']:<40} HTTP {a['http']} {a['classificacao'] or a['erro'][:60]}")
    print(f"  API  banco igual: {resultado['api']['banco_igual']} · senha na trilha: {resultado['api']['senha_na_trilha']}")
    for p in proc:
        print(f"  PROC {'ok  ' if p['negado_ou_vazio'] else 'FALHA'} {p['ataque']:<40} {p['mensagem'][:80]}")
    print(f"  PROC banco igual: {resultado['procedimentos']['banco_igual']} · módulos com SQL dinâmico: {resultado['procedimentos']['modulos_com_sql_dinamico']}")
    print(f"  PRIM {'FALHA' if resultado['primitiva']['substituiu_pela_senha'] else 'ok  '} {resultado['primitiva']['detalhe']}")
    print(f"Resultado: {resultado['resultado']} · {saida.name}")


def documento() -> None:
    """seguranca/injecao-sql.md a partir de injecao-sql-antes.json e injecao-sql-depois.json (nada digitado à mão)."""
    antes = json.loads((EV / "injecao-sql-antes.json").read_text(encoding="utf-8"))
    depois = json.loads((EV / "injecao-sql-depois.json").read_text(encoding="utf-8"))
    sim = lambda v: "sim" if v else "não"
    l = ["# Injeção de SQL: ataques em três níveis", "",
         "Gerado por `seguranca/testar_injecao_sql.py` a partir de `sqlserver/evidence/parte3/injecao-sql-antes.json` e "
         "`injecao-sql-depois.json`. Cada ataque roda contra o sistema no ar, e o banco é conferido antes e depois (linhas de "
         "notas, pagamentos, locais e provedores, objetos, permissões da IA e membros do sysadmin).", "",
         f"| | Antes ({antes['executado_em_utc']}) | Depois ({depois['executado_em_utc']}) |", "|---|---|---|",
         f"| Resultado | {antes['resultado']} | {depois['resultado']} |",
         f"| Ataques pela API sem efeito | {sum(a['seguro'] for a in antes['api']['ataques'])}/{len(antes['api']['ataques'])} | {sum(a['seguro'] for a in depois['api']['ataques'])}/{len(depois['api']['ataques'])} |",
         f"| Ataques nos procedimentos sem efeito | {sum(a['negado_ou_vazio'] for a in antes['procedimentos']['ataques'])}/{len(antes['procedimentos']['ataques'])} | {sum(a['negado_ou_vazio'] for a in depois['procedimentos']['ataques'])}/{len(depois['procedimentos']['ataques'])} |",
         f"| Banco igual depois dos ataques | {sim(antes['api']['banco_igual'] and antes['procedimentos']['banco_igual'])} | {sim(depois['api']['banco_igual'] and depois['procedimentos']['banco_igual'])} |",
         f"| Senha na trilha de auditoria | {sim(antes['api']['senha_na_trilha'])} | {sim(depois['api']['senha_na_trilha'])} |",
         f"| Procedimentos com SQL dinâmico | {antes['procedimentos']['modulos_com_sql_dinamico']} | {depois['procedimentos']['modulos_com_sql_dinamico']} |",
         f"| Primitiva da API troca `$(VARIÁVEL)` | {sim(antes['primitiva']['substituiu_pela_senha'])}: {antes['primitiva']['detalhe']} | {sim(depois['primitiva']['substituiu_pela_senha'])}: {depois['primitiva']['detalhe']} |",
         "", "## 1. Pela API da IA (como um usuário mal-intencionado)", "", "| Ataque | HTTP | Resposta |", "|---|---|---|"]
    for x in depois["api"]["ataques"]:
        l.append(f"| {x['ataque']} | {x['http']} | {x['classificacao'] or x['erro'][:90].splitlines()[0]} |")
    l += ["", "Por que nada passa: o texto da fatura nunca entra no SQL. A descrição vira um hash (SHA-256), o provedor é trocado "
          "pelo código de uma lista fixa (ou PROV-UNKNOWN), o valor só aceita número, a classificação do modelo só aceita três "
          "valores e o motivo é um texto fixo das regras. O local vem da credencial do serviço, nunca do corpo (400).", "",
          "## 2. Direto nos procedimentos, com o usuário da IA", "", "| Ataque | Resultado |", "|---|---|"]
    for x in depois["procedimentos"]["ataques"]:
        l.append(f"| {x['ataque']} | {x['mensagem'] or 'sem efeito (nenhuma linha de outro local, nada executado)'} |")
    l += ["", "Os erros 51001 e 51003 são do próprio procedimento (escopo e limite conferidos); 229 é permissão negada (a IA não "
          "lê tabela, nem por SQL dinâmico); 37359 é a trilha ledger recusando apagar. Nenhum procedimento dos schemas `ai` e "
          "`app` monta SQL dinâmico.", "",
          "## 3. A primitiva que fala com o banco (achado e correção)", "",
          "A API chama o `sqlcmd` com o texto da consulta. O `sqlcmd` troca `$(VARIÁVEL)` pelo valor da variável de ambiente: "
          "na primeira rodada, `$(SIGP_AI_API_KEY)` virou um texto de 64 caracteres (a chave da API da IA) e `$(HOME)` a pasta "
          "do usuário. Hoje nenhum texto do usuário chega à consulta, mas bastaria um campo novo com texto livre para a chave ir "
          "parar na trilha ou numa mensagem de erro. Correção: `-x` no `sqlcmd` de `ia/app.py` (desliga a troca). Depois: as "
          "duas variáveis ficam como texto. Só o tamanho é medido; o valor nunca é lido.", ""]
    (Path(__file__).resolve().parent / "injecao-sql.md").write_text("\n".join(l), encoding="utf-8")
    print("ok: injecao-sql.md")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "atual"
    documento() if modo == "documento" else main(modo)
