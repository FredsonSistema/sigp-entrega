"""E-mails dos alertas diários: Configurações > Alertas por e-mail, lidos pelo WF-06 (GET /api/configuracoes/alertas)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import config_alertas, database

ADMIN = {"X-API-Key": "chave-admin-teste"}


class ConfigAlertasTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp),
            patch.object(app_module, "API_KEY", ADMIN["X-API-Key"]),
            patch.dict(os.environ, {"SIGP_RELATORIO_EMAIL": ""}),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_sem_nada_configurado_nao_ha_destinatario(self):
        r = self.client.get("/api/configuracoes/alertas", headers=ADMIN).json
        self.assertEqual((r["emails"], r["origem"]), ([], "nenhum"))

    def test_padrao_vem_do_env_com_varios_enderecos(self):
        with patch.dict(os.environ, {"SIGP_RELATORIO_EMAIL": "A@Empresa.com.br; b@empresa.com.br, a@empresa.com.br"}):
            r = self.client.get("/api/configuracoes/alertas", headers=ADMIN).json
        self.assertEqual((r["emails"], r["origem"]), (["a@empresa.com.br", "b@empresa.com.br"], ".env"))

    def test_administrador_salva_um_ou_mais_e_a_tela_vale_mais_que_o_env(self):
        with patch.dict(os.environ, {"SIGP_RELATORIO_EMAIL": "env@empresa.com.br"}):
            r = self.client.put("/api/configuracoes/alertas", headers=ADMIN,
                                json={"emails": ["Fredson@Empresa.com.br", "contas@empresa.com.br", "fredson@empresa.com.br", ""]})
            self.assertEqual(r.status_code, 200, r.json)
            lido = self.client.get("/api/configuracoes/alertas", headers=ADMIN).json
        self.assertEqual(lido["emails"], ["fredson@empresa.com.br", "contas@empresa.com.br"])
        self.assertEqual((lido["origem"], lido["atualizadoPor"]), ("tela", "Administrador"))
        self.assertTrue(lido["atualizadoEm"])

    def test_lista_vazia_salva_desliga_o_envio_mesmo_com_env(self):
        with patch.dict(os.environ, {"SIGP_RELATORIO_EMAIL": "env@empresa.com.br"}):
            self.client.put("/api/configuracoes/alertas", headers=ADMIN, json={"emails": []})
            lido = self.client.get("/api/configuracoes/alertas", headers=ADMIN).json
        self.assertEqual((lido["emails"], lido["origem"]), ([], "tela"))

    def test_email_invalido_ou_lista_grande_e_recusado(self):
        r = self.client.put("/api/configuracoes/alertas", headers=ADMIN, json={"emails": ["sem-arroba.com.br"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("E-mail inválido", r.json["error"])
        r = self.client.put("/api/configuracoes/alertas", headers=ADMIN, json={"emails": "a@b.com\nc@d.com"})
        self.assertEqual(r.status_code, 200)
        muitos = [f"u{i}@empresa.com.br" for i in range(config_alertas.MAX_EMAILS + 1)]
        r = self.client.put("/api/configuracoes/alertas", headers=ADMIN, json={"emails": muitos})
        self.assertEqual(r.status_code, 400)
        r = self.client.put("/api/configuracoes/alertas", headers=ADMIN, json={"emails": ["x@y.com', 'z"]})
        self.assertEqual(r.status_code, 400)

    def test_sem_permissao_nao_ve_nem_altera(self):
        r = self.client.post("/api/acesso/usuarios", headers=ADMIN, json={"nome": "Leitor", "grupoId": "grp-leitura"})
        leitor = {"X-API-Key": r.json["chave"]}
        self.assertEqual(self.client.get("/api/configuracoes/alertas", headers=leitor).status_code, 403)
        self.assertEqual(self.client.put("/api/configuracoes/alertas", headers=leitor, json={"emails": []}).status_code, 403)
        self.assertEqual(self.client.put("/api/configuracoes/alertas", json={"emails": []}).status_code, 401)
        # Os e-mails são dado pessoal: ler sem chave também é recusado, mesmo com a leitura aberta.
        self.assertEqual(self.client.get("/api/configuracoes/alertas").status_code, 401)


if __name__ == "__main__":
    unittest.main()
