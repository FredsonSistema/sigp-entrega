"""SIGP_MODULOS: o pacote da entrega ("gestao") só tem o fluxo de gestão de contas; o sistema completo não muda."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import acesso, database
from backend import app as app_module

ADMIN = {"X-API-Key": "chave-admin-teste"}
DESLIGADAS_ABAS = {"sig", "geral", "sie", "os", "agenda-servicos", "agenda-pessoal", "sys", "assistente"}
FLUXO_ABAS = {"notas-recebidas", "notas", "faturas", "agencias", "rv", "gr", "ia", "config"}


class ModulosTests(unittest.TestCase):
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

    def test_completo_e_o_padrao_e_nao_muda_nada(self):
        with patch.dict(os.environ, {"SIGP_MODULOS": ""}):
            eu = self.client.get("/api/acesso/eu", headers=ADMIN).json
            self.assertIsNone(eu["abas"])
            self.assertEqual(eu["modulo"], "completo")
            self.assertEqual(self.client.get("/api/sig/resumo", headers=ADMIN).status_code, 200)
        with patch.dict(os.environ, {"SIGP_MODULOS": "nome-errado"}):
            self.assertEqual(acesso.modulo(), "completo")

    def test_gestao_mostra_so_as_abas_do_fluxo_ate_para_o_administrador(self):
        with patch.dict(os.environ, {"SIGP_MODULOS": "gestao"}):
            eu = self.client.get("/api/acesso/eu", headers=ADMIN).json
        self.assertEqual(set(eu["abas"]), FLUXO_ABAS)
        self.assertFalse(set(eu["abas"]) & DESLIGADAS_ABAS)
        self.assertFalse({"sig.decidir", "sie.ver", "assistente.usar", "os.usar"} & set(eu["permissoes"]))

    def test_gestao_fecha_as_rotas_dos_modulos_desligados_para_todos(self):
        with patch.dict(os.environ, {"SIGP_MODULOS": "gestao"}):
            for metodo, rota in (("GET", "/api/sie/resumo"), ("POST", "/api/assistente/perguntar"), ("POST", "/api/sig/decisoes")):
                r = self.client.open(rota, method=metodo, headers=ADMIN, json={})
                self.assertEqual(r.status_code, 404, rota)
                self.assertIn("SIGP_MODULOS=gestao", r.json["error"])
            # O fluxo continua: locais, notas recebidas, faturas, alertas e e-mail das faturas.
            # Os alertas de vencimento e as análises continuam: o WF-06 e o selo "situação da conta" usam (só a aba some).
            for rota in ("/api/locais", "/api/notas-recebidas", "/api/faturas", "/api/configuracoes/email-faturas", "/api/llm/metricas",
                         "/api/alertas?dias=7&tipo=vencimento", "/api/analises"):
                self.assertEqual(self.client.get(rota, headers=ADMIN).status_code, 200, rota)
            # Sem chave continua 401 nas rotas do fluxo (o módulo não abre nada).
            self.assertEqual(self.client.get("/api/locais").status_code, 401)

    def test_gestao_tira_os_modulos_do_catalogo_de_permissoes(self):
        with patch.dict(os.environ, {"SIGP_MODULOS": "gestao"}):
            areas = self.client.get("/api/acesso/catalogo", headers=ADMIN).json["areas"]
        ids = {f["id"] for a in areas for f in a["funcionalidades"]}
        self.assertFalse(ids & acesso.MODULOS_DESLIGADOS["gestao"])
        self.assertIn("notas_recebidas.associar", ids)
        self.assertNotIn("Assistente da IA", {a["area"] for a in areas})


if __name__ == "__main__":
    unittest.main()
