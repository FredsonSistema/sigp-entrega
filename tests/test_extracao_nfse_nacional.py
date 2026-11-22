"""NFS-e Nacional: rótulo e valor em colunas, em linhas diferentes (mesmo caso do extrator do WF-08, texto fictício)."""
import unittest

from backend.app import _extract_invoice_fields

TEXTO = "Alíq. Efetiva Municipal - IBS                Valor Apurado Municipal - IBS                 Alíq. Efetiva Estadual - IBS\n0,00 %                                       R$ 0,00                                       0,10 %\nValor Total Apurado - IBS                    Alíquota - CBS                                Alíquota Efetiva - CBS\nR$ 0,03                                      0,90 %                                        0,90 %\nVALOR TOTAL DA NFS-E                         VALOR DA OPERAÇÃO / SERVIÇO                   Desconto Incondicionado\nR$ 15,00                                      -                                                    -\nTotal das Retenções (ISSQN / Federais)       VALOR LÍQUIDO DA NFS-e                        Total do IBS/CBS\n-                                            R$ 15,00                                      R$ 0,13\n"
SO_LIQUIDO = "Total das Retenções (ISSQN / Federais)       VALOR LÍQUIDO DA NFS-e                        Total do IBS/CBS\n-                                            R$ 1.234,50                                   R$ 0,13\n"
SO_IMPOSTO = "Valor Total Apurado - IBS                    Alíquota - CBS\nR$ 0,03                                      0,90 %\n"


class ExtracaoNfseNacionalTests(unittest.TestCase):
    def test_valor_total_em_coluna_sem_pegar_o_imposto(self):
        self.assertEqual(_extract_invoice_fields(TEXTO)["valorTotal"], 15.0)
        self.assertEqual(_extract_invoice_fields(SO_LIQUIDO)["valorTotal"], 1234.5)
        self.assertIsNone(_extract_invoice_fields(SO_IMPOSTO)["valorTotal"])

    def test_rotulo_na_mesma_linha_continua_valendo(self):
        self.assertEqual(_extract_invoice_fields("Valor total: R$ 119,90")["valorTotal"], 119.9)


if __name__ == "__main__":
    unittest.main()
