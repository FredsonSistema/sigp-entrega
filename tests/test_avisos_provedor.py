"""Situação 1 — vários e-mails da mesma fatura: tipo de e-mail, vínculo com a cobrança e pagamento automático."""
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import avisos_provedor, database

REMETENTE = '"Fibra Exemplo" <financeiro@fibraexemplo.net>'


class DetectarEventoTests(unittest.TestCase):
    def casos(self):
        return [
            ("Sua fatura de novembro chegou", "", "fatura_nova"),
            ("Pagamento confirmado", "Recebemos seu pagamento, obrigado!", "pagamento_confirmado"),
            ("Fatura em atraso", "Evite o bloqueio do serviço", "aviso_atraso"),
            ("Lembrete: sua fatura vence amanhã", "", "lembrete_vencimento"),
            ("2ª via da fatura", "", "segunda_via"),
            ("Aviso", "Identificamos débitos em aberto", "aviso_atraso"),
        ]

    def test_frases_claras(self):
        for assunto, corpo, esperado in self.casos():
            self.assertEqual(avisos_provedor.detectar_evento(assunto, corpo)["tipo"], esperado, assunto)

    def test_boleto_com_multa_apos_vencimento_nao_e_atraso(self):
        texto = "BOLETO. Após o vencimento cobrar multa de 2%. Fatura vencida paga em qualquer banco."
        self.assertEqual(avisos_provedor.detectar_evento("Sua fatura chegou", "", texto)["tipo"], "fatura_nova")

    def test_data_de_pagamento_no_texto(self):
        self.assertEqual(avisos_provedor.data_pagamento_no_texto("Pagamento realizado em 16/11/2026."), "2026-11-16")


