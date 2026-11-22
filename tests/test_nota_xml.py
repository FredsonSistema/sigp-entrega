"""Fatura PDF + XML da nota fiscal na mesma mensagem: os dois são guardados; o XML vale para os campos fiscais."""
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database
from backend.campos import aplicar_prioridade_xml

RAIZ = Path(__file__).resolve().parents[1]
XML = (RAIZ / "docs" / "XML para testes" / "01-ITABUNA-7001001-CONNECT-FIBRA.xml")
# O que o n8n (n8n/lib/xml_fiscal.js) lê desse XML; aqui fixo, o leitor tem testes próprios em node.
XML_LIDO = {
    "ok": True, "tipoXml": "nfse_abrasf", "numero": "7001001", "serie": "1",
    "chave": "29108001234567800019000000700100170000001", "emissorNome": "CONNECT FIBRA TELECOM LTDA",
    "cnpjEmissor": "12345678000190", "valorTotal": 89.9, "dataEmissao": "2026-11-10", "dataVencimento": "2026-11-20",
    "descricaoServico": "SERVICO DE ACESSO A INTERNET FIBRA OPTICA 300MBPS - MENSALIDADE",
    "servicos": [{"descricao": "SERVICO DE ACESSO A INTERNET FIBRA OPTICA 300MBPS - MENSALIDADE",
                  "quantidade": 1, "valorUnitario": 89.9, "valorTotal": 89.9}],
}


