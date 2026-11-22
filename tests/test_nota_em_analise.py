"""Nota recebida "Em análise": nota em dúvida fica separada, sem associar nem descartar, até o operador decidir."""
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database


class NotaEmAnaliseTests(unittest.TestCase):
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

    def receber(self, valor=100):
        return self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "msg-1", "gmailAttachmentId": "a1", "assunto": "Fatura",
            "dadosExtracao": json.dumps({"emissorNome": "Provedor", "valorTotal": valor, "dataVencimento": "2026-11-20"}),
            "arquivo": (BytesIO(b"%PDF-1.4 x"), "fatura.pdf"),
        }, content_type="multipart/form-data")

    def test_em_analise_sai_da_fila_preserva_observacao_e_volta(self):
        item_id = self.receber().json["item"]["id"]
        r = self.client.patch(f"/api/notas-recebidas/{item_id}/analise",
                              json={"observacao": "confirmar local com o gerente", "operador": "ana"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["item"]["status"], "EM_ANALISE")
        self.assertEqual(r.json["item"]["dados"]["analise"]["observacao"], "confirmar local com o gerente")
        filtro = self.client.get("/api/notas-recebidas?status=EM_ANALISE").json["items"]
        self.assertEqual([i["id"] for i in filtro], [item_id])
        self.assertEqual(self.client.get("/api/notas-recebidas?status=AGUARDANDO_ASSOCIACAO").json["items"], [])

        # Reprocessamento do Gmail não tira a nota da análise nem troca a extração.
        self.receber(valor=999)
        atual = database.get_nota_recebida(item_id)
        self.assertEqual(atual["status"], "EM_ANALISE")
        self.assertEqual(atual["dados"]["valorTotal"], 100)

        volta = self.client.patch(f"/api/notas-recebidas/{item_id}/liberar", json={"operador": "ana"})
        self.assertEqual(volta.status_code, 200, volta.json)
        self.assertEqual(volta.json["item"]["status"], "AGUARDANDO_ASSOCIACAO")
        self.assertEqual(volta.json["item"]["dados"]["analiseAnterior"]["observacao"], "confirmar local com o gerente")

    def test_em_analise_pode_ser_descartada_e_restaurada_para_analise(self):
        item_id = self.receber().json["item"]["id"]
        self.client.patch(f"/api/notas-recebidas/{item_id}/analise", json={})
        d = self.client.patch(f"/api/notas-recebidas/{item_id}/descartar", json={"motivo": "duplicada"})
        self.assertEqual(d.json["item"]["status"], "DESCARTADA")
        # Descartada não entra em análise; restaurar devolve ao estado anterior (em análise).
        self.assertEqual(self.client.patch(f"/api/notas-recebidas/{item_id}/analise", json={}).status_code, 409)
        r = self.client.patch(f"/api/notas-recebidas/{item_id}/restaurar", json={})
        self.assertEqual(r.json["item"]["status"], "EM_ANALISE")

    def test_leitura_antiga_avisa_e_a_releitura_grava_preservando_o_resto(self):
        item = self.receber().json["item"]  # sem versaoRegras = leitura antiga
        self.assertTrue(item["leituraDesatualizada"])
        database.colocar_em_analise(item["id"], "conferir", "ana")
        ocr = {"ok": True, "text": "Prestador: OPIX INTERNET LTDA\nNº documento: 302500\nValor total: R$ 119,90\nVencimento: 10/11/2026"}
        with patch.object(app_module, "urlopen", return_value=BytesIO(json.dumps(ocr).encode())):
            r = self.client.post(f"/api/notas-recebidas/{item['id']}/extrair")
        self.assertTrue(r.json["gravada"], r.json)
        salvo = database.get_nota_recebida(item["id"])
        self.assertEqual((salvo["dados"]["numero"], salvo["dados"]["valorTotal"]), ("302500", 119.9))
        self.assertEqual(salvo["status"], "EM_ANALISE")
        self.assertEqual(salvo["dados"]["analise"]["observacao"], "conferir")  # o que não é leitura fica
        lista = self.client.get("/api/notas-recebidas?status=EM_ANALISE").json["items"]
        self.assertFalse(lista[0]["leituraDesatualizada"])

    def test_liberar_exige_estar_em_analise_e_404(self):
        item_id = self.receber().json["item"]["id"]
        self.assertEqual(self.client.patch(f"/api/notas-recebidas/{item_id}/liberar", json={}).status_code, 409)
        self.assertEqual(self.client.patch("/api/notas-recebidas/nrec-x/analise", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
