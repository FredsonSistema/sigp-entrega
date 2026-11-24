"""Entrada manual em Notas recebidas: fatura PDF e/ou XML enviados pela tela (provedor que ainda não manda e-mail).

O documento entra na mesma caixa, passa pela mesma leitura e IA do e-mail (WF-10 no n8n), não recebe etiqueta no Gmail
e, quando a mesma fatura chegar por e-mail, as duas ficam ligadas (a tela sugere o mesmo local; a pessoa decide).
"""
import base64
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database

PDF = b"%PDF-1.4 fatura de teste"
XML = '<?xml version="1.0"?><CompNfse><Nfse><InfNfse><Numero>7001001</Numero></InfNfse></Nfse></CompNfse>'
LIDO = {"emissorNome": "NETFIBRA TELECOM FICTICIA LTDA", "valorTotal": 189.9, "dataVencimento": "2026-12-10",
        "numero": "4521", "cnpjEmissor": "12345678000100", "chave": "999999999"}


class EntradaManualTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        (temp / "faturas").mkdir()
        (temp / "recebidas").mkdir()
        self.recebidas = temp / "recebidas"
        self.chamadas = []
        self.n8n_ok = True

        def avisar(item_id):
            self.chamadas.append(item_id)
            return (True, "") if self.n8n_ok else (False, "o n8n não respondeu (teste)")

        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp / "faturas"),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", self.recebidas),
            patch.object(app_module, "API_KEY", ""),
            patch.object(app_module, "_avisar_n8n_entrada_manual", side_effect=avisar),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()
        self.local = self.client.post("/api/locais/agencia/item", json={"nome": "Agência Centro", "cidade": "Itabuna"}).json["item"]

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def enviar(self, pdf=PDF, xml=None, observacao="", nome_pdf="fatura.pdf", nome_xml="nota.xml"):
        form = {"observacao": observacao}
        if pdf is not None:
            form["pdf"] = (BytesIO(pdf), nome_pdf)
        if xml is not None:
            form["xml"] = (BytesIO(xml.encode("utf-8")), nome_xml)
        return self.client.post("/api/notas-recebidas/manual", data=form, content_type="multipart/form-data")

    def resultado_da_ia(self, item, dados, arquivo=PDF, nome="fatura.pdf"):
        """O que o WF-10 grava depois da leitura e da IA (a mesma rota e o mesmo formato do WF-08)."""
        form = {"gmailMessageId": item["gmail_message_id"], "gmailAttachmentId": item["gmail_attachment_id"],
                "assunto": item["assunto"], "remetente": item["remetente"], "recebidaEm": item["recebida_em"],
                "dadosExtracao": json.dumps(dados), "arquivo": (BytesIO(arquivo), nome)}
        return self.client.post("/api/notas-recebidas", data=form, content_type="multipart/form-data")

    def chegar_por_email(self, dados, mensagem="msg-email-1"):
        form = {"gmailMessageId": mensagem, "gmailAttachmentId": "a1", "remetente": "faturas@netfibra.com.br",
                "assunto": "Sua fatura", "dadosExtracao": json.dumps(dados), "arquivo": (BytesIO(PDF), "fatura-email.pdf")}
        return self.client.post("/api/notas-recebidas", data=form, content_type="multipart/form-data")

    def test_pdf_entra_na_caixa_sem_etiqueta_e_chama_a_ia(self):
        r = self.enviar(observacao="Fatura entregue no balcão")
        self.assertEqual(r.status_code, 201, r.json)
        item = r.json["item"]
        self.assertTrue(item["origemManual"])
        self.assertTrue(item["gmail_message_id"].startswith("manual-"))
        self.assertEqual(item["status"], "AGUARDANDO_ASSOCIACAO")
        self.assertEqual(item["etiqueta_status"], "SEM_EMAIL")
        self.assertTrue(item["dados"]["aguardandoIA"])
        self.assertEqual(item["dados"]["entradaManual"]["observacao"], "Fatura entregue no balcão")
        self.assertEqual(self.chamadas, [item["id"]])
        self.assertTrue(r.json["iaAvisada"])
        self.assertTrue(self.client.get(item["downloadUrl"]).data.startswith(b"%PDF"))

    def test_pdf_e_xml_juntos_e_so_xml_em_revisao(self):
        junto = self.enviar(xml=XML).json["item"]
        self.assertIn("xmlUrl", junto)
        self.assertIn(b"7001001", self.client.get(junto["xmlUrl"]).data)
        so_xml = self.enviar(pdf=None, xml=XML).json["item"]
        self.assertEqual(so_xml["status"], "REVISAO")
        self.assertTrue(so_xml["dados"]["semPdf"])
        self.assertIn("faturaPdf", so_xml["dados"]["camposParaRevisar"])

    def test_arquivos_invalidos_sao_recusados_sem_gravar(self):
        self.assertEqual(self.client.post("/api/notas-recebidas/manual", data={}, content_type="multipart/form-data").status_code, 400)
        self.assertEqual(self.enviar(pdf=b"nao e pdf").status_code, 400)
        self.assertEqual(self.enviar(nome_pdf="fatura.exe").status_code, 400)
        self.assertEqual(self.enviar(pdf=None, xml="isto não é xml").status_code, 400)
        self.assertEqual(self.enviar(pdf=None, xml='<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x/>').status_code, 400)
        self.assertEqual(list(self.recebidas.iterdir()), [])
        self.assertEqual(self.chamadas, [])

    def test_n8n_fora_do_ar_nao_perde_o_documento(self):
        self.n8n_ok = False
        r = self.enviar()
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.json["iaAvisada"])
        self.assertIn("Extrair dados do PDF", r.json["aviso"])
        dados = r.json["item"]["dados"]
        self.assertFalse(dados["aguardandoIA"])
        self.assertIn("não respondeu", dados["iaNaoChamada"])

    def test_n8n_le_o_documento_no_formato_do_email(self):
        item = self.enviar(xml=XML, observacao="só chega impresso").json["item"]
        r = self.client.get(f"/api/notas-recebidas/{item['id']}/entrada-manual")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(base64.b64decode(r.json["arquivoBase64"]), PDF)
        self.assertEqual((r.json["soXml"], r.json["mimeType"], r.json["corpo"]), (False, "application/pdf", "só chega impresso"))
        self.assertIn("7001001", r.json["xmlTexto"])
        so_xml = self.enviar(pdf=None, xml=XML).json["item"]
        r = self.client.get(f"/api/notas-recebidas/{so_xml['id']}/entrada-manual").json
        self.assertEqual((r["soXml"], r["mimeType"]), (True, "application/xml"))
        # Documento do Gmail não sai por esta rota.
        email = self.chegar_por_email(LIDO).json["item"]
        self.assertEqual(self.client.get(f"/api/notas-recebidas/{email['id']}/entrada-manual").status_code, 404)

    def test_resultado_da_ia_preserva_quem_enviou_e_nao_cria_outra_nota(self):
        item = self.enviar(observacao="balcão").json["item"]
        r = self.resultado_da_ia(item, {**LIDO, "decisaoIA": "importar"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertTrue(r.json["duplicada"])
        novo = r.json["item"]
        self.assertEqual(novo["id"], item["id"])
        self.assertEqual(novo["dados"]["emissorNome"], LIDO["emissorNome"])
        self.assertEqual(novo["dados"]["entradaManual"]["observacao"], "balcão")
        self.assertNotIn("aguardandoIA", novo["dados"])
        self.assertIn("iaProcessadaEm", novo["dados"])
        self.assertEqual(novo["etiqueta_status"], "SEM_EMAIL")
        self.assertEqual(len([f for f in self.recebidas.iterdir() if f.suffix == ".pdf"]), 1)  # a cópia do n8n não fica

    def test_ia_diz_que_nao_e_cobranca_vai_para_revisao_e_nao_some(self):
        item = self.enviar().json["item"]
        dados = {**LIDO, "decisaoIA": "ignorar", "triagem": {"decisao": "ignorar", "autoDescarte": True}}
        novo = self.resultado_da_ia(item, dados).json["item"]
        self.assertEqual(novo["status"], "REVISAO")
        self.assertEqual(novo["dados"]["decisaoIA"], "ignorar")  # o veredito fica gravado para o painel da IA
        self.assertIn(item["id"], [i["id"] for i in self.client.get("/api/notas-recebidas").json["items"]])

    def test_codigo_de_mensagem_manual_que_nao_existe_e_recusado(self):
        form = {"gmailMessageId": "manual-inventado", "gmailAttachmentId": "manual", "dadosExtracao": json.dumps(LIDO),
                "arquivo": (BytesIO(PDF), "x.pdf")}
        r = self.client.post("/api/notas-recebidas", data=form, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 404)

    def test_manual_associada_nao_entra_na_fila_de_etiquetas_do_gmail(self):
        item = self.enviar().json["item"]
        self.resultado_da_ia(item, {**LIDO, "decisaoIA": "importar"})
        r = self.client.patch(f"/api/notas-recebidas/{item['id']}/associar",
                              json={"entidadeTipo": "agencia", "entidadeId": self.local["id"], "dados": LIDO})
        self.assertEqual(r.status_code, 200, r.json)
        pendentes = self.client.get("/api/notas-recebidas?etiquetaPendente=1").json["items"]
        self.assertNotIn(item["id"], [i["id"] for i in pendentes])

    def test_mesma_fatura_chega_por_email_e_vem_com_o_local_da_manual(self):
        manual = self.enviar().json["item"]
        self.resultado_da_ia(manual, {**LIDO, "decisaoIA": "importar"})
        self.client.patch(f"/api/notas-recebidas/{manual['id']}/associar",
                          json={"entidadeTipo": "agencia", "entidadeId": self.local["id"], "dados": LIDO})
        email = self.chegar_por_email({**LIDO, "numero": "999999999"}).json["item"]  # número não lido: casa por emissor+valor+vencimento
        corr = email["correspondenteManual"]
        self.assertEqual((corr["id"], corr["status"], corr["entidadeId"]), (manual["id"], "ASSOCIADA", self.local["id"]))
        self.assertEqual(corr["motivo"], "mesmo emissor, valor e vencimento")
        self.assertFalse(email["origemManual"])
        self.assertEqual(email["etiqueta_status"], "PENDENTE")  # o e-mail recebe a etiqueta ao ser associado
        manual_agora = self.client.get("/api/notas-recebidas?status=ASSOCIADA").json["items"][0]
        self.assertEqual(manual_agora["dados"]["chegouPorEmail"]["id"], email["id"])

    def test_casamento_por_chave_e_por_numero_e_cnpj_e_nao_casa_outra_fatura(self):
        chave = "29261098765432000110620010000162101069255993"
        m1 = self.enviar().json["item"]
        self.resultado_da_ia(m1, {**LIDO, "chave": chave, "valorTotal": 1.0, "decisaoIA": "importar"})
        e1 = self.chegar_por_email({**LIDO, "chave": chave}, "msg-a").json["item"]
        self.assertEqual(e1["correspondenteManual"]["motivo"], "mesma chave da nota")
        m2 = self.enviar().json["item"]
        self.resultado_da_ia(m2, {**LIDO, "numero": "8800", "valorTotal": 2.0, "decisaoIA": "importar"})
        e2 = self.chegar_por_email({**LIDO, "numero": "8800", "valorTotal": 3.0}, "msg-b").json["item"]
        self.assertEqual(e2["correspondenteManual"]["id"], m2["id"])
        self.assertEqual(e2["correspondenteManual"]["motivo"], "mesmo emissor e mesmo número")
        outra = self.chegar_por_email({**LIDO, "numero": "9999", "valorTotal": 55.0, "dataVencimento": "2027-01-10"}, "msg-c").json["item"]
        self.assertNotIn("correspondenteManual", outra)


if __name__ == "__main__":
    unittest.main()
