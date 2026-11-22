"""Cofre de chaves (backend/cofre.py): o valor é gravado criptografado e nunca aparece na API, no banco, na auditoria ou nos logs."""
import io
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import cofre, database

ADMIN = {"X-API-Key": "chave-admin-teste"}
SEGREDO = "GOCSPX-segredoFicticioDeTeste_1234567890abcdWXYZ"
CLIENT_ID = "123456789012-ficticio0abcdefghijklmnop.apps.googleusercontent.com"


class CofreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_dir.name)
        self.chave = cofre.gerar_chave()
        self.patches = [
            patch.object(database, "DB_PATH", self.temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", self.temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", self.temp),
            patch.object(app_module, "API_KEY", ADMIN["X-API-Key"]),
            patch.dict(os.environ, {cofre.VARIAVEL: self.chave}),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def _salvar(self, nome="google_client_secret", valor=SEGREDO, headers=ADMIN):
        return self.client.put(f"/api/cofre/{nome}", headers=headers, json={"valor": valor})

    def _item(self, dados, nome="google_client_secret"):
        return next(s for s in dados["segredos"] if s["nome"] == nome)

    def test_salva_e_mostra_so_o_final_nunca_o_valor(self):
        r = self._salvar()
        self.assertEqual(r.status_code, 200, r.json)
        lido = self.client.get("/api/cofre", headers=ADMIN)
        item = self._item(lido.json)
        self.assertTrue(item["definido"] and item["legivel"])
        self.assertEqual((item["final"], item["atualizadoPor"]), ("WXYZ", "Administrador"))
        for resposta in (r, lido):
            self.assertNotIn(SEGREDO, resposta.get_data(as_text=True))
            self.assertNotIn(SEGREDO[:-4], resposta.get_data(as_text=True))
        self.assertEqual(cofre.ler_valor("google_client_secret"), SEGREDO)

    def test_valor_nao_aparece_no_banco_na_auditoria_nem_nos_logs(self):
        saida = io.StringIO()
        handler = logging.StreamHandler(saida)
        raiz = logging.getLogger()
        nivel = raiz.level
        raiz.addHandler(handler)
        raiz.setLevel(logging.DEBUG)
        try:
            self._salvar()
            self._salvar("google_client_id", CLIENT_ID)
            self._salvar(valor="com espaço " + SEGREDO)  # erro de validação também não pode ecoar o valor
            erro = self._salvar(valor="com espaço " + SEGREDO)
        finally:
            raiz.removeHandler(handler)
            raiz.setLevel(nivel)
        self.assertNotIn(SEGREDO, erro.get_data(as_text=True))
        self.assertNotIn(SEGREDO, saida.getvalue())
        bruto = b"".join(p.read_bytes() for p in self.temp.glob("test.db*"))
        conn = database.get_connection()
        cifrado = conn.execute("SELECT cifrado FROM cofre_segredos WHERE nome='google_client_secret'").fetchone()[0]
        conn.close()
        self.assertIn(cifrado.encode(), bruto, "controle: o texto cifrado precisa estar no arquivo lido")
        for valor in (SEGREDO, CLIENT_ID, SEGREDO[5:25]):
            self.assertNotIn(valor.encode(), bruto, "valor em texto puro no arquivo do banco")
        auditoria = json.dumps(self.client.get("/api/acesso/auditoria", headers=ADMIN).json, ensure_ascii=False)
        self.assertIn("/api/cofre/<nome>", auditoria)
        self.assertNotIn(SEGREDO, auditoria)

    def test_sem_chave_mestra_nao_grava_nada(self):
        with patch.dict(os.environ, {cofre.VARIAVEL: ""}):
            r = self._salvar()
            self.assertEqual(r.status_code, 400)
            self.assertIn("SIGP_COFRE_CHAVE", r.json["error"])
            self.assertFalse(self.client.get("/api/cofre", headers=ADMIN).json["disponivel"])
        with patch.dict(os.environ, {cofre.VARIAVEL: "curta-demais"}):
            self.assertEqual(self._salvar().status_code, 400)
        self.assertFalse(self._item(self.client.get("/api/cofre", headers=ADMIN).json)["definido"])

    def test_outra_chave_mestra_nao_decifra_e_pede_para_colar_de_novo(self):
        self._salvar()
        with patch.dict(os.environ, {cofre.VARIAVEL: cofre.gerar_chave()}):
            self.assertFalse(self._item(self.client.get("/api/cofre", headers=ADMIN).json)["legivel"])
            with self.assertRaisesRegex(cofre.CofreErro, "outra chave mestra"):
                cofre.ler_valor("google_client_secret")

    def test_valor_alterado_ou_trocado_de_lugar_no_banco_e_recusado(self):
        self._salvar()
        self._salvar("google_client_id", CLIENT_ID)
        conn = database.get_connection()
        try:
            cifrado = conn.execute("SELECT cifrado FROM cofre_segredos WHERE nome='google_client_secret'").fetchone()[0]
            # Copiar o segredo para o lugar do Client ID: o nome autenticado não bate.
            conn.execute("UPDATE cofre_segredos SET cifrado=? WHERE nome='google_client_id'", (cifrado,))
            # Mudar um caractere do segredo: a etiqueta do GCM não bate.
            meio = len(cifrado) // 2
            conn.execute("UPDATE cofre_segredos SET cifrado=? WHERE nome='google_client_secret'",
                         (cifrado[:meio] + ("A" if cifrado[meio] != "A" else "B") + cifrado[meio + 1:],))
            conn.commit()
        finally:
            conn.close()
        for nome in ("google_client_id", "google_client_secret"):
            with self.assertRaisesRegex(cofre.CofreErro, "corrompido ou foi alterado"):
                cofre.ler_valor(nome)

    def test_cada_gravacao_usa_um_nonce_novo(self):
        self._salvar()
        conn = database.get_connection()
        primeiro = conn.execute("SELECT cifrado FROM cofre_segredos").fetchone()[0]
        conn.close()
        self._salvar()
        conn = database.get_connection()
        segundo = conn.execute("SELECT cifrado FROM cofre_segredos").fetchone()[0]
        conn.close()
        self.assertNotEqual(primeiro, segundo)

    def test_valores_invalidos_e_nome_desconhecido(self):
        for ruim in ["", "   ", "com espaco no meio", "linha\nquebrada", "x" * 301, None, 123]:
            self.assertEqual(self._salvar(valor=ruim).status_code, 400, repr(ruim))
        self.assertEqual(self._salvar("senha_do_banco").status_code, 404)
        self.assertEqual(self.client.delete("/api/cofre/senha_do_banco", headers=ADMIN).status_code, 404)

    def test_valor_curto_nao_mostra_final(self):
        self._salvar("google_client_id", "curto-123")
        self.assertEqual(self._item(self.client.get("/api/cofre", headers=ADMIN).json, "google_client_id")["final"], "")

    def test_apagar(self):
        self._salvar()
        r = self.client.delete("/api/cofre/google_client_secret", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self._item(r.json)["definido"])
        self.assertIsNone(cofre.ler_valor("google_client_secret"))

    def test_sem_permissao_nao_ve_nem_grava(self):
        r = self.client.post("/api/acesso/usuarios", headers=ADMIN, json={"nome": "Leitor", "grupoId": "grp-leitura"})
        leitor = {"X-API-Key": r.json["chave"]}
        self.assertEqual(self.client.get("/api/cofre", headers=leitor).status_code, 403)
        self.assertEqual(self._salvar(headers=leitor).status_code, 403)
        self.assertEqual(self.client.delete("/api/cofre/google_client_secret", headers=leitor).status_code, 403)
        self.assertEqual(self.client.get("/api/cofre").status_code, 401)
        self.assertEqual(self._salvar(headers={}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
