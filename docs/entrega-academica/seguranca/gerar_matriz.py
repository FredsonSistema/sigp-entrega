"""Gera docs/entrega-academica/seguranca/matriz-permissoes.md a partir do banco (permissões efetivas medidas, não
digitadas) e grava a evidência em sqlserver/evidence/parte3/matriz-permissoes.json.
Roda sqlserver/15_matriz_permissoes.sql como sa; a senha vem do .env.academic (ignorado pelo Git) por variável de ambiente.
Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/seguranca/gerar_matriz.py
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

DIR = Path(__file__).resolve().parent
SQLDIR = DIR.parent / "sqlserver"
SAIDA = DIR / "matriz-permissoes.md"
EVID = SQLDIR / "evidence" / "parte3" / "matriz-permissoes.json"

# Por que cada DENY existe (o cenário), e o teste que o prova.
JUSTIFICATIVA = {
    ("sigp_api", "DELETE", "SCHEMA::app"): (
        "Nota fiscal, pagamento e conciliação são registro contábil: erro se corrige com novo status ou estorno, nunca "
        "apagando. Só o dono do banco apaga, numa manutenção registrada pela auditoria nativa. DENY e não só ausência de "
        "GRANT: o DENY vence qualquer GRANT que a API ganhe depois por outro papel (prova abaixo, com db_datawriter).",
        "02_security_tests.sql (delete_api_negado); prova do DENY abaixo"),
    ("sigp_api", "SELECT", "audit.Eventos"): (
        "Quem é auditado não lê a própria trilha: saberia o que ficou registrado e o que não ficou.",
        "14_auditoria_testes.sql (T2d)"),
    ("sigp_api", "INSERT", "audit.Eventos"): (
        "A trilha só recebe eventos dos procedimentos da IA e do gatilho de auditoria. Com INSERT direto, o operador "
        "forjava eventos em nome de outro (achado H-21).",
        "14_auditoria_testes.sql (T2a)"),
    ("sigp_api", "UPDATE", "audit.Eventos"): ("Ninguém reescreve a trilha.", "08_ataque_escalonamento.sql (E5)"),
    ("sigp_api", "DELETE", "audit.Eventos"): ("Ninguém apaga a trilha.", "08 (E4); 14 (T2b)"),
    ("sigp_api", "INSERT", "app.ResumoDiario"): (
        "O resumo da consulta 1 só muda pelo gatilho; gravar direto forjaria totais.", "12_resumo_testes.sql"),
    ("sigp_api", "UPDATE", "app.ResumoDiario"): ("Mesmo motivo: forjar o total faturado.", "12_resumo_testes.sql (forjar total)"),
    ("sigp_api", "DELETE", "app.ResumoDiario"): ("Mesmo motivo.", "12_resumo_testes.sql"),
    ("sigp_ia", "SELECT", "SCHEMA::app"): (
        "A IA só recebe o contexto mínimo pelo procedimento que confere o local. Sem leitura direta, nem um prompt injection "
        "nem uma credencial vazada da IA leem as tabelas.",
        "02 (leitura_direta_negada); testar_ia_perfis.py"),
    ("sigp_ia", "INSERT", "SCHEMA::app"): ("A IA não grava dado de negócio: só sugere.", "02_security_tests.sql"),
    ("sigp_ia", "UPDATE", "SCHEMA::app"): ("Idem: a IA não altera nota nem pagamento.", "02_security_tests.sql"),
    ("sigp_ia", "DELETE", "SCHEMA::app"): ("Idem.", "02_security_tests.sql"),
    ("sigp_ia", "SELECT", "SCHEMA::audit"): ("A IA não lê a trilha que a registra.", "testar_ia_perfis.py (parte D)"),
    ("sigp_ia", "INSERT", "SCHEMA::audit"): (
        "A IA não escreve na trilha direto; só pelos procedimentos, que validam o conteúdo e o escopo.",
        "testar_ia_perfis.py (D1)"),
    ("sigp_ia", "UPDATE", "SCHEMA::audit"): ("A IA não reescreve a trilha.", "testar_ia_perfis.py"),
    ("sigp_ia", "DELETE", "SCHEMA::audit"): ("A IA não apaga a trilha.", "testar_ia_perfis.py"),
    ("sigp_ia", "SELECT", "ai.vw_contexto_minimo"): (
        "A view não filtra por escopo sozinha; quem confere o local é o procedimento ai.usp_get_context.",
        "02_security_tests.sql"),
    ("sigp_ia", "INSERT", "ai.vw_contexto_minimo"): ("A view é só leitura para a IA.", "02_security_tests.sql"),
    ("sigp_ia", "UPDATE", "ai.vw_contexto_minimo"): ("Idem.", "02_security_tests.sql"),
    ("sigp_ia", "DELETE", "ai.vw_contexto_minimo"): ("Idem.", "02_security_tests.sql"),
    ("sigp_ia", "INSERT", "SCHEMA::ai"): ("A IA não cria nem altera objetos e dados do schema ai.", "02_security_tests.sql"),
    ("sigp_ia", "UPDATE", "SCHEMA::ai"): ("Idem.", "02_security_tests.sql"),
    ("sigp_ia", "DELETE", "SCHEMA::ai"): ("Idem.", "02_security_tests.sql"),
}
OBJETOS_TABELA = ["app.Notas", "app.ItensNota", "app.Pagamentos", "app.Conciliacoes", "app.Locais", "app.Provedores",
                  "app.ResumoDiario", "security.LocalScope", "audit.Eventos", "ai.vw_contexto_minimo"]
LETRA = {"SELECT": "L", "INSERT": "I", "UPDATE": "A", "DELETE": "E"}


def senha_sa() -> str:
    for linha in (SQLDIR / ".env.academic").read_text(encoding="utf-8").splitlines():
        if linha.startswith("MSSQL_SA_PASSWORD="):
            return linha.split("=", 1)[1].strip()
    sys.exit("MSSQL_SA_PASSWORD não encontrada no .env.academic.")


def rodar() -> dict:
    # A saída vai para um arquivo (-o): pelo console, a primeira chamada do sqlcmd numa janela sai na página 850 do
    # Windows mesmo com "-f 65001" ("não" vira 0xC6); o arquivo sai sempre em UTF-8.
    saida = Path(tempfile.gettempdir()) / f"sigp-matriz-{os.getpid()}.txt"
    try:
        r = subprocess.run(["sqlcmd", "-S", "127.0.0.1,14333", "-U", "sa", "-d", "SIGpAcademic", "-C", "-I", "-b", "-y", "0",
                            "-f", "65001", "-i", str(SQLDIR / "15_matriz_permissoes.sql"), "-o", str(saida)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "SQLCMDPASSWORD": senha_sa()}, timeout=180, check=False)
        texto = saida.read_text(encoding="utf-8-sig") if saida.exists() else ""
    finally:
        saida.unlink(missing_ok=True)
    if r.returncode:
        sys.exit(f"15_matriz_permissoes.sql falhou: {texto[-500:]} {r.stderr[-500:]}")
    if "\ufffd" in texto:
        sys.exit("A saída do sqlcmd veio com caracteres inválidos (codificação); o documento não foi gerado.")
    # Com -y 0 o sqlcmd não imprime o nome das colunas: cada resultado (FOR JSON) vem numa linha, na ordem do script.
    nomes = ["principais", "matriz", "denys", "prova_deny"]
    linhas = [l.strip() for l in texto.splitlines() if l.strip().startswith("[")]
    if len(linhas) != len(nomes):
        sys.exit(f"Esperava {len(nomes)} resultados em JSON do 15_matriz_permissoes.sql e vieram {len(linhas)}.")
    return {n: json.loads(l) for n, l in zip(nomes, linhas)}


def main() -> None:
    d = rodar()
    princ = d["principais"]
    usuarios = [p["usuario"] for p in princ]
    ef = {(x["usuario"], x["objeto"], x["permissao"], x.get("sub")): bool(x["efetiva"]) for x in d["matriz"]}
    prova = d["prova_deny"]
    EVID.write_text(json.dumps({"gerado_em_utc": datetime.now(timezone.utc).isoformat(), **d}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")

    def cel(u: str, obj: str) -> str:
        letras = "".join(LETRA[p] for p in ("SELECT", "INSERT", "UPDATE", "DELETE") if ef.get((u, obj, p, None)))
        return letras or "—"

    L = [
        "# Matriz final de papéis e permissões",
        "",
        "Gerada por [`gerar_matriz.py`](gerar_matriz.py) a partir do banco: cada célula é a permissão **efetiva** medida como o "
        "usuário de teste (`HAS_PERMS_BY_NAME` com `EXECUTE AS USER`, que considera GRANT, DENY, papéis e herança do schema), "
        "não uma cópia do script. Script: [`../sqlserver/15_matriz_permissoes.sql`](../sqlserver/15_matriz_permissoes.sql). "
        f"Evidência: [`matriz-permissoes.json`](../sqlserver/evidence/parte3/matriz-permissoes.json).",
        "",
        "## Perfis",
        "",
        "| Usuário de teste | Perfil | Papéis | Escopo (RLS) |",
        "|---|---|---|---|",
        *[f"| `{p['usuario']}` | {p['perfil']} | {p.get('papeis') or '—'} | {p.get('escopo_rls') or 'nenhum'} |" for p in princ],
        "",
        "## Tabelas e view",
        "",
        "L = ler, I = inserir, A = alterar, E = apagar; — = nada. A RLS filtra ainda as linhas de `app.Notas` e "
        "`app.ResumoDiario` pelo escopo, e os predicados BLOCK impedem gravar fora dele.",
        "",
        "| Objeto | " + " | ".join(f"`{u}`" for u in usuarios) + " |",
        "|---|" + "---|" * len(usuarios),
        *[f"| `{o}` | " + " | ".join(cel(u, o) for u in usuarios) + " |" for o in OBJETOS_TABELA],
        "",
        "## Procedimentos, dado sensível e privilégios",
        "",
        "| Permissão | " + " | ".join(f"`{u}`" for u in usuarios) + " |",
        "|---|" + "---|" * len(usuarios),
    ]
    extras = [("EXECUTE `ai.usp_get_context`", "ai.usp_get_context", "EXECUTE", None),
              ("EXECUTE `ai.usp_log_sources`", "ai.usp_log_sources", "EXECUTE", None),
              ("EXECUTE `ai.usp_log_response`", "ai.usp_log_response", "EXECUTE", None),
              ("UNMASK `app.Notas.chave_fiscal`", "app.Notas", "UNMASK", "chave_fiscal"),
              ("UNMASK `app.Pagamentos.referencia`", "app.Pagamentos", "UNMASK", "referencia"),
              ("ALTER no papel `sigp_auditor` (entrar nele)", "sigp_auditor", "ALTER", None),
              ("IMPERSONATE `sigp_ia_loc002` (se passar por ele)", "sigp_ia_loc002", "IMPERSONATE", None)]
    for rot, obj, perm, sub in extras:
        L.append(f"| {rot} | " + " | ".join("sim" if ef.get((u, obj, perm, sub)) else "—" for u in usuarios) + " |")
    L += [
        "",
        "Leitura rápida: a API e o operador leem e gravam o negócio, mas nunca apagam, e a chave fiscal chega a eles mascarada. "
        "O auditor só lê a trilha e a view sem chave fiscal. O fiscal é o único que vê a chave fiscal. A IA não lê nenhuma "
        "tabela: só executa os três procedimentos, que conferem o local. Ninguém consegue entrar noutro papel nem se passar por "
        "outro usuário.",
        "",
        "## Os DENY e por que existem",
        "",
        "| Papel | DENY | Em | Por quê | Teste que prova |",
        "|---|---|---|---|---|",
    ]
    for x in d["denys"]:
        j = JUSTIFICATIVA.get((x["papel"], x["permissao"], x["alvo"]), ("(sem justificativa registrada)", "—"))
        L.append(f"| `{x['papel']}` | {x['permissao']} | `{x['alvo']}` | {j[0]} | {j[1]} |")
    L += [
        "",
        "## Prova do DENY: o DENY vence um GRANT dado depois",
        "",
        "O DENY de exclusão da API no schema `app` é o DENY principal. Sem ele, bastaria alguém colocar a API num papel "
        "amplo para ela passar a apagar notas fiscais. O teste faz exatamente isso, dentro de uma transação desfeita:",
        "",
        "| Teste | Esperado | Obtido | Veredito |",
        "|---|---|---|---|",
        *[f"| {p['teste']} | {p['esperado']} | {p['obtido']} | {p['veredito']} |" for p in prova],
        "",
        f"Resultado: **{'APROVADO' if all(p['veredito'] == 'OK' for p in prova) else 'REPROVADO'}**. O controle mostra que o "
        "papel db_datawriter de fato dá DELETE; só o DENY segura as tabelas do schema `app`.",
        "",
        "## Os testes que provam a matriz em uso",
        "",
        "| Teste | O que prova |",
        "|---|---|",
        "| [`02_security_tests.sql`](../sqlserver/02_security_tests.sql) | IA lê só pelo procedimento e só o próprio local; DELETE da API negado; sem papel não executa nada; auditor lê a trilha |",
        "| [`07_mascaramento_parte2.sql`](../sqlserver/07_mascaramento_parte2.sql) | API vê a chave mascarada; fiscal vê a chave real; auditor não lê as notas; a view da IA não tem a chave |",
        "| [`08_ataque_escalonamento.sql`](../sqlserver/08_ataque_escalonamento.sql) | Escalonamento vertical e horizontal barrados (ver [`ataque-escalonamento.md`](ataque-escalonamento.md)) |",
        "| [`12_resumo_testes.sql`](../sqlserver/12_resumo_testes.sql) | Resumo da consulta 1 com a mesma RLS; ninguém forja o total |",
        "| [`14_auditoria_testes.sql`](../sqlserver/14_auditoria_testes.sql) | Trilha de quem fez o quê, sem como forjar, apagar, ler (operador) ou desligar |",
        "| [`testar_ia_perfis.py`](../sqlserver/testar_ia_perfis.py) | A IA não vaza o que o banco protege, perfil por perfil |",
        "",
    ]
    SAIDA.write_text("\n".join(L), encoding="utf-8")
    print(f"ok: {SAIDA} · prova do DENY: {[p['veredito'] for p in prova]}")


if __name__ == "__main__":
    main()
