import unittest

from backend.provedores import aplicar_fatura_no_provedor, encontrar_provedor, normalizar_nome_provedor


class ProvedorDoLocalTests(unittest.TestCase):
    def aplicar(self, provedores, nome="VOX TELECOM LTDA", venc="2026-12-10"):
        return aplicar_fatura_no_provedor(provedores, nome=nome, valor=129.9, data_vencimento=venc, fatura_id="fat-1")

    def test_atualiza_provedor_existente_por_nome_parcial(self):
        r = self.aplicar([{"id": "p1", "nome": "vox"}])
        self.assertEqual(r["acao"], "atualizado")
        p = r["provedores"][0]
        self.assertEqual((p["id"], p["nome"], p["valor"], p["dataVencimento"], p["diaVencimento"], p["faturaAtualId"]),
                         ("p1", "vox", "129.90", "2026-12-10", "10", "fat-1"))

    def test_cria_provedor_quando_nao_existe(self):
        r = self.aplicar([{"id": "p1", "nome": "Algar"}])
        self.assertEqual(r["acao"], "criado")
        self.assertEqual(len(r["provedores"]), 2)
        self.assertEqual(r["provedor"]["nome"], "VOX TELECOM LTDA")

    def test_ambiguo_nao_altera(self):
        r = self.aplicar([{"id": "a", "nome": "Vox"}, {"id": "b", "nome": "Vox Telecom Fibra"}], nome="VOX TELECOM")
        self.assertEqual(r["acao"], "ambiguo")
        self.assertNotIn("valor", r["provedores"][0])

    def test_fatura_mais_antiga_nao_regride_o_vencimento(self):
        r = self.aplicar([{"id": "p1", "nome": "Vox", "dataVencimento": "2026-12-10", "valor": "100.00"}], venc="2026-11-10")
        self.assertEqual(r["acao"], "historico")
        self.assertEqual(r["provedores"][0]["dataVencimento"], "2026-12-10")

    def test_mesma_empresa_com_razao_social_diferente_nao_duplica(self):
        r = self.aplicar([{"id": "p1", "nome": "OPIX INTERNET"}], nome="OPIX SERVICOS DE TECNOLOGIA EIRELI")
        self.assertEqual((r["acao"], len(r["provedores"])), ("atualizado", 1))
        # palavras genéricas não contam como marca: "Fibra Rápida" x "Fibra Veloz" são empresas diferentes
        r = self.aplicar([{"id": "p1", "nome": "FIBRA RAPIDA"}], nome="FIBRA VELOZ LTDA")
        self.assertEqual(r["acao"], "criado")

    def test_normalizacao_ignora_sufixos_e_acentos(self):
        self.assertEqual(normalizar_nome_provedor("Telecomunicações Ação S/A"), normalizar_nome_provedor("TELECOMUNICACOES ACAO"))
        self.assertEqual(encontrar_provedor([{"nome": "Brisanet"}], "BRISANET SERVICOS LTDA")[1], "parcial")


class RegraPorIdEFaturaTests(unittest.TestCase):
    def test_id_da_linha_tem_prioridade_sobre_o_nome(self):
        r = aplicar_fatura_no_provedor(
            [{"id": "a", "nome": "Vox"}, {"id": "b", "nome": "Link Principal"}],
            nome="VOX TELECOM", valor=10, data_vencimento="2026-12-01", fatura_id="f", provedor_id="b",
        )
        self.assertEqual(r["provedores"][1]["valor"], "10.00")
        self.assertNotIn("valor", r["provedores"][0])

    def test_nota_sem_fatura_mantem_a_fatura_atual(self):
        r = aplicar_fatura_no_provedor(
            [{"id": "a", "nome": "Vox", "faturaAtualId": "fat-antiga"}],
            nome="Vox", valor=10, data_vencimento="2026-12-01",
        )
        self.assertEqual(r["provedores"][0]["faturaAtualId"], "fat-antiga")


