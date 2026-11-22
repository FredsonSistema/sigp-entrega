"""Situações 3 a 5: o mesmo provedor em vários locais; o código do cliente/contrato aprendido decide o local."""
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database


class CodigosClienteTests(unittest.TestCase):
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
        # Três agências em Itabuna; HE-NET atende duas (e a terceira tem outro provedor).
        self.a = self.local("Agência Itabuna Centro", [{"id": "pa", "nome": "HE-NET"}])
        self.b = self.local("Agência Itabuna São Caetano", [{"id": "pb", "nome": "HE-NET"}, {"id": "pb2", "nome": "Vivo"}])
        self.c = self.local("Agência Itabuna Pontalzinho", [{"id": "pc", "nome": "Vivo"}])

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def local(self, nome, provedores):
        item = self.client.post("/api/locais/agencia/item", json={"nome": nome, "cidade": "Itabuna"}).json["item"]
        conn = database.get_connection()
        try:
            conn.execute("UPDATE locais SET provedores_json = ? WHERE id = ?", (json.dumps(provedores), item["id"]))
            conn.commit()
        finally:
            conn.close()
        return item

    def receber(self, msg, codigos, venc="2026-11-20"):
        dados = {"emissorNome": "HE-NET TELECOMUNICACOES LTDA", "valorTotal": 150, "dataVencimento": venc, "numero": msg[-4:],
                 "identificadoresCliente": [{"tipo": "contrato", "valor": c} for c in codigos]}
        return self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": msg, "remetente": "HE-NET <boleto@henet.com.br>", "dadosExtracao": json.dumps(dados),
            "arquivo": (BytesIO(b"%PDF-1.4 x"), f"{msg}.pdf")}, content_type="multipart/form-data").json["item"]

    def associar(self, item, local):
        return self.client.patch(f"/api/notas-recebidas/{item['id']}/associar", json={
            "entidadeTipo": "agencia", "entidadeId": local["id"], "dados": item["dados"]})

    def provedor(self, local, nome="HE-NET"):
        return next(p for p in database.get_local(local["id"])["provedores"] if p["nome"].startswith(nome[:4]))

    def test_associacao_ensina_e_proxima_fatura_vem_com_o_local_certo(self):
        primeira = self.receber("m-0001", ["004821"])
        sem_codigo = self.client.get(f"/api/notas-recebidas?status=AGUARDANDO_ASSOCIACAO").json["items"][0]
        self.assertEqual(sem_codigo.get("provedorEmVariosLocais"), 2)  # HE-NET atende 2 locais: confira
        r = self.associar(primeira, self.b)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["codigosAprendidos"], ["004821"])
        self.assertEqual(r.json["provedor"]["codigosCliente"], "004821")  # o navegador recebe e não apaga
        self.assertEqual(self.provedor(self.b)["codigosCliente"], "004821")
        self.assertNotIn("codigosCliente", self.provedor(self.a))
        # Dezembro: o mesmo contrato (escrito sem zeros) já sugere a Agência São Caetano primeiro.
        dezembro = self.receber("m-0002", ["4821"], venc="2026-12-20")
        item = next(i for i in self.client.get("/api/notas-recebidas").json["items"] if i["id"] == dezembro["id"])
        self.assertEqual(item["sugestoesLocal"][0]["id"], self.b["id"])
        self.assertIn("4821", item["sugestoesLocal"][0]["motivo"])
        self.assertNotIn("provedorEmVariosLocais", item)

    def test_codigo_ja_em_outro_local_nao_e_guardado(self):
        self.associar(self.receber("m-0003", ["7777"]), self.a)
        r = self.associar(self.receber("m-0004", ["7777"], venc="2026-12-20"), self.b)
        self.assertEqual((r.json["codigosAprendidos"], r.json["codigosEmOutroLocal"]), ([], ["7777"]))
        self.assertNotIn("7777", str(self.provedor(self.b).get("codigosCliente") or ""))

    def test_dois_provedores_no_mesmo_local_cada_um_com_seu_codigo(self):
        self.associar(self.receber("m-0005", ["5150"]), self.b)
        self.assertEqual(self.provedor(self.b)["codigosCliente"], "5150")
        self.assertNotIn("codigosCliente", self.provedor(self.b, "Vivo"))

    def test_aviso_de_pagamento_usa_o_codigo_para_achar_o_local(self):
        self.associar(self.receber("m-0006", ["4242"]), self.b)
        # Fatura de novembro lançada nos dois locais (HE-NET): só o código diz qual foi paga.
        outra = self.receber("m-0007", [], venc="2026-11-20")
        self.associar(outra, self.a)
        aviso = {"emissorNome": "HE-NET", "evento": {"tipo": "pagamento_confirmado"}, "identificadoresCliente": [{"tipo": "contrato", "valor": "4242"}]}
        r = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "m-pago", "remetente": "HE-NET <boleto@henet.com.br>", "dadosExtracao": json.dumps(aviso),
            "arquivo": (BytesIO(b"%PDF-1.4 x"), "comprovante.pdf")}, content_type="multipart/form-data").json["item"]
        self.assertEqual((r["status"], r["entidade_id"]), ("AVISO", self.b["id"]), r["dados"].get("aviso"))


if __name__ == "__main__":
    unittest.main()
