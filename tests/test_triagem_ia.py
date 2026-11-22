"""Etapa 2 — triagem pela IA: tudo é gravado; ignorados ficam numa fila própria; confirmar e resgatar viram exemplos."""
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database


class TriagemIATests(unittest.TestCase):
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

    def receber(self, msg, decisao, execucao="exec-1", **extra):
        dados = {"emissorNome": "Hotel Exemplo", "valorTotal": 10, "dataVencimento": "2026-11-20", "decisaoIA": decisao,
                 "triagem": {"decisao": decisao, "execucaoId": execucao, "em": f"2026-11-14T10:00:{msg[-1]}0Z",
                             "motivo": "recibo de hotel", "confianca": 0.9}, **extra}
        return self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": msg, "dadosExtracao": json.dumps(dados),
            "arquivo": (BytesIO(b"%PDF-1.4 x"), f"{msg}.pdf"),
        }, content_type="multipart/form-data").json["item"]

    def test_ignorado_fica_fora_da_caixa_e_resumo_por_execucao(self):
        ign1, ign2 = self.receber("m1", "ignorar"), self.receber("m2", "ignorar")
        ok = self.receber("m3", "importar")
        self.assertEqual((ign1["status"], ok["status"]), ("IGNORADA_IA", "AGUARDANDO_ASSOCIACAO"))
        caixa = [i["id"] for i in self.client.get("/api/notas-recebidas").json["items"]]
        self.assertEqual(caixa, [ok["id"]])  # "Todos" não mostra os ignorados
        fila = {i["id"] for i in self.client.get("/api/notas-recebidas?status=IGNORADA_IA").json["items"]}
        self.assertEqual(fila, {ign1["id"], ign2["id"]})
        r = self.client.get("/api/notas-recebidas/triagem").json
        self.assertEqual(r["ignoradosPendentes"], 2)
        e = r["execucoes"][0]
        self.assertEqual((e["execucaoId"], e["documentos"], e["paraCaixa"], e["ignorados"]), ("exec-1", 3, 1, 2))
        # Ignorado não pode ser associado sem resgate.
        local = self.client.post("/api/locais/agencia/item", json={"nome": "Agência X", "cidade": "Ilhéus"}).json["item"]
        assoc = self.client.patch(f"/api/notas-recebidas/{ign1['id']}/associar",
                                  json={"entidadeTipo": "agencia", "entidadeId": local["id"], "dados": {}})
        self.assertEqual(assoc.status_code, 409)

    def test_confirmar_em_lote_e_resgatar_viram_exemplos(self):
        ign1, ign2, ign3 = (self.receber(m, "ignorar") for m in ("m1", "m2", "m3"))
        r = self.client.post("/api/notas-recebidas/ignorados/confirmar",
                             json={"ids": [ign1["id"], ign2["id"], "nrec-inexistente"], "operador": "ana"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(len(r.json["confirmados"]), 2)
        self.assertEqual(database.get_nota_recebida(ign1["id"])["status"], "DESCARTADA")
        self.assertEqual(database.get_nota_recebida(ign1["id"])["dados"]["descarte"]["motivo"], "nao_cobranca")
        res = self.client.patch(f"/api/notas-recebidas/{ign3['id']}/resgatar", json={"operador": "ana"})
        self.assertEqual(res.json["item"]["status"], "AGUARDANDO_ASSOCIACAO")
        self.assertEqual(res.json["item"]["dados"]["triagem"]["resgatadoPor"], "ana")
        self.assertEqual(self.client.patch(f"/api/notas-recebidas/{ign3['id']}/resgatar", json={}).status_code, 409)
        conn = database.get_connection()
        tipos = sorted(row["tipo"] for row in conn.execute("SELECT tipo FROM extracao_feedback"))
        conn.close()
        self.assertEqual(tipos, ["ignorado_confirmado", "ignorado_confirmado", "ignorado_resgatado"])
        resumo = self.client.get("/api/notas-recebidas/triagem").json
        self.assertEqual((resumo["ignoradosPendentes"], resumo["execucoes"][0]["resgatados"]), (0, 1))

    def test_reprocessamento_pode_tirar_da_fila_de_ignorados(self):
        ign = self.receber("m1", "ignorar")
        de_novo = self.receber("m1", "importar", execucao="exec-2")
        self.assertEqual(de_novo["id"], ign["id"])
        self.assertEqual(de_novo["status"], "AGUARDANDO_ASSOCIACAO")


if __name__ == "__main__":
    unittest.main()