class GravacaoDaTelaNaoApagaFaturaTests(unittest.TestCase):
    def test_retrato_antigo_nao_apaga_nem_regride(self):
        from backend.database import preservar_fatura_atual
        existente = [{"id": "p1", "nome": "Vox", "valor": "149.90", "dataVencimento": "2026-11-15", "diaVencimento": "15", "faturaAtualId": "f1"}]
        sem_dados = preservar_fatura_atual([{"id": "p1", "nome": "Vox", "contato": "x"}], existente)[0]
        self.assertEqual((sem_dados["valor"], sem_dados["dataVencimento"], sem_dados["contato"]), ("149.90", "2026-11-15", "x"))
        antigo = preservar_fatura_atual([{"id": "p1", "nome": "Vox", "valor": "99.00", "dataVencimento": "2026-10-15"}], existente)[0]
        self.assertEqual(antigo["dataVencimento"], "2026-11-15")
        edicao = preservar_fatura_atual([{"id": "p1", "nome": "Vox", "valor": "150.00", "dataVencimento": "2026-11-15"}], existente)[0]
        self.assertEqual(edicao["valor"], "150.00")  # edição manual com a mesma data vale


class AlertaDePagamentoTests(unittest.TestCase):
    def test_pagas_na_janela_viram_alerta_e_atraso_e_destacado(self):
        from datetime import date
        from backend.alerts import build_alerts
        nota = {"id": "n1", "numero": "302500", "chave": "", "provedor_nome": "OPIX", "valor_total": 119.9,
                "data_vencimento": "2026-11-10", "data_emissao": "2026-11-01", "entidade_tipo": "garagem", "entidade_id": "g1"}
        pago = lambda dia: {"id": f"p-{dia}", "numero": "302500", "chave": "", "provedor_nome": "OPIX", "valor_pago": 119.9,  # noqa: E731
                            "data_pagamento": dia, "data_emissao": "2026-11-01", "status": "PAGA",
                            "entidade_tipo": "garagem", "entidade_id": "g1"}
        hoje = date(2026, 11, 12)
        no_prazo = [a for a in build_alerts([], [nota], [pago("2026-11-09")], [], hoje, 7) if a["tipo"] == "pagamento"]
        self.assertEqual([(a["status"], a["severidade"]) for a in no_prazo], [("PAGO", "info")])
        self.assertIn("no prazo", no_prazo[0]["mensagem"])
        atrasado = [a for a in build_alerts([], [nota], [pago("2026-11-12")], [], hoje, 7) if a["tipo"] == "pagamento"]
        self.assertEqual((atrasado[0]["status"], atrasado[0]["atrasoDias"]), ("PAGO_COM_ATRASO", 2))
        antigo = [a for a in build_alerts([], [nota], [pago("2026-10-01")], [], hoje, 7) if a["tipo"] == "pagamento"]
        self.assertEqual(antigo, [])

    def test_mesma_cobranca_nao_gera_alerta_duplicado_e_nome_sem_tipo_repetido(self):
        from datetime import date
        from backend.alerts import build_alerts
        local = {"id": "a1", "tipo": "agencia", "nome": "Agência Itacaré",
                 "provedores": [{"nome": "ITS TELECOMUNICAÇÕES LTDA", "dataVencimento": "2026-11-10", "diaVencimento": "10", "valor": "174.00"}]}
        nota = {"id": "n1", "numero": "2847941", "provedor_nome": "ITS TELECOMUNICAÇÕES LTDA", "valor_total": 174.0,
                "data_vencimento": "2026-11-10", "entidade_tipo": "agencia", "entidade_id": "a1"}
        venc = [a for a in build_alerts([local], [nota], [], [], date(2026, 11, 12), 7) if a["tipo"] == "vencimento"]
        self.assertEqual([(a["origem"], a["status"]) for a in venc], [("nota", "VENCIDO")])
        self.assertEqual(venc[0]["local"], "Agência Itacaré")
        # sem nota com saldo, o alerta do provedor continua
        so_provedor = [a for a in build_alerts([local], [], [], [], date(2026, 11, 12), 7) if a["tipo"] == "vencimento"]
        self.assertEqual([a["origem"] for a in so_provedor], ["provedor"])


class RecorrenciaTests(unittest.TestCase):
    def test_mesma_empresa_e_competencia(self):
        from backend.provedores import competencia, mesma_empresa
        self.assertTrue(mesma_empresa("OPIX INTERNET", "OPIX SERVICOS DE TECNOLOGIA EIRELI"))
        self.assertFalse(mesma_empresa("OPIX INTERNET", "BRISANET"))
        self.assertEqual(competencia("2026-11-10"), "2026-11")
        self.assertEqual(competencia(""), "")


