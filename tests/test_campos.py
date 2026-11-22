import unittest

from backend.campos import (
    VALOR_PADRAO, aplicar_data_emissao, aplicar_padrao_identificacao, eh_padrao, mesclar_identificacao,
    motivo_chave_invalida, motivo_numero_invalido,
)
from backend.reconciliation import invoice_identity_matches


class IdentificacaoPadraoTests(unittest.TestCase):
    def test_numero_vazio_ou_invalido_vira_padrao(self):
        for lido in ("", "   ", "0000", "Documento", "11.222.333/0001-81", "12/12/2026", "R$ 289,90"):
            campos = aplicar_padrao_identificacao({"numero": lido, "chave": ""})
            self.assertEqual(campos["numero"], VALOR_PADRAO, lido)
            self.assertTrue(campos["numeroPadrao"], lido)

    def test_numero_valido_e_preservado(self):
        for lido in ("4455667", "NF-123/2026", "FAT.0001"):
            campos = aplicar_padrao_identificacao({"numero": lido, "chave": ""})
            self.assertEqual(campos["numero"], lido)
            self.assertFalse(campos["numeroPadrao"])

    def test_chave_lida_tem_prioridade_e_o_padrao_so_vale_sem_chave(self):
        # Decisão do usuário (14/11/2026): chave fora de 44/50 fica como veio, com o motivo anotado.
        self.assertEqual(motivo_chave_invalida("1" * 44), "")
        self.assertEqual(motivo_chave_invalida("1" * 50), "")
        self.assertNotEqual(motivo_chave_invalida("12345"), "")
        campos = aplicar_padrao_identificacao({"numero": "10", "chave": "ABC123"})
        self.assertEqual(campos["chave"], "ABC123")
        self.assertFalse(campos["chavePadrao"])
        self.assertTrue(campos["chaveMotivo"])
        self.assertNotIn("chave", campos["camposParaRevisar"])
        self.assertEqual(aplicar_padrao_identificacao({"numero": "10", "chave": ""})["chave"], VALOR_PADRAO)
    def test_chave_vazia_nao_entra_em_revisao_mas_numero_vazio_entra(self):
        campos = aplicar_padrao_identificacao({"numero": "", "chave": ""})
        self.assertIn("numero", campos["camposParaRevisar"])
        self.assertNotIn("chave", campos["camposParaRevisar"])

    def test_dado_real_vence_o_padrao_e_nao_o_contrario(self):
        novo = aplicar_padrao_identificacao({"numero": "", "chave": ""})
        mesclar_identificacao(novo, {"numero": "778899", "chave": "1" * 44})
        self.assertEqual(novo["numero"], "778899")
        self.assertEqual(novo["chave"], "1" * 44)
        novo = aplicar_padrao_identificacao({"numero": "4455667", "chave": ""})
        mesclar_identificacao(novo, {"numero": VALOR_PADRAO})
        self.assertEqual(novo["numero"], "4455667")

    def test_padrao_nao_gera_identidade_na_conciliacao(self):
        lancada = {"chave": VALOR_PADRAO, "numero": VALOR_PADRAO, "provedor_nome": "Algar"}
        paga = {"chave": VALOR_PADRAO, "numero": VALOR_PADRAO, "provedor_nome": "Algar"}
        self.assertIsNone(invoice_identity_matches(lancada, paga))
        self.assertTrue(eh_padrao(VALOR_PADRAO))
        self.assertEqual(motivo_numero_invalido(VALOR_PADRAO), "")


class DataEmissaoTests(unittest.TestCase):
    def test_sem_emissao_usa_recebimento_e_registra_a_origem(self):
        campos = aplicar_data_emissao({"dataEmissao": ""}, "Wed, 11 Nov 2026 10:30:00 -0300")
        self.assertEqual(campos["dataEmissao"], "2026-11-11")
        self.assertEqual(campos["dataEmissaoOrigem"], "recebimento")
        self.assertIn("dataEmissao", campos["camposParaRevisar"])

    def test_emissao_do_documento_e_mantida(self):
        campos = aplicar_data_emissao({"dataEmissao": "01/12/2026"}, "2026-11-11")
        self.assertEqual(campos["dataEmissao"], "2026-12-01")
        self.assertEqual(campos["dataEmissaoOrigem"], "documento")


if __name__ == "__main__":
    unittest.main()
