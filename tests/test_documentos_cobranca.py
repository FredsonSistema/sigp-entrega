"""Documentos da mesma cobrança: o segundo documento de um local/provedor/mês (XML ou NFS-e em PDF, boleto à parte, outro
e-mail) entra como documento adicional e não substitui a fatura principal; associar de novo o mesmo documento não duplica;
divergência confirmada (correção) continua substituindo."""
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database, notas_disponiveis


class DocumentosCobrancaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", self.temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", self.temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", self.temp),
            patch.object(app_module, "API_KEY", ""),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()
        self.local = self.client.post("/api/locais/agencia/item", json={"nome": "Agência Docs", "cidade": "Eunápolis"}).json["item"]["id"]

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    DADOS = {"emissorNome": "Infortel", "numero": "4572", "valorTotal": 1880, "dataEmissao": "2026-11-17", "dataVencimento": "2026-12-05"}

    def receber(self, mensagem, anexo, nome):
        r = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": mensagem, "gmailAttachmentId": anexo, "dadosExtracao": json.dumps(self.DADOS),
            "arquivo": (BytesIO(f"%PDF-1.4 {nome}".encode()), nome)}, content_type="multipart/form-data")
        self.assertIn(r.status_code, (200, 201), r.json)
        return r.json["item"]["id"]

    def associar(self, item_id, **extra):
        r = self.client.patch(f"/api/notas-recebidas/{item_id}/associar",
                              json={"entidadeTipo": "agencia", "entidadeId": self.local, "dados": self.DADOS, **extra})
        self.assertEqual(r.status_code, 200, r.json)
        return r.json

    def test_segundo_documento_da_cobranca_entra_como_adicional(self):
        fatura = self.associar(self.receber("msg-1", "a1", "fatura.pdf"))
        self.assertFalse(fatura["documentoAdicional"])
        danfse = self.associar(self.receber("msg-1", "a2", "nfse.pdf"))
        self.assertTrue(danfse["documentoAdicional"])
        self.assertEqual(danfse["notaDisponivel"]["id"], fatura["notaDisponivel"]["id"])
        faturas = database.list_faturas_locais("agencia", self.local)
        self.assertEqual(len(faturas), 2)
        self.assertEqual(sorted(f["nome_arquivo"] for f in faturas), ["fatura.pdf", "nfse.pdf"])
        for f in faturas:  # os dois arquivos continuam no local
            self.assertTrue((self.temp / f["arquivo_storage"]).is_file(), f["nome_arquivo"])
        self.assertEqual(sum(bool(f["dados"].get("documentoAdicional")) for f in faturas), 1)
        # A fatura atual do provedor e a referência da nota continuam sendo a principal.
        principal = next(f for f in faturas if not f["dados"].get("documentoAdicional"))
        r = self.client.post("/api/notas/lancadas", json={"id": "fin-4572", "source": "json", "entidadeTipo": "agencia", "entidadeId": self.local,
                                                         "dados": {"numero": "4572", "provedorNome": "Infortel", "valor": 1880,
                                                                   "dataEmissao": "2026-11-17", "dataVencimento": "2026-12-05"}})
        self.assertEqual((r.status_code, r.json["notaDisponivelId"]), (200, fatura["notaDisponivel"]["id"]), r.json)
        self.assertEqual(database.latest_fatura_for_nota("fin-4572")["id"], principal["id"])
        provedor = next(p for p in database.get_local(self.local)["provedores"])
        self.assertEqual(provedor["faturaAtualId"], principal["id"])
        # Um terceiro documento (outro e-mail) também soma; e associar de novo o mesmo documento não duplica.
        terceiro = self.receber("msg-2", "a1", "boleto.pdf")
        self.associar(terceiro)
        self.associar(terceiro)
        self.assertEqual(len(database.list_faturas_locais("agencia", self.local)), 3)
        self.assertEqual(len(database.list_nota_lancadas()), 1)  # só a do financeiro
        self.assertEqual(len(notas_disponiveis.listar("agencia", self.local)), 1)