@unittest.skipUnless(XML.exists(), "sem XML de teste")
class NotaXmlTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        (temp / "faturas").mkdir()
        (temp / "recebidas").mkdir()
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp / "faturas"),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp / "recebidas"),
            patch.object(app_module, "API_KEY", ""),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()
        self.xml = XML.read_text(encoding="utf-8")
        self.local = self.client.post("/api/locais/agencia/item", json={"nome": "Agência Itabuna", "cidade": "Itabuna"}).json["item"]

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def receber(self, **campos):
        pdf_lido = {"emissorNome": "CONNECT FIBRA", "numero": "999999999", "valorTotal": 89.9, "dataVencimento": "2026-11-20"}
        dados = aplicar_prioridade_xml(pdf_lido, XML_LIDO)
        dados["xmlFiscal"] = XML_LIDO
        form = {
            "gmailMessageId": "msg-xml-1", "gmailAttachmentId": "a1", "dadosExtracao": json.dumps(dados),
            "arquivo": (BytesIO(b"%PDF-1.4 fatura"), "fatura.pdf"), "xmlConteudo": self.xml,
            "xmlNomeArquivo": XML.name,
        }
        form.update(campos)
        return self.client.post("/api/notas-recebidas", data=form, content_type="multipart/form-data")

    def test_numero_com_zeros_a_esquerda_nao_e_divergencia(self):
        xml = {"ok": True, "numero": "4572", "cnpjEmissor": "54321098000150", "valorTotal": 1880}
        r = aplicar_prioridade_xml({"numero": "000004572", "cnpjEmissor": "54.321.098/0001-50", "valorTotal": 1880}, xml)
        self.assertEqual((r["divergenciasXml"], r["camposParaRevisar"]), ([], []))
        r = aplicar_prioridade_xml({"numero": "4573", "valorTotal": 1880}, xml)
        self.assertEqual([d["campo"] for d in r["divergenciasXml"]], ["numero"])

    def test_pdf_e_xml_guardados_e_xml_vai_para_a_nota_do_local(self):
        r = self.receber()
        self.assertEqual(r.status_code, 201, r.json)
        item = r.json["item"]
        self.assertEqual(item["dados"]["numero"], "7001001")  # XML venceu o padrão do PDF
        self.assertIn("xmlUrl", item)
        baixado = self.client.get(item["xmlUrl"])
        self.assertEqual(baixado.status_code, 200)
        self.assertIn(b"CONNECT FIBRA TELECOM LTDA", baixado.data)
        self.assertTrue(self.client.get(item["downloadUrl"]).data.startswith(b"%PDF"))  # o PDF continua lá

        assoc = self.client.patch(f"/api/notas-recebidas/{item['id']}/associar", json={
            "entidadeTipo": "agencia", "entidadeId": self.local["id"], "dados": item["dados"],
        })
        self.assertEqual(assoc.status_code, 200, assoc.json)
        # Documento do e-mail é NOTA DISPONÍVEL no local; nota lançada é só do financeiro.
        self.assertIsNone(assoc.json["notaLancada"])
        self.assertEqual(database.list_nota_lancadas(), [])
        nota = assoc.json["notaDisponivel"]
        self.assertEqual((nota["numero"], nota["serie"], nota["valor_total"]), ("7001001", "1", 89.9))
        self.assertEqual(nota["servicos"][0]["descricao"][:27], "SERVICO DE ACESSO A INTERNE")
        disp = self.client.get(f"/api/notas-disponiveis?entidadeTipo=agencia&entidadeId={self.local['id']}").json["items"]
        self.assertEqual([d["id"] for d in disp], [nota["id"]])
        xml_da_nota = self.client.get(disp[0]["documentos"][0]["xmlUrl"])
        self.assertEqual(xml_da_nota.status_code, 200, xml_da_nota.json if xml_da_nota.is_json else "")
        self.assertEqual(xml_da_nota.data.decode("utf-8"), self.xml)
        self.assertTrue(self.client.get(disp[0]["documentos"][0]["url"]).data.startswith(b"%PDF"))
        self.assertEqual(len(database.list_faturas_locais()), 1)
        # Cópia antiga da tela tentando regravar como nota lançada: recusada.
        r = self.client.post("/api/notas/lancadas", json={"id": "gmail-copia-antiga", "source": "json", "entidadeTipo": "agencia",
                                                         "entidadeId": self.local["id"], "dados": {"numero": "7001001", "valor": 89.9, "provedorNome": "X"}})
        self.assertEqual((r.status_code, r.json.get("codigo")), (409, "nota_disponivel"))
        # O financeiro lança a nota: ela se liga à nota disponível (mesma chave) e os documentos vão junto.
        r = self.client.post("/api/notas/lancadas", json={"id": "fin-7001001", "source": "json", "entidadeTipo": "agencia",
                                                         "entidadeId": self.local["id"], "dados": {
            "chave": XML_LIDO["chave"], "numero": "7001001", "serie": "1", "provedorNome": "CONNECT FIBRA TELECOM LTDA",
            "valor": 89.9, "dataVencimento": "2026-11-20", "dataEmissao": "2026-11-10"}})
        self.assertEqual((r.status_code, r.json["notaDisponivelId"]), (200, nota["id"]), r.json)
        self.assertEqual(database.list_faturas_locais()[0]["nota_lancada_id"], "fin-7001001")
        self.assertEqual(self.client.get(f"/api/notas-disponiveis?entidadeId={self.local['id']}").json["items"][0]["nota_lancada_id"], "fin-7001001")

    def test_so_xml_entra_em_revisao_e_nao_associa_sem_a_fatura_pdf(self):
        r = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "msg-xml-2", "gmailAttachmentId": "x1",
            "dadosExtracao": json.dumps({**XML_LIDO, "revisaoManual": False}),
            "arquivo": (BytesIO(self.xml.encode("utf-8")), XML.name),
        }, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.json)
        item = r.json["item"]
        self.assertEqual(item["status"], "REVISAO")
        self.assertTrue(item["dados"]["semPdf"])
        self.assertIn("faturaPdf", item["dados"]["camposParaRevisar"])
        self.assertEqual(self.client.get(item["xmlUrl"]).status_code, 200)
        assoc = self.client.patch(f"/api/notas-recebidas/{item['id']}/associar", json={
            "entidadeTipo": "agencia", "entidadeId": self.local["id"], "dados": item["dados"],
        })
        self.assertEqual(assoc.status_code, 409)
        self.assertIn("fatura PDF", assoc.json["error"])
        self.assertEqual(self.client.post(f"/api/notas-recebidas/{item['id']}/extrair").status_code, 422)

    def test_xml_invalido_ou_com_entidade_e_recusado(self):
        self.assertEqual(self.receber(xmlConteudo="isto não é xml").status_code, 400)
        r = self.receber(xmlConteudo='<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><x>&a;</x>')
        self.assertEqual(r.status_code, 400)
        self.assertIn("DOCTYPE", r.json["error"])

    def test_releitura_do_pdf_nao_substitui_os_campos_do_xml(self):
        item = self.receber().json["item"]
        ocr = {"ok": True, "text": "Prestador: OUTRO NOME LTDA\nValor total: R$ 50,00\nVencimento: 01/12/2026\nNº documento: 555"}
        with patch.object(app_module, "urlopen", return_value=BytesIO(json.dumps(ocr).encode())):
            r = self.client.post(f"/api/notas-recebidas/{item['id']}/extrair")
        self.assertEqual(r.status_code, 200, r.json)
        d = r.json["dados"]
        self.assertEqual((d["numero"], d["valorTotal"], d["dataVencimento"], d["emissorNome"]),
                         ("7001001", 89.9, "2026-11-20", "CONNECT FIBRA TELECOM LTDA"))
        self.assertEqual({x["campo"] for x in d["divergenciasXml"]}, {"numero", "valorTotal", "dataVencimento"})

    def test_regravar_a_mesma_nota_com_a_copia_do_navegador_nao_e_duplicidade(self):
        """Bug 14/11/2026: "Enviar para análise" regravava a nota com a chave de 41 dígitos do XML (no banco: 999999999)."""
        item = self.receber().json["item"]
        disp = self.client.patch(f"/api/notas-recebidas/{item['id']}/associar", json={
            "entidadeTipo": "agencia", "entidadeId": self.local["id"], "dados": item["dados"],
        }).json["notaDisponivel"]
        self.assertEqual(disp["chave"], XML_LIDO["chave"])  # chave lida tem prioridade, mesmo fora de 44/50
        # A nota lançada vem do financeiro (com a chave do XML) e se liga à disponível.
        r = self.client.post("/api/notas/lancadas", json={"id": "fin-xml-1", "source": "json", "entidadeTipo": "agencia",
                                                         "entidadeId": self.local["id"], "dados": {
            "chave": XML_LIDO["chave"], "numero": "7001001", "serie": "1", "provedorNome": "CONNECT FIBRA TELECOM LTDA",
            "valor": 89.9, "dataVencimento": "2026-11-20", "dataEmissao": "2026-11-10"}})
        self.assertEqual(r.status_code, 200, r.json)
        nota = r.json["item"]
        copia = {"id": nota["id"], "numero": "7001001", "serie": "1", "provedorNome": nota["provedor_nome"], "valor": 89.9,
                 "dataVencimento": "2026-11-20", "localTipo": "agencia"}
        corpo = lambda **extra: {"id": nota["id"], "source": "json", "entidadeTipo": "agencia", "entidadeId": self.local["id"],
                                 "dados": {**copia, **extra}}
        for extra in ({"chave": XML_LIDO["chave"], "dataEmissao": "2026-11-10"},
                      {"chave": "", "dataEmissao": "2026-11-10T09:30:00-03:00"}):
            r = self.client.post("/api/notas/lancadas", json=corpo(**extra))
            self.assertEqual(r.status_code, 200, (extra, r.json))
        r = self.client.post("/api/notas/lancadas", json=corpo(chave="", dataEmissao="2026-11-10", servicos=[{"descricao": "FIBRA 200MB", "valorTotal": None}]))
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["item"]["servicos"][0]["valorTotal"], 89.9)  # item único sem valor recebe o total
        gravada = database.get_nota_lancada(nota["id"])
        self.assertEqual((gravada["chave"], gravada["numero"], gravada["data_emissao"]), (XML_LIDO["chave"], "7001001", "2026-11-10"))
        # Bug 14/11/2026 (2): cópia antiga com série vazia (no banco, "1" do XML) ao marcar como pago.
        r = self.client.post("/api/notas/lancadas", json=corpo(chave="999999999", serie="", dataEmissao="2026-11-10"))
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(database.get_nota_lancada(nota["id"])["serie"], "1")
        from backend.reconciliation import invoice_identity_matches
        lancada = {"chave": "999999999", "numero": "7001001", "serie": "1", "provedor_nome": "X LTDA", "data_emissao": "2026-11-10"}
        self.assertTrue(invoice_identity_matches(lancada, {**lancada, "serie": ""}))  # série não informada no pagamento
        self.assertFalse(invoice_identity_matches(lancada, {**lancada, "serie": "2"}))  # série diferente diverge
        # Documento realmente diferente com o mesmo id continua recusado: outro número real ou outro local.
        self.assertEqual(self.client.post("/api/notas/lancadas", json=corpo(chave="", numero="7009999", dataEmissao="2026-11-10")).status_code, 409)
        outro_local = {**corpo(chave="", dataEmissao="2026-11-10"), "entidadeId": "outro-local"}
        self.assertEqual(self.client.post("/api/notas/lancadas", json=outro_local).status_code, 409)
        # Corrigir o emitente do mesmo registro (nome fantasia -> razão social) é permitido.
        r = self.client.post("/api/notas/lancadas", json=corpo(chave="", provedorNome="CONNECT FIBRA", dataEmissao="2026-11-10"))
        self.assertEqual(r.status_code, 200, r.json)

    def test_xml_reprocessado_nao_deixa_arquivo_sobrando(self):
        self.receber()
        self.receber()  # reprocessamento da mesma mensagem
        xmls = list((Path(self.temp_dir.name) / "recebidas").glob("*.xml"))
        self.assertEqual(len(xmls), 1, xmls)


if __name__ == "__main__":
    unittest.main()
