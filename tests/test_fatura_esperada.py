"""Situação 2 — fatura do mês que não chegou (exemplo do usuário: chega 17/11, vence 20/11)."""
import unittest
from datetime import date

from backend import fatura_esperada
from backend.alerts import build_alerts
from backend.provedores import mesma_empresa

LOCAL = {"id": "loc-1", "tipo": "agencia", "nome": "Itabuna Centro", "ativo": True,
         "provedores": [{"id": "p1", "nome": "HE-NET", "diaVencimento": "20", "valor": "150,00"}]}
LANCADA = {"id": "nl-1", "entidade_id": "loc-1", "entidade_tipo": "agencia", "provedor_nome": "HE-NET TELECOM LTDA",
           "data_vencimento": "2026-11-20", "valor_total": 150.0}
ASSOCIADA = {"id": "nr-1", "status": "ASSOCIADA", "entidade_id": "loc-1", "recebida_em": "2026-11-17T09:00:00Z",
             "gmail_message_id": "m1", "created_at": "2026-12-17T09:00:00", "dados": {"emissorNome": "HE-NET", "dataVencimento": "2026-11-20"}}


def gerar(hoje, recebidas=(ASSOCIADA,), local=LOCAL, ultima=None):
    return fatura_esperada.alertas([local], [LANCADA], list(recebidas), hoje, mesma_empresa, lambda l: f"Agência {l['nome']}", ultima)


class FaturaEsperadaTests(unittest.TestCase):
    def test_exemplo_do_usuario(self):
        self.assertEqual(gerar(date(2026, 12, 17)), [])  # 17/12: ainda é o dia esperado
        a = gerar(date(2026, 12, 18))
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["status"], a[0]["severidade"], a[0]["esperadaEm"], a[0]["vencimento"], a[0]["antecedenciaDias"]),
                         ("FATURA_NAO_RECEBIDA", "media", "2026-12-17", "2026-12-20", 3))
        self.assertIn("dez/2026 não chegou", a[0]["mensagem"])
        self.assertEqual(gerar(date(2026, 12, 20))[0]["severidade"], "alta")

    def test_varios_meses_sem_fatura(self):
        a = gerar(date(2027, 2, 18))
        self.assertEqual(a[0]["ciclosSemFatura"], 3)
        self.assertIn("3 meses sem fatura", a[0]["mensagem"])

    def test_fatura_chegou_mas_esta_na_caixa(self):
        caixa = {"id": "nr-2", "status": "AGUARDANDO_ASSOCIACAO", "recebida_em": "2026-12-16T10:00:00Z", "gmail_message_id": "m2",
                 "dados": {"emissorNome": "HE-NET TELECOM", "dataVencimento": "2026-12-20"}}
        a = gerar(date(2026, 12, 18), recebidas=(ASSOCIADA, caixa))
        self.assertEqual((a[0]["status"], a[0]["notaRecebidaId"]), ("FATURA_NA_CAIXA", "nr-2"))

    def test_pago_ou_sem_fatura_nao_alerta(self):
        pago = {**LOCAL, "provedores": [{**LOCAL["provedores"][0], "pagoAte": "2026-12-20"}]}
        self.assertEqual(gerar(date(2026, 12, 18), local=pago), [])
        sem = {**LOCAL, "provedores": [{**LOCAL["provedores"][0], "periodicidade": "sem_fatura"}]}
        self.assertEqual(gerar(date(2026, 12, 18), local=sem), [])

    def test_sem_historico_nao_acompanha_ainda(self):
        novo = {**LOCAL, "provedores": [{"id": "p2", "nome": "Vox", "diaVencimento": "10"}]}
        self.assertEqual(fatura_esperada.alertas([novo], [], [], date(2026, 12, 18), mesma_empresa, lambda l: "x"), [])

    def test_leitura_do_gmail_parada(self):
        a = gerar(date(2026, 12, 18), ultima="2026-12-10T08:00:00")
        status = {x["status"]: x for x in a}
        self.assertEqual(status["LEITURA_GMAIL_PARADA"]["severidade"], "alta")
        self.assertEqual(status["FATURA_NAO_RECEBIDA"]["severidade"], "baixa")

    def test_antecedencia_padrao_sem_historico_de_email(self):
        a = gerar(date(2026, 12, 16), recebidas=())
        self.assertEqual((a[0]["antecedenciaDias"], a[0]["esperadaEm"]), (5, "2026-12-15"))

    def test_entra_no_build_alerts(self):
        itens = build_alerts([LOCAL], [LANCADA], [], [], date(2026, 12, 18), 7, received_notes=[ASSOCIADA])
        self.assertIn("FATURA_NAO_RECEBIDA", {i["status"] for i in itens})


if __name__ == "__main__":
    unittest.main()
