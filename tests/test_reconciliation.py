import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database
from backend.app import app
from backend.dashboard import build_sig_summary
from backend.reconciliation import compare_reconciliation


def make_note(note_id: str, *, paid: bool = False, amount: float = 100.0, status: str = "CONTRATADO"):
    service = {
        "descricao": "Internet",
        "valorTotal": 100.0,
        "classificacao": status,
    }
    note = {
        "id": note_id,
        "entidadeTipo": "agencia",
        "entidadeId": "local-1",
        "chave": "chave-123",
        "numero": "123",
        "serie": "1",
        "provedorNome": "Provedor",
        "localNome": "Agência Centro",
        "localCidade": "Salvador",
        "valorTotal": 100.0,
        "dataEmissao": "2026-10-01",
        "servicos": [service],
        "status": "PAGA" if paid else "PENDENTE",
    }
    if paid:
        note.update({
            "valorPago": amount,
            "dataPagamento": "2026-10-05",
        })
    return note


class ReconciliationRulesTests(unittest.TestCase):
    def setUp(self):
        self.launched = make_note("launched")
        self.paid = make_note("paid", paid=True)

    def test_match_requires_both_service_lists_reviewed(self):
        result = compare_reconciliation(self.launched, self.paid, 100.0)
        self.assertEqual(result["status"], "MATCH")
        self.assertTrue(result["comparacao"]["servicos"])

        self.paid["servicos"][0]["classificacao"] = "PENDENTE"
        pending = compare_reconciliation(self.launched, self.paid, 100.0)
        self.assertEqual(pending["status"], "PENDENTE")

        self.paid["servicos"][0]["classificacao"] = "CONTRATADO"
        self.launched["servicos"][0]["classificacao"] = "PENDENTE"
        pending_launched = compare_reconciliation(self.launched, self.paid, 100.0)
        self.assertEqual(pending_launched["status"], "PENDENTE")

    def test_divergent_paid_service_blocks_match(self):
        self.paid["servicos"][0]["classificacao"] = "DIVERGENTE"
        result = compare_reconciliation(self.launched, self.paid, 100.0)
        self.assertEqual(result["status"], "DIVERGENCIA")

    def test_partial_payment_is_not_match_or_amount_divergence(self):
        self.paid["valorTotal"] = 100.0
        self.paid["valorPago"] = 60.0
        result = compare_reconciliation(self.launched, self.paid, 60.0)
        self.assertEqual(result["status"], "PAGO_PARCIAL")
        self.assertFalse(result["comparacao"]["valor"])

    def test_pdf_amount_is_the_reference_for_note_and_payment_values(self):
        agrees = compare_reconciliation(self.launched, self.paid, 100.0, invoice_amount=100.0)
        self.assertEqual(agrees["status"], "MATCH")
        self.assertTrue(agrees["comparacao"]["valor"])

        diverges = compare_reconciliation(self.launched, self.paid, 100.0, invoice_amount=120.0)
        self.assertEqual(diverges["status"], "DIVERGENCIA")
        self.assertFalse(diverges["comparacao"]["valor"])

    def test_partial_payment_is_measured_against_pdf_amount(self):
        self.paid["valorPago"] = 60.0
        result = compare_reconciliation(self.launched, self.paid, 60.0, invoice_amount=100.0)
        self.assertEqual(result["status"], "PAGO_PARCIAL")

    def test_identity_and_local_divergence_block_match(self):
        self.paid["chave"] = "different-key"
        result = compare_reconciliation(self.launched, self.paid, 100.0)
        self.assertEqual(result["status"], "DIVERGENCIA")

        self.paid["chave"] = "chave-123"
        self.paid["entidadeId"] = "other-local"
        result = compare_reconciliation(self.launched, self.paid, 100.0)
        self.assertEqual(result["status"], "DIVERGENCIA")

        self.paid["entidadeId"] = "local-1"
        self.paid["valorTotal"] = 120.0
        result = compare_reconciliation(self.launched, self.paid, 100.0)
        self.assertEqual(result["status"], "DIVERGENCIA")


