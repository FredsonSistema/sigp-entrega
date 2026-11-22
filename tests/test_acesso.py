"""Perfis e permissões: administrador (chave do .env), grupos, ajustes individuais, auditoria e catálogo completo."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import acesso
from backend import app as app_module
from backend import database

ADMIN = {"X-API-Key": "chave-admin-teste"}


class AcessoTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp),
            patch.object(app_module, "API_KEY", ADMIN["X-API-Key"]),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def usuario(self, nome, grupo, **ajustes):
        r = self.client.post("/api/acesso/usuarios", headers=ADMIN, json={"nome": nome, "grupoId": grupo, "ajustes": ajustes})
        self.assertEqual(r.status_code, 201, r.json)
        return r.json["item"], {"X-API-Key": r.json["chave"]}

    def test_administrador_e_a_chave_do_env_e_tem_tudo(self):
        eu = self.client.get("/api/acesso/eu", headers=ADMIN).json
        self.assertEqual((eu["perfil"], eu["abas"]), ("administrador", None))
        self.assertEqual(len(eu["permissoes"]), len(acesso.TODAS))
        grupos = {g["nome"] for g in self.client.get("/api/acesso/grupos", headers=ADMIN).json["items"]}
        self.assertEqual(grupos, {"Gerente", "Operador", "Leitura", "Integração (n8n)"})
        self.assertEqual(self.client.post("/api/saude/banco/backup", headers=ADMIN).status_code, 200)

    def test_operador_trabalha_mas_nao_decide_nem_administra(self):
        _u, chave = self.usuario("Jonata de Jesus", "grp-operador")
        self.assertEqual(self.client.post("/api/locais/agencia/item", headers=chave, json={"nome": "Agência X", "cidade": "Ilhéus"}).status_code, 201)
        self.assertEqual(self.client.get("/api/notas-recebidas", headers=chave).status_code, 200)
        negado = self.client.post("/api/sig/decisoes", headers=chave, json={})
        self.assertEqual(negado.status_code, 403)
        self.assertIn("Operador", negado.json["error"])
        self.assertEqual(negado.json["permissao"], "sig.decidir")
        self.assertEqual(self.client.post("/api/saude/banco/backup", headers=chave).status_code, 403)
        self.assertEqual(self.client.get("/api/acesso/usuarios", headers=chave).status_code, 403)
        eu = self.client.get("/api/acesso/eu", headers=chave).json
        self.assertEqual((eu["nome"], eu["grupo"]), ("Jonata de Jesus", "Operador"))
        self.assertIn("notas-recebidas", eu["abas"])
        self.assertNotIn("banco.manter", eu["permissoes"])
        self.assertNotIn("sig.decidir", eu["permissoes"])

    def test_leitura_so_consulta(self):
        _u, chave = self.usuario("Auditoria", "grp-leitura")
        self.assertEqual(self.client.get("/api/locais", headers=chave).status_code, 200)
        self.assertEqual(self.client.post("/api/locais/agencia/item", headers=chave, json={"nome": "Y", "cidade": "Z"}).status_code, 403)
        self.assertEqual(self.client.put("/api/app-state/sigp_os_v1", headers=chave, json={"value": []}).status_code, 403)

    def test_ajustes_individuais_permitem_e_negam(self):
        _u, leitura_mais = self.usuario("Maciel Lopes", "grp-leitura", **{"locais.editar": True})
        self.assertEqual(self.client.post("/api/locais/agencia/item", headers=leitura_mais, json={"nome": "A", "cidade": "B"}).status_code, 201)
        _u, operador_menos = self.usuario("Aeverton", "grp-operador", **{"notas.lancar": False})
        self.assertEqual(self.client.post("/api/notas/lancadas", headers=operador_menos, json={}).status_code, 403)

    def test_grupo_novo_e_mudanca_de_permissoes_valem_na_hora(self):
        g = self.client.post("/api/acesso/grupos", headers=ADMIN, json={"nome": "Agenda", "permissoes": ["agenda_servicos.usar"]}).json["item"]
        _u, chave = self.usuario("Recepção", g["id"])
        self.assertEqual(self.client.put("/api/app-state/sigp_eventos_v1", headers=chave, json={"value": []}).status_code, 200)
        self.assertEqual(self.client.put("/api/app-state/sigp_os_v1", headers=chave, json={"value": []}).status_code, 403)
        self.client.put(f"/api/acesso/grupos/{g['id']}", headers=ADMIN, json={"nome": "Agenda", "permissoes": []})
        self.assertEqual(self.client.put("/api/app-state/sigp_eventos_v1", headers=chave, json={"value": []}).status_code, 403)
        self.assertEqual(self.client.post("/api/acesso/grupos", headers=ADMIN, json={"nome": "X", "permissoes": ["nao.existe"]}).status_code, 400)
        self.assertEqual(self.client.delete("/api/acesso/grupos/grp-operador", headers=ADMIN).status_code, 400)

    def test_usuario_desativado_e_chave_trocada_perdem_acesso(self):
        u, chave = self.usuario("Temporário", "grp-operador")
        self.client.put(f"/api/acesso/usuarios/{u['id']}", headers=ADMIN, json={"ativo": False})
        self.assertEqual(self.client.post("/api/auth/verify", headers=chave).status_code, 401)
        self.client.put(f"/api/acesso/usuarios/{u['id']}", headers=ADMIN, json={"ativo": True})
        nova = self.client.post(f"/api/acesso/usuarios/{u['id']}/nova-chave", headers=ADMIN).json["chave"]
        self.assertEqual(self.client.post("/api/auth/verify", headers=chave).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/verify", headers={"X-API-Key": nova}).json["nome"], "Temporário")

    def test_chave_guardada_so_como_hash(self):
        _u, chave = self.usuario("Fulano", "grp-leitura")
        conn = sqlite3.connect(database.DB_PATH)
        try:
            dump = "\n".join(conn.iterdump())
        finally:
            conn.close()
        self.assertNotIn(chave["X-API-Key"], dump)

    def test_sem_login_nem_chave_nada_e_liberado_alem_do_publico(self):
        # Desde o login no servidor, a leitura também exige login ou chave (SIGP_EXIGIR_CHAVE_LEITURA=0 reabre).
        self.assertEqual(self.client.get("/api/locais").status_code, 401)
        self.assertEqual(self.client.post("/api/locais/agencia/item", json={"nome": "A", "cidade": "B"}).status_code, 401)
        self.assertEqual(self.client.get("/api/acesso/usuarios").status_code, 401)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/estado").status_code, 200)
        with patch.object(app_module, "EXIGIR_CHAVE_LEITURA", False):
            self.assertEqual(self.client.get("/api/locais").status_code, 200)
            self.assertEqual(self.client.get("/api/acesso/usuarios").status_code, 401)

    def test_auditoria_registra_permitido_e_negado(self):
        _u, chave = self.usuario("Jonata de Jesus", "grp-operador")
        self.client.post("/api/locais/agencia/item", headers=chave, json={"nome": "Agência Z", "cidade": "Itabuna"})
        self.client.post("/api/sig/decisoes", headers=chave, json={})
        itens = self.client.get("/api/acesso/auditoria", headers=ADMIN).json["items"]
        resumo = [(i["usuario"], i["funcionalidade"], i["resultado"]) for i in itens if i["usuario"] == "Jonata de Jesus"]
        self.assertIn(("Jonata de Jesus", "locais.editar", "permitido"), resumo)
        self.assertIn(("Jonata de Jesus", "sig.decidir", "negado"), resumo)

    def test_toda_rota_da_api_esta_no_catalogo(self):
        soltas = []
        for regra in app_module.app.url_map.iter_rules():
            if not regra.rule.startswith("/api/") or regra.rule.startswith("/api/acesso/"):
                continue
            for metodo in regra.methods - {"HEAD", "OPTIONS"}:
                if acesso.funcionalidade_da_rota(metodo, regra.rule, "sigp_os_v1") == "admin":
                    soltas.append(f"{metodo} {regra.rule}")
        self.assertEqual(soltas, [], "rotas sem funcionalidade no catálogo (só o administrador usaria)")


if __name__ == "__main__":
    unittest.main()
