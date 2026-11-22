"""Trilha à prova de adulteração: confere a ledger da audit.Eventos (SQL Server 2022) e guarda o digest FORA do banco.

1. A audit.Eventos é uma tabela ledger "somente inclusão".
2. Gera o digest do banco (sp_generate_database_ledger_digest) e acrescenta em
   sqlserver/evidence/parte3/ledger-digests.json. Esse arquivo vai para o Git: é o "armazenamento confiável" fora do
   banco. Quem controla o banco não consegue reescrever o digest já publicado.
3. Verifica a ledger contra TODOS os digests guardados desta instalação do banco (sp_verify_database_ledger). Se alguém
   alterasse um evento já registrado (até editando as páginas do arquivo), a cadeia de hashes não bateria.
4. Controle negativo: um digest com o hash trocado tem de ser recusado (erro 37392).
5. O sa tenta alterar, apagar e truncar a trilha: UPDATE e DELETE dão 37359, TRUNCATE dá 13545.
6. Mostra o histórico de operações da tabela (sys.ledger_table_history) e o evento LEDGER_ATIVADA da migração.
Saída: sqlserver/evidence/parte3/ledger-verificacao.json. A senha do sa vem do .env.academic e vai ao sqlcmd por variável
de ambiente; nunca é gravada.
Uso, na raiz do projeto:  python docs/entrega-academica/seguranca/verificar_ledger.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ENTREGA = Path(__file__).resolve().parents[1]
SQL = ENTREGA / "sqlserver"
EV = SQL / "evidence" / "parte3"
DIGESTS = EV / "ledger-digests.json"
SAIDA = EV / "ledger-verificacao.json"


def senha() -> str:
    for linha in (SQL / ".env.academic").read_text(encoding="utf-8").splitlines():
        if linha.startswith("MSSQL_SA_PASSWORD="):
            return linha.split("=", 1)[1].strip()
    raise SystemExit("MSSQL_SA_PASSWORD não está no .env.academic")


def sql(texto: str) -> tuple[int, str]:
    """Roda um lote no SIGpAcademic como sa; devolve (código de saída, texto)."""
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8-sig") as f:
        f.write("SET NOCOUNT ON;\n" + texto)
        caminho = f.name
    try:
        r = subprocess.run(["sqlcmd", "-S", "127.0.0.1,14333", "-U", "sa", "-d", "SIGpAcademic", "-C", "-I", "-f", "65001",
                            "-y", "0", "-i", caminho], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "SQLCMDPASSWORD": senha()}, timeout=120)
        return r.returncode, (r.stdout + r.stderr)
    finally:
        os.unlink(caminho)


def linha_json(saida: str):
    for l in saida.splitlines():
        l = l.strip()
        if l.startswith(("{", "[")):
            return json.loads(l)
    raise RuntimeError("o SQL Server não devolveu o JSON esperado:\n" + saida[:500])


def erro(saida: str) -> int | None:
    m = re.search(r"ERRO=(\d+)", saida)
    return int(m.group(1)) if m else None


def tentativa(comando: str) -> str:
    return (f"BEGIN TRY EXEC sys.sp_executesql N'{comando}'; PRINT 'ERRO=0'; END TRY "
            "BEGIN CATCH PRINT CONCAT('ERRO=', ERROR_NUMBER()); END CATCH;")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    verificacoes = []

    def conferir(teste: str, esperado: str, obtido: str, ok: bool) -> None:
        verificacoes.append({"teste": teste, "esperado": esperado, "obtido": obtido, "veredito": "OK" if ok else "FALHA"})
        print(f"  {'OK   ' if ok else 'FALHA'} {teste}: {obtido}")

    _, s = sql("SELECT (SELECT t.ledger_type_desc AS tipo, CONVERT(CHAR(27), d.create_date, 126) AS banco_criado_em, "
               "(SELECT COUNT_BIG(*) FROM audit.Eventos) AS eventos FROM sys.tables t CROSS JOIN sys.databases d "
               "WHERE t.object_id = OBJECT_ID(N'audit.Eventos') AND d.name = DB_NAME() FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);")
    info = linha_json(s)
    conferir("A trilha é uma tabela ledger somente inclusão", "APPEND_ONLY_LEDGER_TABLE", info["tipo"], info["tipo"] == "APPEND_ONLY_LEDGER_TABLE")

    # 2. digest novo, guardado fora do banco
    _, s = sql("EXEC sys.sp_generate_database_ledger_digest;")
    digest = linha_json(s)
    guardados = json.loads(DIGESTS.read_text(encoding="utf-8")) if DIGESTS.exists() else []
    guardados.append({"gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "banco_criado_em": info["banco_criado_em"], "eventos": info["eventos"], "digest": digest})
    DIGESTS.write_text(json.dumps(guardados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    desta_instalacao = [g["digest"] for g in guardados if g["banco_criado_em"] == info["banco_criado_em"]]

    # 3. verificação contra todos os digests guardados desta instalação
    lista = json.dumps(desta_instalacao).replace("'", "''")
    cod, s = sql(f"BEGIN TRY EXEC sys.sp_verify_database_ledger N'{lista}'; PRINT 'ERRO=0'; END TRY "
                 "BEGIN CATCH PRINT CONCAT('ERRO=', ERROR_NUMBER(), ' ', ERROR_MESSAGE()); END CATCH;")
    conferir(f"Ledger confere com os {len(desta_instalacao)} digest(s) guardados fora do banco", "verificada",
             "verificada" if erro(s) == 0 else f"falhou: {s.strip()[-200:]}", erro(s) == 0)

    # 4. controle negativo: digest com o hash trocado
    falso = dict(digest)
    h = falso["hash"]
    falso["hash"] = h[:10] + ("AA" if h[10:12] != "AA" else "BB") + h[12:]
    _, s = sql(f"BEGIN TRY EXEC sys.sp_verify_database_ledger N'{json.dumps(falso)}'; PRINT 'ERRO=0'; END TRY "
               "BEGIN CATCH PRINT CONCAT('ERRO=', ERROR_NUMBER()); END CATCH;")
    conferir("Controle: digest adulterado é recusado", "erro 37392", f"erro {erro(s)}", erro(s) == 37392)

    # 5. o sa tenta mexer na trilha
    for rotulo, comando, codigo in (("O sa altera um evento (UPDATE)", "UPDATE audit.Eventos SET ator = N''sa'' WHERE id = (SELECT MIN(id) FROM audit.Eventos);", 37359),
                                    ("O sa apaga eventos (DELETE)", "DELETE FROM audit.Eventos WHERE acao = N''AI_RESPONSE'';", 37359),
                                    ("O sa esvazia a trilha (TRUNCATE)", "TRUNCATE TABLE audit.Eventos;", 13545)):
        _, s = sql(tentativa(comando))
        conferir(rotulo, f"negado (erro {codigo})", "PERMITIDO" if erro(s) == 0 else f"negado (erro {erro(s)})", erro(s) == codigo)
    _, s = sql("SELECT COUNT_BIG(*) AS n FROM audit.Eventos FOR JSON PATH, WITHOUT_ARRAY_WRAPPER;")
    depois = linha_json(s)["n"]
    conferir("Nenhum evento sumiu depois das tentativas", f">= {info['eventos']}", str(depois), depois >= info["eventos"])

    # 6. histórico da tabela e evento da migração
    _, s = sql("SELECT (SELECT h.operation_type_desc AS operacao, CONVERT(CHAR(19), t.commit_time, 120) AS quando, t.principal_name AS quem "
               "FROM sys.ledger_table_history h JOIN sys.database_ledger_transactions t ON t.transaction_id = h.transaction_id "
               "WHERE h.object_id = OBJECT_ID(N'audit.Eventos') ORDER BY t.commit_time FOR JSON PATH) AS j;")
    historico = linha_json(s)
    _, s = sql("SELECT (SELECT TOP 1 id, CONVERT(CHAR(19), criado_em, 120) AS criado_em, detalhe_redigido AS detalhe FROM audit.Eventos "
               "WHERE acao = N'LEDGER_ATIVADA' ORDER BY id FOR JSON PATH, WITHOUT_ARRAY_WRAPPER) AS j;")
    migracao = linha_json(s)
    conferir("Migração registrada na própria trilha (LEDGER_ATIVADA)", "1 evento com contagem e SHA-256", migracao["detalhe"][:60] + "…",
             "sha256_antes=0x" in migracao["detalhe"])

    falhas = [v for v in verificacoes if v["veredito"] != "OK"]
    resultado = {"executado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "resultado": "APROVADO" if not falhas else "REPROVADO", "tabela": info, "verificacoes": verificacoes,
                 "historico_da_tabela": historico, "evento_de_migracao": migracao,
                 "digests_guardados": len(guardados), "digests_desta_instalacao": len(desta_instalacao),
                 "ultimo_digest": digest}
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Resultado: {resultado['resultado']} · {SAIDA.relative_to(ENTREGA.parents[1])}")
    sys.exit(0 if not falhas else 1)


if __name__ == "__main__":
    main()
