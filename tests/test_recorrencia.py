"""Regra das notas recorrentes na gravação direta (POST /api/notas/lancadas: NFS-e no local, WF-01)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database


def nota(id_, numero="", venc="2026-11-10", emissao="2026-11-01", provedor="OPIX INTERNET", valor=119.9):
    return {"id": id_, "entidadeTipo": "garagem", "entidadeId": "g1", "origem": "manual",
            "dados": {"numero": numero, "provedorNome": provedor, "valor": valor,
                      "dataEmissao": emissao, "dataVencimento": venc}}


class RecorrenciaNotaLancadaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "API_KEY", ""),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def post(self, body):
        return self.client.post("/api/notas/lancadas", json=body)

    def test_mesmo_mes_sem_numero_substitui_a_nota_existente(self):
        primeira = self.post(nota("a", numero="302500")).get_json()["item"]
        r = self.post(nota("b", numero="", emissao="2026-11-03", provedor="OPIX SERVICOS DE TECNOLOGIA EIRELI", valor=120.5))
        self.assertEqual(r.status_code, 200, r.get_json())
        item = r.get_json()["item"]
        self.assertEqual(item["id"], primeira["id"])          # atualizou a nota do mês
        self.assertEqual(item["numero"], "302500")            # número real mantido
        self.assertEqual(item["provedor_nome"], "OPIX INTERNET")  # nome do provedor mantido
        self.assertEqual(float(item["valor_total"]), 120.5)   # valor substituído
        self.assertEqual(item["recorrencia"]["notaSubstituida"], primeira["id"])
        self.assertEqual(len(database.list_nota_lancadas()), 1)

    def test_mes_seguinte_cria_nota_nova(self):
        self.post(nota("a", numero="302500"))
        r = self.post(nota("c", numero="", venc="2026-12-10", emissao="2026-12-01"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["item"]["id"], "c")
        self.assertEqual(len(database.list_nota_lancadas()), 2)

    def test_numero_real_diferente_no_mesmo_mes_e_outra_cobranca(self):
        self.post(nota("a", numero="302500"))
        r = self.post(nota("d", numero="302777"))
        self.assertEqual(r.get_json()["item"]["id"], "d")
        self.assertEqual(len(database.list_nota_lancadas()), 2)

    def test_regravar_sem_numero_mantem_o_numero_real(self):
        self.post(nota("a", numero="302500"))
        r = self.post(nota("a", numero=""))
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["item"]["numero"], "302500")


if __name__ == "__main__":
    unittest.main()