class AvisosRotasTests(unittest.TestCase):
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
        self.local = self.client.post("/api/locais/agencia/item", json={"nome": "Agência Itabuna Centro", "cidade": "Itabuna"}).json["item"]
        self.cadastrar_provedor(self.local["id"], "Fibra Exemplo", "fibraexemplo.net")

    def cadastrar_provedor(self, local_id, nome, email):
        conn = database.get_connection()
        try:
            conn.execute("UPDATE locais SET provedores_json = ? WHERE id = ?",
                         (json.dumps([{"id": "p1", "nome": nome, "email": email, "diaVencimento": "15"}]), local_id))
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def lancar(self, nota_id="nl-1", venc="2026-11-15", valor=129.9, numero="555", local=None, provedor="FIBRA EXEMPLO TELECOM LTDA"):
        local = local or self.local
        r = self.client.post("/api/notas/lancadas", json={"id": nota_id, "entidadeTipo": "agencia", "entidadeId": local["id"], "dados": {
            "id": nota_id, "numero": numero, "provedorNome": provedor, "localNome": local["nome"],
            "localCidade": "Itabuna", "valorTotal": valor, "dataEmissao": "2026-11-01", "dataVencimento": venc,
            "servicos": [{"descricao": "Internet", "valorTotal": valor}]}})
        self.assertIn(r.status_code, (200, 201), r.json)
        return r.json["item"]

    def aviso(self, msg, assunto, corpo, data="2026-11-17T10:00:00Z"):
        return self.client.post("/api/notas-recebidas/aviso", json={
            "gmailMessageId": msg, "assunto": assunto, "corpo": corpo, "remetente": REMETENTE, "recebidaEm": data})

    def test_pagamento_confirmado_sem_anexo_marca_como_pago(self):
        nota = self.lancar()
        r = self.aviso("m-pago", "Pagamento confirmado", "Olá! Recebemos seu pagamento. Pagamento realizado em 16/11/2026.")
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(r.json["acao"], "pagamento_registrado")
        item = r.json["item"]
        self.assertEqual((item["status"], item["entidade_id"]), ("AVISO", self.local["id"]))
        pagas = [p for p in database.list_nota_pagas() if p["id"] == f"paga-aviso-{item['id']}"]
        self.assertEqual(len(pagas), 1)
        self.assertEqual((pagas[0]["valor_pago"], pagas[0]["data_pagamento"], pagas[0]["status"], pagas[0]["origem"]),
                         (129.9, "2026-11-16", "PAGO_COM_ATRASO", "aviso_provedor"))
        self.assertEqual(app_module._saldo_nota(database.get_nota_lancada(nota["id"])), 0)
        prov = database.get_local(self.local["id"])["provedores"][0]
        self.assertEqual(prov["pagoAte"], "2026-11-15")
        # O mesmo e-mail de novo (reprocessamento) não paga duas vezes.
        self.aviso("m-pago", "Pagamento confirmado", "Recebemos seu pagamento.")
        self.assertEqual(len([p for p in database.list_nota_pagas() if p["origem"] == "aviso_provedor"]), 1)

    def test_aviso_de_atraso_vincula_sem_pagar(self):
        self.lancar()
        r = self.aviso("m-atraso", "Fatura em atraso", "Sua fatura venceu em 15/11/2026. Evite o bloqueio.")
        self.assertEqual(r.json["acao"], "vinculado")
        self.assertEqual(r.json["item"]["status"], "AVISO")
        self.assertFalse([p for p in database.list_nota_pagas() if p["origem"] == "aviso_provedor"])

    def test_sem_cobranca_lancada_fica_inconclusivo_na_caixa(self):
        r = self.aviso("m-sem", "Pagamento confirmado", "Recebemos seu pagamento.")
        item = r.json["item"]
        self.assertEqual(r.json["acao"], "sem_vinculo")
        self.assertIn(item["status"], ("AGUARDANDO_ASSOCIACAO", "REVISAO"))
        self.assertEqual(item["dados"]["triagem"]["probabilidade"], "inconclusivo")

    def test_duas_em_aberto_sem_identificacao_pede_escolha(self):
        self.lancar("nl-1", venc="2026-11-15", valor=129.9, numero="555")
        self.lancar("nl-2", venc="2026-11-05", valor=129.9, numero="556")
        r = self.aviso("m-duas", "Pagamento confirmado", "Recebemos seu pagamento.")
        self.assertEqual(r.json["acao"], "varias_candidatas")
        self.assertEqual(len(r.json["item"]["dados"]["aviso"]["candidatas"]), 2)

    def test_aviso_sem_anexo_nao_associa_e_revincula_depois(self):
        r = self.aviso("m-cedo", "Pagamento confirmado", "Recebemos seu pagamento.")
        item = r.json["item"]
        self.assertEqual(r.json["acao"], "sem_vinculo")
        assoc = self.client.patch(f"/api/notas-recebidas/{item['id']}/associar",
                                  json={"entidadeTipo": "agencia", "entidadeId": self.local["id"], "dados": {}})
        self.assertEqual(assoc.status_code, 409)
        self.lancar()
        de_novo = self.client.post(f"/api/notas-recebidas/{item['id']}/vincular-aviso").json
        self.assertEqual(de_novo["acao"], "pagamento_registrado")

    def test_fatura_nova_sem_anexo_nao_entra(self):
        r = self.aviso("m-nova", "Sua fatura chegou", "Acesse o link para ver sua fatura.")
        self.assertEqual(r.json["acao"], "nenhum")
        self.assertFalse(database.list_notas_recebidas())

    def test_lembrete_com_pdf_vincula_pela_cobranca_do_mesmo_vencimento(self):
        nota = self.lancar()
        dados = {"emissorNome": "Fibra Exemplo", "valorTotal": 129.9, "dataVencimento": "2026-11-15",
                 "evento": {"tipo": "lembrete_vencimento", "origem": "regra"}}
        r = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "m-lemb", "remetente": REMETENTE, "dadosExtracao": json.dumps(dados),
            "arquivo": (BytesIO(b"%PDF-1.4 x"), "lembrete.pdf")}, content_type="multipart/form-data")
        item = r.json["item"]
        self.assertEqual(item["status"], "AVISO")
        self.assertEqual(item["dados"]["aviso"]["notaLancadaId"], nota["id"])

    def test_remetente_generico_acha_pelo_email_cadastrado_e_nao_pelo_nome(self):
        # Nome do remetente só "Fibra" (genérico): outra cobrança "CONNECT FIBRA" não pode entrar.
        outro = self.client.post("/api/locais/agencia/item", json={"nome": "Agência Outra", "cidade": "Ilhéus"}).json["item"]
        self.lancar("nl-outro", local=outro, provedor="CONNECT FIBRA TELECOM LTDA", numero="900")
        nota = self.lancar()
        r = self.client.post("/api/notas-recebidas/aviso", json={"gmailMessageId": "m-gen", "assunto": "Pagamento confirmado",
                             "corpo": "Recebemos seu pagamento.", "remetente": "Fibra <cobranca@fibraexemplo.net>", "recebidaEm": "2026-11-17T10:00:00Z"})
        self.assertEqual(r.json["acao"], "pagamento_registrado", r.json["item"]["dados"].get("aviso"))
        self.assertEqual(r.json["item"]["dados"]["aviso"]["notaLancadaId"], nota["id"])

    def test_nome_generico_sem_email_cadastrado_nao_vincula(self):
        self.lancar(provedor="CONNECT FIBRA TELECOM LTDA")
        r = self.client.post("/api/notas-recebidas/aviso", json={"gmailMessageId": "m-gen2", "assunto": "Pagamento confirmado",
                             "corpo": "Recebemos seu pagamento.", "remetente": "Fibra <x@desconhecido.example>", "recebidaEm": "2026-11-17T10:00:00Z"})
        self.assertEqual(r.json["acao"], "sem_vinculo")

    def test_classificar_devolve_o_evento(self):
        r = self.client.post("/api/notas-recebidas/classificar", json={"texto": "x", "assunto": "Pagamento confirmado", "remetente": REMETENTE})
        self.assertEqual(r.json["classificacao"]["evento"]["tipo"], "pagamento_confirmado")


if __name__ == "__main__":
    unittest.main()
