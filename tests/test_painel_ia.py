"""Etapa 5 — métricas da LLM e saúde do banco."""
import json
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database, metricas_llm, saude_banco


def nota(status, tipo, mes="2026-11", exemplos=(), descarte=None, duracao=None, nivel=None, resgatado=False):
    dados = {"classificacao": {"ia": {"tipoDocumento": tipo, "confianca": 0.9, "exemplosUsados": list(exemplos),
                                      **({"duracaoMs": duracao} if duracao else {})}},
             "triagem": {"probabilidade": nivel, **({"resgatadoEm": "x"} if resgatado else {})}}
    if descarte:
        dados["descarte"] = descarte
    return {"status": status, "recebida_em": f"{mes}-10T10:00:00Z", "dados": dados}


HUMANO = {"motivo": "nao_cobranca", "operador": "ana"}


class MetricasTests(unittest.TestCase):
    def test_acuracia_da_triagem_com_e_sem_exemplos(self):
        notas = [
            nota("ASSOCIADA", "boleto_fatura", exemplos=["e1"], duracao=1000, nivel="alta"),  # acerto
            nota("DESCARTADA", "outro", descarte=HUMANO, duracao=3000, nivel="baixa"),         # acerto
            nota("DESCARTADA", "nota_fiscal", descarte=HUMANO, exemplos=["e2"]),                # falso positivo
            nota("AGUARDANDO_ASSOCIACAO", "outro", resgatado=True),                             # falso negativo
            nota("DESCARTADA", "outro", descarte={"motivo": "nao_cobranca", "operador": "sigp-ia"}),  # automático: fora
            nota("DESCARTADA", "boleto_fatura", descarte={"motivo": "duplicada", "operador": "ana"}),  # outro motivo: fora
            nota("REVISAO", "boleto_fatura", nivel="inconclusivo"),                              # sem decisão: fora
            nota("ASSOCIADA", "boleto_fatura", mes="2026-01"),                                   # fora da janela
        ]
        r = metricas_llm.calcular(notas, [], meses=3, hoje=date(2026, 11, 14))
        t = r["total"]
        self.assertEqual([m["mes"] for m in r["mensal"]], ["2026-09", "2026-10", "2026-11"])
        self.assertEqual((t["documentos"], t["decididos"], t["acertos"]), (7, 4, 2))
        self.assertEqual((t["falsoPositivo"], t["falsoNegativo"], t["descartesAutomaticos"]), (1, 1, 1))
        self.assertEqual(t["acuracia"], 0.5)
        self.assertEqual((t["comExemplos"]["decididos"], t["comExemplos"]["acertos"]), (2, 1))
        self.assertEqual(t["niveis"]["alta"], 1)
        self.assertEqual(t["tempoMedianoMs"], 2000)

    def test_campos_e_local_vem_do_feedback_da_associacao(self):
        fb = {"tipo": "associada", "created_at": "2026-11-12T00:00:00Z", "entidade_id": "loc-1",
              "extraidos": {"emissorNome": "Fibra X", "numero": "", "valorTotal": 99.9, "dataVencimento": "2026-11-20"},
              "finais": {"emissorNome": "FIBRA X", "numero": "999999999", "valorTotal": 100.0, "dataVencimento": "2026-11-20",
                         "sugestaoLocalId": "loc-1"}}
        r = metricas_llm.calcular([], [fb], meses=1, hoje=date(2026, 11, 14))
        c = r["total"]["campos"]
        self.assertEqual((c["total"], c["corretos"]), (4, 3))  # só o valor foi corrigido
        self.assertEqual(c["porCampo"]["valorTotal"]["acuracia"], 0.0)
        self.assertEqual(r["total"]["local"]["acuracia"], 1.0)

    def test_modelo_indisponivel_nao_quebra(self):
        estado = metricas_llm.estado_modelo("http://127.0.0.1:9", "qwen2.5:3b", timeout=0.2)
        self.assertFalse(estado["disponivel"])


class SaudeBancoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "sigp.db"
        with patch.object(database, "DB_PATH", self.db):
            database.init_db()
        self.pastas = {"notas_recebidas": self.dir / "nr"}
        self.pastas["notas_recebidas"].mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_banco_novo_sem_backup_pede_atencao(self):
        r = saude_banco.verificar(self.db, self.dir / "backups", self.pastas)
        self.assertTrue(r["verificacao"]["ok"])
        self.assertEqual(r["status"], "atencao")
        self.assertIn("Nenhum backup", " ".join(r["avisos"]))

    def test_backup_verificado_e_rodizio(self):
        backups = self.dir / "backups"
        inicio = datetime(2026, 11, 14, 3, 0, tzinfo=timezone.utc)
        for dias in range(40, -1, -1):  # 41 dias de backups diários
            saude_banco.fazer_backup(self.db, backups, agora=inicio - timedelta(days=dias))
        restantes = saude_banco.listar_backups(backups)
        self.assertLessEqual(len(restantes), 11)  # 7 diários + até 4 semanais
        self.assertEqual(restantes[0]["arquivo"], "sigp-20261114-030000.db")
        conn = sqlite3.connect(restantes[-1]["_caminho"])
        self.assertEqual(conn.execute("PRAGMA quick_check").fetchone()[0], "ok")
        conn.close()

    def test_arquivo_orfao_e_ausente(self):
        (self.pastas["notas_recebidas"] / "sobrando.pdf").write_bytes(b"%PDF")
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("INSERT INTO notas_recebidas (id, gmail_message_id, gmail_attachment_id, nome_arquivo, arquivo_storage,"
                         " dados_json, status, created_at, updated_at)"
                         " VALUES ('n1', 'm', 'a', 'sumiu.pdf', 'sumiu.pdf', '{}', 'REVISAO', 'x', 'x')")
            conn.commit()
        finally:
            conn.close()
        r = saude_banco.verificar(self.db, self.dir / "backups", self.pastas)
        self.assertEqual((r["arquivos"]["orfaos"], r["arquivos"]["ausentes"]), (1, 1))

    def test_manutencao(self):
        r = saude_banco.manutencao(self.db)
        self.assertTrue(r["optimize"])


class RotasPainelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        temp = Path(self.tmp.name)
        self.patches = [patch.object(database, "DB_PATH", temp / "test.db"), patch.object(app_module, "FATURAS_DIR", temp),
                        patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp), patch.object(app_module, "API_KEY", ""),
                        patch.object(metricas_llm, "estado_modelo", return_value={"disponivel": False})]
        for p in self.patches:
            p.start()
        database.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_rotas(self):
        r = self.client.get("/api/llm/metricas?meses=2").json
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["mensal"]), 2)
        b = self.client.post("/api/saude/banco/backup").json
        self.assertTrue(b["ok"] and b["verificado"], b)
        s = self.client.get("/api/saude/banco").json
        self.assertEqual(s["backups"]["quantidade"], 1)
        self.assertTrue(self.client.post("/api/saude/banco/manutencao").json["ok"])

    def test_associacao_grava_o_local_sugerido(self):
        local = self.client.post("/api/locais/agencia/item", json={"nome": "Agência X", "cidade": "Ilhéus"}).json["item"]
        item = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "m1", "dadosExtracao": json.dumps({"emissorNome": "Fibra X", "valorTotal": 10, "dataVencimento": "2026-12-10"}),
            "arquivo": (BytesIO(b"%PDF-1.4 x"), "a.pdf")}, content_type="multipart/form-data").json["item"]
        r = self.client.patch(f"/api/notas-recebidas/{item['id']}/associar", json={"entidadeTipo": "agencia", "entidadeId": local["id"], "dados": {}})
        self.assertEqual(r.status_code, 200, r.json)
        fb = [f for f in database.listar_feedback() if f["tipo"] == "associada"][0]
        self.assertIn("sugestaoLocalId", fb["finais"])


if __name__ == "__main__":
    unittest.main()