class SugestaoPorHistoricoTests(unittest.TestCase):
    def test_provedor_ja_associado_sugere_o_local(self):
        from unittest import mock
        from backend import app as app_module
        locais = [{"id": "g1", "tipo": "garagem", "nome": "Rota Aracaju", "cidade": "Aracaju",
                   "provedores": [{"nome": "Brisanet", "email": "faturas@brisanet.com.br"}]}]
        notas = [{"provedor_nome": "OPIX INTERNET", "entidade_id": "g1"}]
        with app_module.app.test_request_context(), \
                mock.patch.object(app_module, "list_locais", return_value=locais), \
                mock.patch.object(app_module, "list_nota_lancadas", return_value=notas):
            por_nome = app_module._sugestoes_por_historico("OPIX SERVICOS DE TECNOLOGIA EIRELI", "")
            self.assertEqual([s["id"] for s in por_nome], ["g1"])
            self.assertIn("Histórico", por_nome[0]["motivo"])
            por_email = app_module._sugestoes_por_historico("Empresa X", "Cobrança <faturas@brisanet.com.br>")
            self.assertIn("e-mail do remetente", por_email[0]["motivo"])
            self.assertEqual(app_module._sugestoes_por_historico("Outra Empresa", "a@b.com"), [])


class ExtratorUnificadoTests(unittest.TestCase):
    def setUp(self):
        from backend import app as app_module
        self.client = app_module.app.test_client()

    def test_texto_de_boleto_devolve_formato_do_wf03(self):
        texto = "\n".join([
            "Beneficiário: FIBRANET TELECOMUNICACOES LTDA", "CNPJ: 11.222.333/0001-81",
            "Número da fatura: 4455667", "Data de emissão: 01/12/2026",
            "Vencimento: 12/12/2026", "Valor total da fatura: R$ 289,90",
        ])
        r = self.client.post("/api/extracao/texto", json={"texto": texto, "provedorEsperado": "Fibranet", "valorEsperado": 289.9}).get_json()
        self.assertEqual((r["emissorNome"], r["numeroFatura"], r["dataVencimento"], r["valorTotal"]),
                         ("FIBRANET TELECOMUNICACOES LTDA", "4455667", "2026-12-12", 289.9))
        self.assertTrue(r["comparacao"]["valorConfere"])
        self.assertTrue(r["emissorEsperadoEncontrado"])

    def test_sem_numero_vale_o_padrao_e_sem_texto_avisa(self):
        r = self.client.post("/api/extracao/texto", json={"texto": "Vencimento: 10/11/2026\nTotal a pagar: R$ 99,90"}).get_json()
        self.assertEqual((r["numeroFatura"], r["numeroPadrao"]), ("999999999", True))
        vazio = self.client.post("/api/extracao/texto", json={"texto": ""}).get_json()
        self.assertFalse(vazio["textEncontrado"])
        self.assertTrue(vazio["aviso"])


class AlertaDoProvedorTests(unittest.TestCase):
    def setUp(self):
        from datetime import date
        from backend.alerts import provider_due_status
        self.hoje = date(2026, 11, 12)
        self.status = lambda **kw: provider_due_status(
            kw.get("dia"), kw.get("pago"), self.hoje, 7, kw.get("data"))

    def test_data_da_fatura_atual_tem_prioridade_sobre_o_dia(self):
        # Dia 16 sozinho daria "vencido em 16/10"; a fatura atual vence em 16/11.
        r = self.status(dia="16", data="2026-11-16")
        self.assertEqual((r["status"], r["vencimento"]), ("VENCE_EM_BREVE", "2026-11-16"))

    def test_fatura_atual_vencida_e_paga(self):
        self.assertEqual(self.status(dia="5", data="2026-11-05")["status"], "VENCIDO")
        self.assertIsNone(self.status(dia="5", data="2026-11-05", pago="2026-11-05"))

    def test_sem_data_continua_valendo_o_dia(self):
        self.assertEqual(self.status(dia="10")["status"], "VENCIDO")


if __name__ == "__main__":
    unittest.main()