class SigDashboardTests(unittest.TestCase):
    def test_summary_excludes_ambiguous_invoice_keys_and_aggregates_paid_events(self):
        first = make_note("launch-1")
        first["dataEmissao"] = "2026-10-01"
        duplicate = make_note("launch-duplicate")
        duplicate["dataEmissao"] = "2026-10-01"
        other = make_note("launch-2")
        other["chave"] = "different-key"
        other["valorTotal"] = 50.0
        other["dataEmissao"] = "2026-10-02"
        paid = make_note("payment-1", paid=True, amount=50.0)
        paid["chave"] = "different-key"
        paid["valorPago"] = 50.0
        paid["dataPagamento"] = "2026-10-05"
        result = build_sig_summary(
            [first, duplicate, other],
            [paid],
            [{"nota_lancada_id": "launch-2", "status": "MATCH", "updated_at": "2026-10-05"}],
            "2026-10-01",
            "2026-10-31",
        )
        self.assertEqual(result["indicadores"]["notasLancadas"], 1)
        self.assertEqual(result["indicadores"]["valorLancado"], 50.0)
        self.assertEqual(result["indicadores"]["valorPago"], 50.0)
        self.assertEqual(result["indicadores"]["valorPendente"], 0.0)
        self.assertEqual(result["indicadores"]["conciliadas"], 1)
        self.assertEqual(result["qualidade"]["notasAmbiguasExcluidas"], 2)

    def test_summary_filters_status_and_provider(self):
        note = make_note("launch")
        note["dataEmissao"] = "2026-10-01"
        result = build_sig_summary(
            [note],
            [],
            [{"nota_lancada_id": "launch", "status": "DIVERGENCIA", "updated_at": "2026-10-05"}],
            "2026-10-01",
            "2026-10-31",
            provider_query="provedor",
            status_filter="DIVERGENCIA",
        )
        self.assertEqual(result["indicadores"]["notasLancadas"], 1)
        self.assertEqual(result["indicadores"]["divergencias"], 1)


class BackendPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.faturas_dir = Path(self.temp_dir.name) / "faturas"
        self.faturas_dir.mkdir()
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.faturas_patch = patch("backend.app.FATURAS_DIR", self.faturas_dir)
        self.faturas_patch.start()
        database.init_db()
        self.client = app.test_client()

    def tearDown(self):
        self.faturas_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def create_launch(self, note_id: str = "launch-1"):
        note = make_note(note_id)
        return database.save_nota_lancada(note)

    def create_payment(self, note_id: str, amount: float, date: str):
        note = make_note(note_id, paid=True, amount=amount)
        note["dataPagamento"] = date
        return database.save_nota_paga(note)

    def test_database_uses_rollback_journal_for_local_storage(self):
        conn = database.get_connection()
        try:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        finally:
            conn.close()

    def test_app_state_round_trips_json_and_rejects_unapproved_keys(self):
        value = [{"id": "note-1", "texto": "Persistir acentos: ação"}]
        response = self.client.put("/api/app-state/sigp_notes_v1", json={"value": value})
        self.assertEqual(response.status_code, 200)

        loaded = self.client.get("/api/app-state?keys=sigp_notes_v1")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json["items"]["sigp_notes_v1"], value)
        self.assertEqual(
            self.client.put("/api/app-state/sigp_api_key", json={"value": "secret"}).status_code,
            400,
        )

    def test_local_api_round_trips_nested_operational_fields(self):
        payload = {
            "items": [{
                "id": "agency-1",
                "nome": "Agência Central",
                "cidade": "São Paulo",
                "vencimentoFatura": "2026-10-20",
                "provedores": [{"id": "provider-1", "nome": "Link"}],
                "notasFiscais": [{"id": "invoice-1", "numero": "123"}],
                "historicoVisitas": [{"id": "visit-1", "data": "2026-10-01"}],
                "redes": [{"nome": "Matriz", "ipWireguard": "10.0.0.1"}],
            }],
        }
        saved = self.client.put("/api/locais/agencia", json=payload)
        self.assertEqual(saved.status_code, 200)

        loaded = self.client.get("/api/locais?tipo=agencia")
        self.assertEqual(loaded.status_code, 200)
        agency = loaded.json["items"][0]
        self.assertEqual(agency["notasFiscais"], payload["items"][0]["notasFiscais"])
        self.assertEqual(agency["historicoVisitas"], payload["items"][0]["historicoVisitas"])
        self.assertEqual(agency["redes"], payload["items"][0]["redes"])
        self.assertEqual(agency["provedores"], payload["items"][0]["provedores"])
        self.assertEqual(agency["vencimentoFatura"], payload["items"][0]["vencimentoFatura"])

    def test_duplicate_invoice_key_is_rejected_without_overwriting(self):
        first = self.create_launch()
        response = self.client.post("/api/notas/lancadas", json={
            "id": "launch-duplicate",
            "entidadeTipo": "agencia",
            "entidadeId": "local-1",
            "dados": {
                "chave": first["chave"],
                "numero": first["numero"],
                "serie": first["serie"],
                "provedorNome": first["provedor_nome"],
                "localCidade": first["local_cidade"],
                "valorTotal": 250.0,
                "dataEmissao": first["data_emissao"],
                "servicos": [],
            },
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["existingId"], first["id"])
        self.assertEqual(len(database.list_nota_lancadas()), 1)
        self.assertEqual(database.get_nota_lancada(first["id"])["valor_total"], 100.0)

    def test_same_id_cannot_be_reused_for_another_invoice(self):
        self.create_launch()
        with self.assertRaises(database.DuplicateDocumentError):
            database.save_nota_lancada(make_note("launch-1") | {"chave": "other-key"})
        self.assertEqual(len(database.list_nota_lancadas()), 1)

    def test_payment_retries_are_idempotent_but_distinct_partial_payments_are_kept(self):
        first = self.create_payment("payment-1", 60.0, "2026-10-05")
        with self.assertRaises(database.DuplicateDocumentError):
            self.create_payment("payment-retry", 60.0, "2026-10-05")

        second = self.create_payment("payment-2", 40.0, "2026-10-06")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(database.list_nota_pagas()), 2)

    def test_distinct_payment_pairs_do_not_overwrite_conciliations(self):
        launched = self.create_launch()
        first_payment = self.create_payment("payment-1", 60.0, "2026-10-05")
        response = self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": first_payment["id"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "PAGO_PARCIAL")

        second_payment = self.create_payment("payment-2", 40.0, "2026-10-06")
        response = self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": second_payment["id"],
        })
        self.assertEqual(response.status_code, 200)
        # Lançada e paga conferem; sem fatura anexada o ciclo fica aguardando a fatura (MATCH exige 3 vias).
        self.assertEqual(response.json["status"], "AGUARDANDO_FATURA")

        results = database.list_conciliacoes()
        self.assertEqual(len(results), 2)
        self.assertEqual(len({item["id"] for item in results}), 2)

    def test_repeating_same_pair_updates_one_reconciliation(self):
        launched = self.create_launch()
        payment = self.create_payment("payment-1", 100.0, "2026-10-05")
        first = self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": payment["id"],
        }).json["resultado"]
        second = self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": payment["id"],
        }).json["resultado"]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(database.list_conciliacoes()), 1)

    def test_latest_invoice_for_provider_becomes_reconciliation_reference(self):
        launched = self.create_launch()
        payment = self.create_payment("payment-1", 100.0, "2026-10-05")
        database.save_fatura_local(
            "invoice-old", "agencia", "local-1", "", "old.pdf", "old.pdf",
            {"emissorNome": "Provedor", "provedorEsperado": "Provedor", "valorTotal": 100.0, "dataVencimento": "2026-10-10"},
            "provider-1", "Provedor",
        )
        first = self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": payment["id"],
        })
        self.assertEqual(first.json["status"], "MATCH")
        self.assertEqual(first.json["fatura"]["id"], "invoice-old")

        database.save_fatura_local(
            "invoice-current", "agencia", "local-1", "", "current.pdf", "current.pdf",
            {"emissorNome": "Provedor", "provedorEsperado": "Provedor", "valorTotal": 120.0, "dataVencimento": "2026-11-10"},
            "provider-1", "Provedor",
        )
        second = self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": payment["id"],
        })
        self.assertEqual(second.json["status"], "DIVERGENCIA")
        self.assertEqual(second.json["fatura"]["id"], "invoice-current")
        self.assertEqual(len(database.list_faturas_locais("agencia", "local-1")), 2)

    def test_delete_local_invoice_removes_pdf_and_updates_reconciliation(self):
        launched = self.create_launch()
        payment = self.create_payment("payment-1", 100.0, "2026-10-05")
        self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": payment["id"],
        })
        stored_pdf = self.faturas_dir / "invoice.pdf"
        stored_pdf.write_bytes(b"%PDF-test")
        database.save_fatura_local(
            "fatura-1",
            "agencia",
            "local-1",
            launched["id"],
            "fatura.pdf",
            stored_pdf.name,
            {"comparacao": {"emissorConfere": True, "valorConfere": True}},
        )
        self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": payment["id"],
        })
        self.assertEqual(database.list_conciliacoes()[0]["status"], "MATCH")

        response = self.client.delete("/api/faturas/fatura-1")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        self.assertFalse(stored_pdf.exists())
        self.assertIsNone(database.get_fatura_local("fatura-1"))
        reconciliation = database.list_conciliacoes()[0]
        self.assertEqual(reconciliation["status"], "AGUARDANDO_FATURA")
        self.assertEqual(reconciliation["fatura_id"], "")

    def test_delete_legacy_invoice_removes_pdf_and_updates_reconciliation(self):
        launched = self.create_launch()
        payment = self.create_payment("payment-1", 100.0, "2026-10-05")
        self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": payment["id"],
        })
        stored_pdf = self.faturas_dir / "legacy.pdf"
        stored_pdf.write_bytes(b"%PDF-test")
        database.save_fatura_provedor(
            launched["id"],
            "fatura.pdf",
            stored_pdf.name,
            {"comparacao": {"emissorConfere": True, "valorConfere": True}},
        )
        self.client.post("/api/notas/conciliar", json={
            "notaLancadaId": launched["id"],
            "notaPagaId": payment["id"],
        })
        self.assertEqual(database.list_conciliacoes()[0]["status"], "MATCH")

        response = self.client.delete(f"/api/notas/lancadas/{launched['id']}/fatura")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        self.assertFalse(stored_pdf.exists())
        self.assertIsNone(database.get_fatura_provedor(launched["id"]))
        self.assertEqual(database.list_conciliacoes()[0]["status"], "AGUARDANDO_FATURA")

    def test_delete_missing_invoice_returns_not_found(self):
        response = self.client.delete("/api/faturas/missing")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json["ok"])

    def test_api_marks_partial_payment_and_dashboard_validates_period(self):
        launch = self.client.post("/api/notas/lancadas", json={
            "id": "launch-1",
            "entidadeTipo": "agencia",
            "entidadeId": "local-1",
            "dados": make_note("launch-1"),
        })
        self.assertEqual(launch.status_code, 200)
        payment_payload = make_note("payment-1", paid=True, amount=60.0)
        payment = self.client.post("/api/notas/pagas", json={
            "id": "payment-1",
            "entidadeTipo": "agencia",
            "entidadeId": "local-1",
            "valorPago": 60.0,
            "dataPagamento": "2026-10-05",
            "dados": payment_payload,
        })
        self.assertEqual(payment.status_code, 200)
        self.assertEqual(payment.json["item"]["status"], "PAGO_PARCIAL")

        invalid_period = self.client.get("/api/sig/resumo?inicio=2026-13-01&fim=2026-10-31")
        self.assertEqual(invalid_period.status_code, 400)
        summary = self.client.get("/api/sig/resumo?inicio=2026-10-01&fim=2026-10-31")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["indicadores"]["notasLancadas"], 1)
        self.assertEqual(summary.json["indicadores"]["valorPendente"], 40.0)


if __name__ == "__main__":
    unittest.main()