class MigracaoNotasDisponiveisTests(DocumentosCobrancaTests):
    def test_nota_lancada_criada_pelo_gmail_vira_nota_disponivel(self):
        from backend import notas_disponiveis
        item = self.receber("msg-9", "a1", "fatura.pdf")
        self.associar(item)
        disp = notas_disponiveis.listar("agencia", self.local)[0]
        # Simula o estado antigo: a associação tinha criado uma nota lançada "gmail-..." com conciliação.
        conn = database.get_connection()
        conn.execute("""INSERT INTO notas_lancadas (id, entidade_tipo, entidade_id, chave, numero, serie, provedor_nome, local_nome, local_cidade,
            municipio_codigo, valor_total, data_emissao, data_vencimento, status, observacao, servicos_json, origem, arquivo_origem, sistema_origem,
            id_externo, created_at, updated_at) VALUES ('gmail-antiga', 'agencia', ?, '999999999', '4572', '', 'Infortel', 'Agência Docs', '', '',
            1880, '2026-11-17', '2026-12-05', 'PENDENTE', '', '[]', 'gmail', 'x.pdf', 'gmail', 'msg-old', '2026-11-18', '2026-11-18')""", (self.local,))
        conn.execute("DELETE FROM notas_disponiveis")
        conn.execute("UPDATE faturas_locais SET nota_lancada_id = 'gmail-antiga', nota_disponivel_id = ''")
        conn.execute("UPDATE notas_recebidas SET nota_lancada_id = 'gmail-antiga', nota_disponivel_id = ''")
        conn.execute("INSERT INTO conciliacoes (id, nota_lancada_id, nota_paga_id, status, created_at, updated_at) VALUES ('c1', 'gmail-antiga', 'p1', 'MATCH', 'x', 'x')")
        linhas = [{"id": "gmail-antiga", "notaLancada": {"id": "gmail-antiga"}},
                  {"id": "gmail-paga", "notaLancada": {"id": "gmail-paga"}, "notaPaga": {"id": "p1"}, "conciliacao": {}},
                  {"id": "fin-1", "notaLancada": {"id": "fin-1"}}]
        conn.execute("UPDATE locais SET dados_json = ? WHERE id = ?", (json.dumps({"notasFiscais": linhas}), self.local))
        conn.commit()
        conn.close()
        previa = notas_disponiveis.migrar_lancadas_do_gmail(aplicar=False)
        self.assertEqual((previa["total"], previa["aplicado"], previa["notas"][0]["documentos"]), (1, False, 1))
        self.assertIsNotNone(database.get_nota_lancada("gmail-antiga"))  # prévia não muda nada
        feito = notas_disponiveis.migrar_lancadas_do_gmail(aplicar=True)
        self.assertEqual((feito["total"], feito["locaisAlterados"]), (1, 1))
        self.assertIsNone(database.get_nota_lancada("gmail-antiga"))
        self.assertEqual(database.list_conciliacoes(), [])
        self.assertEqual([d["id"] for d in notas_disponiveis.listar("agencia", self.local)], ["gmail-antiga"])
        self.assertEqual(database.list_faturas_locais()[0]["nota_disponivel_id"], "gmail-antiga")
        nf = database.get_local(self.local)["notasFiscais"]
        self.assertEqual([l["id"] for l in nf], ["p1", "fin-1"])  # a do pagamento fica (sem a parte lançada); a do financeiro fica
        self.assertNotIn("notaLancada", nf[0])
        # Cópia antiga da tela com a linha do Gmail: não volta.
        r = self.client.put("/api/locais/agencia", json={"items": [{**database.get_local(self.local), "notasFiscais": linhas}]})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual([l["id"] for l in database.get_local(self.local)["notasFiscais"]], ["p1", "fin-1"])


if __name__ == "__main__":
    unittest.main()
