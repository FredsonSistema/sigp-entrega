"""Demonstração de perfis e permissões na API do SIGp (evidência para a entrega).

Num banco TEMPORÁRIO (não toca na produção): cria um usuário de cada grupo padrão, mais um com ajuste individual,
e tenta as mesmas ações com cada chave. Gera a matriz "pode / não pode" com o código HTTP de cada tentativa e a
auditoria registrada. Saída: evidence/permissoes-perfis.json e permissoes-perfis.md (nesta pasta).

Uso, na raiz do projeto:  python docs/entrega-academica/seguranca/demonstrar_perfis.py
"""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
from backend import app as app_module  # noqa: E402
from backend import database  # noqa: E402

PASTA = Path(__file__).resolve().parent
ADMIN = "chave-admin-demonstracao"

ACOES = [
    ("Ver locais", "GET", "/api/locais", None),
    ("Ver caixa de notas recebidas", "GET", "/api/notas-recebidas", None),
    ("Criar local", "POST", "/api/locais/agencia/item", {"nome": "Agência Demonstração {n}", "cidade": "Itabuna"}),
    ("Lançar nota", "POST", "/api/notas/lancadas", {"id": "demo-{n}", "entidadeTipo": "agencia", "entidadeId": "x", "dados": {"id": "demo-{n}"}}),
    ("Decidir no SIG", "POST", "/api/sig/decisoes", {}),
    ("Usar ordens de serviço", "PUT", "/api/app-state/sigp_os_v1", {"value": []}),
    ("Fazer backup do banco", "POST", "/api/saude/banco/backup", None),
    ("Administrar usuários", "GET", "/api/acesso/usuarios", None),
]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console do Windows
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        with patch.object(database, "DB_PATH", temp / "demo.db"), patch.object(app_module, "API_KEY", ADMIN), \
                patch.object(app_module, "FATURAS_DIR", temp), patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp):
            database.init_db()
            c = app_module.app.test_client()
            adm = {"X-API-Key": ADMIN}
            perfis = [("Administrador", adm)]
            for nome, grupo, ajustes in (("Gerente (Maciel)", "grp-gerente", {}), ("Operador (Jonata)", "grp-operador", {}),
                                         ("Leitura (auditoria)", "grp-leitura", {}),
                                         ("Leitura + ordens de serviço (ajuste individual)", "grp-leitura", {"os.usar": True})):
                r = c.post("/api/acesso/usuarios", headers=adm, json={"nome": nome, "grupoId": grupo, "ajustes": ajustes}).json
                perfis.append((nome, {"X-API-Key": r["chave"]}))
            perfis.append(("Sem chave", {}))
            matriz = []
            for i, (perfil, cab) in enumerate(perfis):
                linha = {"perfil": perfil, "acoes": {}}
                for rotulo, metodo, rota, corpo in ACOES:
                    body = json.loads(json.dumps(corpo).replace("{n}", str(i))) if corpo is not None else None
                    r = c.open(rota, method=metodo, headers=cab, json=body)
                    linha["acoes"][rotulo] = {"status": r.status_code, "pode": r.status_code < 400 or r.status_code in (400, 404, 409),
                                              "mensagem": (r.json or {}).get("error", "") if r.status_code in (401, 403) else ""}
                matriz.append(linha)
            auditoria = c.get("/api/acesso/auditoria?limite=100", headers=adm).json["items"]
    evidencia = {"executado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "observacao": "403 = perfil sem permissão; 401 = sem chave; 400/404/409 = permitido, mas os dados de teste são incompletos.",
                 "matriz": matriz, "auditoria": auditoria}
    (PASTA / "evidence").mkdir(exist_ok=True)
    (PASTA / "evidence" / "permissoes-perfis.json").write_text(json.dumps(evidencia, ensure_ascii=False, indent=2), encoding="utf-8")
    cab = "| Perfil | " + " | ".join(a[0] for a in ACOES) + " |"
    sep = "|---" * (len(ACOES) + 1) + "|"
    linhas = [f"| {l['perfil']} | " + " | ".join(("✓" if v["pode"] else "✗") + f" {v['status']}" for v in l["acoes"].values()) + " |" for l in matriz]
    negados = [a for a in auditoria if a["resultado"] in ("negado", "recusado")]
    md = "\n".join([
        "# Perfis e permissões — demonstração", "",
        f"Executado em {evidencia['executado_em_utc']} num banco temporário (`demonstrar_perfis.py`).",
        "✓ = permitido; ✗ = recusado (403 = perfil sem permissão; 401 = sem chave). 400/404/409 contam como permitido: a API aceitou o perfil e recusou só os dados de teste.", "",
        cab, sep, *linhas, "",
        f"Auditoria: {len(auditoria)} registros, {len(negados)} recusas (quem, ação, funcionalidade, resultado). Ver `evidence/permissoes-perfis.json`.", "",
        "Diferença para a Entrega 2: a versão daquela entrega (`sqlserver/evidence/parte2/demo-parte2-saida.txt`) mostrava "
        "\"Sem chave\" com 200 em Ver locais e Ver caixa de notas recebidas, e a leitura sem chave estava listada como pendente. "
        "Desde o login no servidor (commit `00f9f0f`), toda rota exige chave ou sessão, menos `/api/health`; "
        "`SIGP_EXIGIR_CHAVE_LEITURA=0` reabre a leitura só para diagnóstico. A linha \"Sem chave\" acima é a medida atual.", "",
    ])
    (PASTA / "permissoes-perfis.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
