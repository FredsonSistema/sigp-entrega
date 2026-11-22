"""Triagem em três níveis: histórico do remetente (3 confirmações) e descarte automático reversível."""
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database

REMETENTE = '"Faturamento" <faturamento@software.example>'


class TriagemRemetenteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp),
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

    def receber(self, msg, decisao="ignorar", remetente=REMETENTE, auto=False):
        dados = {"emissorNome": "Software Exemplo", "valorTotal": 10, "dataVencimento": "2026-11-20", "decisaoIA": decisao,
                 "triagem": {"decisao": decisao, "probabilidade": "baixa", "autoDescarte": auto}}
        return self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": msg, "remetente": remetente, "dadosExtracao": json.dumps(dados),
            "arquivo": (BytesIO(b"%PDF-1.4 x"), f"{msg}.pdf"),
        }, content_type="multipart/form-data").json["item"]

    def historico(self):
        r = self.client.post("/api/notas-recebidas/classificar", json={"texto": "NFS-e locação de software", "remetente": REMETENTE})
        return r.json["classificacao"]["remetente"]

    def test_conta_so_confirmacoes_humanas_do_mesmo_endereco(self):
        ids = [self.receber(f"m{i}")["id"] for i in range(3)]
        self.receber("outro", remetente="x@outro.example")
        self.assertEqual(self.historico()["confirmadosNaoCobranca"], 0)
        self.client.post("/api/notas-recebidas/ignorados/confirmar", json={"ids": ids, "operador": "ana"})
        h = self.historico()
        self.assertEqual((h["endereco"], h["confirmadosNaoCobranca"], h["cobrancasConfirmadas"]),
                         ("faturamento@software.example", 3, 0))
        # Descarte automático não conta como confirmação (não se realimenta).
        auto = self.receber("m-auto", auto=True)
        self.assertEqual(auto["status"], "DESCARTADA")
        self.assertEqual(auto["dados"]["descarte"]["operador"], database.OPERADOR_AUTOMATICO)
        self.assertEqual(auto["dados"]["descarte"]["motivo"], "nao_cobranca")
        self.assertEqual(self.historico()["confirmadosNaoCobranca"], 3)

    def test_descarte_automatico_pode_ser_restaurado(self):
        auto = self.receber("m-auto", auto=True)
        r = self.client.patch(f"/api/notas-recebidas/{auto['id']}/restaurar", json={"operador": "ana"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertNotEqual(database.get_nota_recebida(auto["id"])["status"], "DESCARTADA")

    def test_sem_auto_descarte_continua_na_fila_de_ignorados(self):
        self.assertEqual(self.receber("m1")["status"], "IGNORADA_IA")
        self.assertEqual(self.receber("m2", decisao="importar")["status"], "AGUARDANDO_ASSOCIACAO")


if __name__ == "__main__":
    unittest.main()
