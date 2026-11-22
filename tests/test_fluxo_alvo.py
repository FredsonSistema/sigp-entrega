"""Testes do fluxo alvo: conciliação 3 vias, correção auditada, origem externa, locais, alertas, SIE e autenticação."""
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database
from backend.alerts import build_alerts, provider_due_status
from backend.dashboard import build_sig_summary, latest_reconciliations
from test_reconciliation import make_note


class FluxoAlvoTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp),
            patch.object(app_module, "API_KEY", ""),
            patch.object(app_module, "EXIGIR_FATURA", True),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    # helpers ---------------------------------------------------------------------------------
    def post_launch(self, note_id="launch-1", **extra):
        body = {"id": note_id, "entidadeTipo": "agencia", "entidadeId": "local-1", "dados": make_note(note_id)}
        body.update(extra)
        return self.client.post("/api/notas/lancadas", json=body)

    def post_payment(self, payment_id="payment-1", amount=100.0, day="2026-10-05", **extra):
        body = {"id": payment_id, "entidadeTipo": "agencia", "entidadeId": "local-1", "valorPago": amount,
                "dataPagamento": day, "dados": make_note(payment_id, paid=True, amount=amount)}
        body.update(extra)
        return self.client.post("/api/notas/pagas", json=body)

    def post_invoice(self, note_id="launch-1", amount=100.0, issuer="Provedor", description=""):
        dados = {"emissorNome": issuer, "dataVencimento": "2026-10-20", "valorTotal": amount, "emissorConfirmado": True}
        if description:
            dados["descricao"] = description
        return self.client.post("/api/faturas", data={
            "entidadeTipo": "agencia", "entidadeId": "local-1", "notaLancadaId": note_id,
            "provedorEsperado": "Provedor", "dadosExtracao": json.dumps(dados),
            "arquivo": (BytesIO(b"%PDF-1.4 teste"), "fatura.pdf"),
        }, content_type="multipart/form-data")

    # conciliação 3 vias ----------------------------------------------------------------------
    def test_payment_auto_reconciles_and_waits_for_invoice(self):
        self.assertEqual(self.post_launch().status_code, 200)
        response = self.post_payment()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["conciliacao"]["status"], "AGUARDANDO_FATURA")

    def test_payment_is_saved_before_launch_and_reconciled_when_launch_arrives(self):
        payment = self.post_payment()
        self.assertEqual(payment.status_code, 200)
        self.assertIsNone(payment.json["conciliacao"])
        self.assertIn("aguardando a importação", payment.json["aviso"])
        self.assertEqual([item["id"] for item in database.list_nota_pagas()], ["payment-1"])

        launched = self.post_launch()
        self.assertEqual(launched.status_code, 200, launched.json)
        self.assertEqual(launched.json["conciliacoes"], [
            {"notaPagaId": "payment-1", "status": "AGUARDANDO_FATURA"},
        ])

    def test_payment_for_another_location_is_not_auto_associated(self):
        payment = self.post_payment(
            entidadeId="local-2",
            dados=make_note("payment-1", paid=True),
        )
        self.assertEqual(payment.status_code, 200)
        launched = self.post_launch()
        self.assertEqual(launched.status_code, 200)
        self.assertEqual(launched.json["conciliacoes"], [])
        self.assertEqual(len(database.list_nota_pagas()), 1)

    def test_invoice_upload_turns_waiting_into_match(self):
        self.post_launch()
        self.post_payment()
        upload = self.post_invoice()
        self.assertEqual(upload.status_code, 200)
        self.assertEqual(upload.json["conciliacoes"], [{
            "notaLancadaId": "launch-1",
            "conciliacoes": [{"notaPagaId": "payment-1", "status": "MATCH"}],
        }])
        latest = latest_reconciliations(database.list_conciliacoes())["launch-1"]
        self.assertEqual(latest["status"], "MATCH")
        self.assertEqual(latest["fatura_match"], 1)

    def test_invoice_upload_persists_reviewed_service_description(self):
        self.post_launch()
        upload = self.post_invoice(description="Link principal de internet")

        self.assertEqual(upload.status_code, 200, upload.json)
        self.assertEqual(upload.json["item"]["dados"]["descricao"], "Link principal de internet")

    def test_existing_invoice_can_be_linked_with_reviewed_service_description(self):
        self.post_launch()
        database.save_fatura_local(
            "invoice-unlinked", "agencia", "local-1", "", "invoice.pdf", "invoice.pdf",
            {"emissorNome": "Provedor", "dataVencimento": "2026-10-20", "valorTotal": 100.0},
            provedor_nome="Provedor",
        )

        response = self.client.post("/api/faturas/invoice-unlinked/vincular", json={
            "notaLancadaId": "launch-1",
            "descricao": "Link principal de internet",
        })

        self.assertEqual(response.status_code, 200, response.json)
        saved = database.get_fatura_local("invoice-unlinked")
        self.assertEqual(saved["nota_lancada_id"], "launch-1")
        self.assertEqual(saved["dados"]["descricao"], "Link principal de internet")
        self.assertEqual(saved["dados"]["comparacao"]["emissorConfere"], True)
        self.assertEqual(saved["dados"]["comparacao"]["valorConfere"], True)
        self.assertEqual(saved["dados"]["statusComparacao"], "SEM_REFERENCIA")

    def test_existing_invoice_link_requires_same_location_and_description(self):
        self.post_launch()
        other_location_note = make_note("launch-other-location") | {
            "entidadeId": "local-2",
            "chave": "chave-other-location",
            "numero": "124",
        }
        database.save_nota_lancada(other_location_note)
        database.save_fatura_local(
            "invoice-unlinked", "agencia", "local-1", "", "invoice.pdf", "invoice.pdf",
            {"emissorNome": "Provedor", "dataVencimento": "2026-10-20", "valorTotal": 100.0},
            provedor_nome="Provedor",
        )

        missing_description = self.client.post("/api/faturas/invoice-unlinked/vincular", json={
            "notaLancadaId": "launch-1",
            "descricao": " ",
        })
        wrong_location = self.client.post("/api/faturas/invoice-unlinked/vincular", json={
            "notaLancadaId": "launch-other-location",
            "descricao": "Link principal de internet",
        })

        self.assertEqual(missing_description.status_code, 400)
        self.assertEqual(wrong_location.status_code, 400)
        self.assertEqual(database.get_fatura_local("invoice-unlinked")["nota_lancada_id"], "")

    def test_invoice_upload_requires_the_backend_note_id(self):
        self.post_launch()
        missing = self.post_invoice(note_id="local-only-note-id")
        self.assertEqual(missing.status_code, 404)
        self.assertIn("nota vinculada não foi encontrada", missing.json["error"])
        linked = self.post_invoice(note_id="launch-1")
        self.assertEqual(linked.status_code, 200)
        self.assertEqual(linked.json["item"]["notaLancadaId"], "launch-1")

    def test_received_gmail_pdf_is_idempotent_and_can_be_associated_and_labeled(self):
        created_local = self.client.post("/api/locais/agencia/item", json={
            "nome": "Agência Centro",
            "cidade": "Salvador",
        })
        self.assertEqual(created_local.status_code, 201, created_local.json)
        uploaded = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-message-1",
            "gmailThreadId": "gmail-thread-1",
            "assunto": "Nota fiscal de serviço",
            "remetente": "fiscal@example.com",
            "recebidaEm": "2026-11-06T10:00:00-03:00",
            "dadosExtracao": json.dumps({
                "emissorNome": "Provedor", "valorTotal": 100, "numero": "NF-001",
                "dataEmissao": "2026-11-05", "dataVencimento": "2026-11-20",
                "destinatarioNome": "Agência Centro",
            }),
            "arquivo": (BytesIO(b"%PDF-1.4 inbox"), "nota recebida.pdf"),
        }, content_type="multipart/form-data")
        repeated = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-message-1",
            "arquivo": (BytesIO(b"%PDF-1.4 duplicate"), "duplicada.pdf"),
        }, content_type="multipart/form-data")
        second_attachment = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-message-1",
            "gmailAttachmentId": "attachment-2",
            "arquivo": (BytesIO(b"%PDF-1.4 second attachment"), "segunda nota.pdf"),
        }, content_type="multipart/form-data")

        self.assertEqual(uploaded.status_code, 201, uploaded.json)
        self.assertEqual(uploaded.json["item"]["status"], "AGUARDANDO_ASSOCIACAO")
        self.assertEqual(uploaded.json["item"]["sugestoesLocal"][0]["id"], created_local.json["item"]["id"])
        self.assertEqual(repeated.status_code, 200, repeated.json)
        self.assertTrue(repeated.json["duplicada"])
        self.assertEqual(second_attachment.status_code, 201, second_attachment.json)
        self.assertFalse(second_attachment.json["duplicada"])
        self.assertEqual(len(list(Path(app_module.NOTAS_RECEBIDAS_DIR).glob("*.pdf"))), 2)

        item_id = uploaded.json["item"]["id"]
        associated = self.client.patch(f"/api/notas-recebidas/{item_id}/associar", json={
            "entidadeTipo": "agencia",
            "entidadeId": created_local.json["item"]["id"],
            "operador": "operador",
        })

        self.assertEqual(associated.status_code, 200, associated.json)
        self.assertEqual(associated.json["gmailLabel"], "SIGp/Agências/Agência Centro")
        self.assertEqual(associated.json["item"]["status"], "ASSOCIADA")
        # Documento do e-mail vira NOTA DISPONÍVEL do local; nota lançada é só do financeiro.
        self.assertTrue(associated.json["item"]["notaDisponivelId"])
        self.assertEqual(associated.json["item"]["notaLancadaId"], "")
        self.assertEqual(associated.json["item"]["dados"]["numero"], "NF-001")
        self.assertEqual(associated.json["notaDisponivel"]["numero"], "NF-001")
        self.assertIsNone(associated.json["notaLancada"])
        self.assertEqual(database.list_nota_lancadas(), [])
        self.assertEqual(len(database.list_faturas_locais()), 1)
        pending_labels = self.client.get("/api/notas-recebidas?etiquetaPendente=1")
        self.assertEqual([item["id"] for item in pending_labels.json["items"]], [item_id])

        confirmed = self.client.post(f"/api/notas-recebidas/{item_id}/confirmar-etiqueta", json={"ok": True})
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json["item"]["etiqueta_status"], "APLICADA")
        self.assertEqual(confirmed.json["item"]["etiqueta_erro"], "")
        self.assertEqual(self.client.get(uploaded.json["item"]["downloadUrl"]).data, b"%PDF-1.4 inbox")
        sie = self.client.get("/api/sie/resumo?inicio=2026-11-01&fim=2026-11-30")
        self.assertEqual(sie.status_code, 200, sie.json)
        # SIE só conta com todas as evidências: sem a nota lançada do financeiro, o documento ainda não entra.
        self.assertEqual(sie.json["notasRecebidas"], [])

    def test_received_gmail_pdf_extracts_fields_without_saving_until_association(self):
        created_local = self.client.post("/api/locais/agencia/item", json={
            "nome": "Agência OCR",
            "cidade": "Salvador",
        })
        uploaded = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-ocr-1",
            "arquivo": (BytesIO(b"%PDF-1.4 OCR"), "nota-ocr.pdf"),
        }, content_type="multipart/form-data")
        self.assertEqual(uploaded.status_code, 201, uploaded.json)
        ocr_body = {
            "ok": True,
            "text": (
                "Prestador: Provedor Exemplo\n"
                "Nota fiscal de serviço: NF-2026-07\n"
                "Valor total da nota: R$ 1.234,56\n"
                "Data de emissão: 05/11/2026\n"
                "Data de vencimento: 20/11/2026\n"
                "Descrição do serviço: Link dedicado"
            ),
            "ocrUsado": True,
            "textEncontrado": True,
        }
        with patch.object(app_module, "urlopen", return_value=BytesIO(json.dumps(ocr_body).encode())):
            extracted = self.client.post(f"/api/notas-recebidas/{uploaded.json['item']['id']}/extrair")

        self.assertEqual(extracted.status_code, 200, extracted.json)
        self.assertEqual(extracted.json["dados"]["emissorNome"], "Provedor Exemplo")
        self.assertEqual(extracted.json["dados"]["numero"], "NF-2026-07")
        self.assertEqual(extracted.json["dados"]["valorTotal"], 1234.56)
        self.assertEqual(extracted.json["dados"]["dataEmissao"], "2026-11-05")
        self.assertEqual(extracted.json["dados"]["dataVencimento"], "2026-11-20")
        self.assertTrue(extracted.json["ocrUsado"])
        self.assertEqual(database.list_nota_lancadas(), [])
        self.assertEqual(database.list_faturas_locais(), [])

        associated = self.client.patch(f"/api/notas-recebidas/{uploaded.json['item']['id']}/associar", json={
            "entidadeTipo": "agencia",
            "entidadeId": created_local.json["item"]["id"],
            "dados": extracted.json["dados"],
        })
        self.assertEqual(associated.status_code, 200, associated.json)
        self.assertEqual(associated.json["notaDisponivel"]["numero"], "NF-2026-07")
        self.assertEqual(len(database.list_nota_lancadas()), 0)
        invoices = database.list_faturas_locais()
        self.assertEqual(len(invoices), 1)
        self.assertEqual(
            (Path(app_module.FATURAS_DIR) / invoices[0]["arquivo_storage"]).read_bytes(),
            b"%PDF-1.4 OCR",
        )

    def test_received_pdf_extraction_preserves_fields_found_during_gmail_import(self):
        stored_fields = {
            "emissorNome": "ITS TELECOMUNICAÇÕES LTDA",
            "numero": "2847941",
            "valorTotal": 174.0,
            "dataEmissao": "2026-05-28",
            "dataVencimento": "2026-11-10",
            "descricaoServico": "PROVIMENTO DE ACESSO À INTERNET",
            "cnpjDestinatario": "76543210000130",
        }
        uploaded = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-its-1",
            "dadosExtracao": json.dumps(stored_fields),
            "arquivo": (BytesIO(b"%PDF-1.4 ITS"), "fatura-its.pdf"),
        }, content_type="multipart/form-data")
        self.assertEqual(uploaded.status_code, 201, uploaded.json)

        ocr_body = {
            "ok": True,
            "text": "Texto OCR sem rótulos compatíveis com o extrator atual.",
            "ocrUsado": False,
            "textEncontrado": True,
        }
        with patch.object(app_module, "urlopen", return_value=BytesIO(json.dumps(ocr_body).encode())):
            extracted = self.client.post(
                f"/api/notas-recebidas/{uploaded.json['item']['id']}/extrair"
            )

        self.assertEqual(extracted.status_code, 200, extracted.json)
        for key, value in stored_fields.items():
            self.assertEqual(extracted.json["dados"][key], value)
        self.assertEqual(extracted.json["dados"]["camposParaRevisar"], [])

    def test_received_invoice_divergence_requires_explicit_confirmation_to_update(self):
        created_local = self.client.post("/api/locais/agencia/item", json={
            "nome": "Agência Divergência",
            "cidade": "Salvador",
        })
        local_id = created_local.json["item"]["id"]

        def upload(message_id, number, amount, filename):
            return self.client.post("/api/notas-recebidas", data={
                "gmailMessageId": message_id,
                "dadosExtracao": json.dumps({
                    "emissorNome": "Provedor",
                    "numero": number,
                    "valorTotal": amount,
                    "dataEmissao": "2026-10-01",
                    "dataVencimento": "2026-10-20",
                }),
                "arquivo": (BytesIO(f"%PDF-1.4 {filename}".encode()), filename),
            }, content_type="multipart/form-data")

        first = upload("gmail-divergence-1", "NF-001", 100, "first.pdf")
        first_associated = self.client.patch(f"/api/notas-recebidas/{first.json['item']['id']}/associar", json={
            "entidadeTipo": "agencia",
            "entidadeId": local_id,
            "dados": first.json["item"]["dados"],
        })
        self.assertEqual(first_associated.status_code, 200, first_associated.json)
        first_note_id = first_associated.json["notaDisponivel"]["id"]

        second = upload("gmail-divergence-2", "NF-002", 120, "second.pdf")
        second_data = second.json["item"]["dados"]
        comparison = self.client.post(
            f"/api/notas-recebidas/{second.json['item']['id']}/comparar",
            json={"entidadeTipo": "agencia", "entidadeId": local_id, "dados": second_data},
        )
        self.assertEqual(comparison.status_code, 200, comparison.json)
        candidate = comparison.json["comparacao"]["candidatas"][0]
        self.assertEqual(candidate["notaDisponivelId"], first_note_id)
        self.assertIn("Número", [field["campo"] for field in candidate["diferencas"]])
        self.assertIn("Valor", [field["campo"] for field in candidate["diferencas"]])

        no_confirmation = self.client.patch(
            f"/api/notas-recebidas/{second.json['item']['id']}/associar",
            json={
                "entidadeTipo": "agencia",
                "entidadeId": local_id,
                "dados": second_data,
                "notaLancadaId": first_note_id,
            },
        )
        self.assertEqual(no_confirmation.status_code, 409)
        self.assertTrue(no_confirmation.json["requiresConfirmation"])
        self.assertEqual(len(database.list_nota_lancadas()), 0)
        self.assertEqual(len(database.list_faturas_locais()), 1)

        confirmed = self.client.patch(
            f"/api/notas-recebidas/{second.json['item']['id']}/associar",
            json={
                "entidadeTipo": "agencia",
                "entidadeId": local_id,
                "dados": second_data,
                "notaLancadaId": first_note_id,
                "confirmarAtualizacao": True,
            },
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.json)
        self.assertEqual(confirmed.json["notaDisponivel"]["id"], first_note_id)
        self.assertEqual(confirmed.json["notaDisponivel"]["numero"], "NF-002")
        self.assertEqual(confirmed.json["notaDisponivel"]["valor_total"], 120)
        self.assertEqual(len(database.list_nota_lancadas()), 0)
        self.assertEqual(len(database.list_faturas_locais()), 1)

    def test_received_pdf_ocr_failure_is_reported_without_persisting_invoice(self):
        uploaded = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-ocr-unavailable",
            "arquivo": (BytesIO(b"%PDF-1.4 OCR"), "nota-ocr.pdf"),
        }, content_type="multipart/form-data")
        with patch.object(app_module, "urlopen", side_effect=app_module.URLError("offline")):
            response = self.client.post(f"/api/notas-recebidas/{uploaded.json['item']['id']}/extrair")
        self.assertEqual(response.status_code, 503)
        self.assertIn("serviço OCR", response.json["error"])
        self.assertEqual(database.list_nota_lancadas(), [])

    def test_document_classifier_uses_registered_provider_and_keeps_uncertain_pdfs_for_review(self):
        created = self.client.post("/api/locais/agencia/item", json={
            "nome": "Agência Classificação",
            "cidade": "Salvador",
        })
        local = created.json["item"]
        database.sync_locais("agencia", [{
            "id": local["id"],
            "nome": local["nome"],
            "cidade": local["cidade"],
            "provedores": [{"nome": "Conecta Exemplo"}],
        }])

        classified = self.client.post("/api/notas-recebidas/classificar", json={
            "texto": "Nota fiscal de serviço de internet Conecta Exemplo - valor total da nota",
            "assunto": "Fatura mensal",
            "nomeArquivo": "documento.pdf",
        })
        uncertain = self.client.post("/api/notas-recebidas/classificar", json={
            "texto": "Relatório de visita técnica e imagens anexas",
            "assunto": "Documentos",
            "nomeArquivo": "anexo.pdf",
        })

        self.assertEqual(classified.status_code, 200, classified.json)
        self.assertEqual(classified.json["classificacao"]["categoria"], "NOTA_SERVICO_INTERNET")
        self.assertGreaterEqual(classified.json["classificacao"]["confianca"], 0.75)
        self.assertIn("Conecta Exemplo", classified.json["classificacao"]["provedoresEncontrados"])
        self.assertFalse(classified.json["classificacao"]["revisaoManual"])
        self.assertEqual(uncertain.status_code, 200, uncertain.json)
        self.assertEqual(uncertain.json["classificacao"]["categoria"], "REVISAO")
        self.assertTrue(uncertain.json["classificacao"]["revisaoManual"])

    def test_resending_received_pdf_updates_extraction_only_while_unassociated(self):
        def enviar(dados):
            return self.client.post("/api/notas-recebidas", data={
                "gmailMessageId": "msg-reprocessar",
                "gmailAttachmentId": "attachment_0:fatura.pdf",
                "remetente": "Fibra <fatura@fibra.example>",
                "dadosExtracao": json.dumps(dados),
                "arquivo": (BytesIO(b"%PDF-1.4 reprocessar"), "fatura.pdf"),
            }, content_type="multipart/form-data")

        first = enviar({"revisaoManual": True, "camposParaRevisar": ["ocr"]})
        second = enviar({"revisaoManual": False, "valorTotal": 99.9})

        self.assertEqual(first.status_code, 201, first.json)
        self.assertEqual(second.status_code, 200, second.json)
        self.assertTrue(second.json["duplicada"])
        self.assertTrue(second.json["atualizada"])
        stored = database.get_nota_recebida(first.json["item"]["id"])
        self.assertEqual(stored["dados"]["valorTotal"], 99.9)
        self.assertEqual(stored["status"], "AGUARDANDO_ASSOCIACAO")
        self.assertEqual(stored["arquivo_storage"], database.get_nota_recebida(first.json["item"]["id"])["arquivo_storage"])

        conn = database.get_connection()
        try:
            conn.execute(
                "UPDATE notas_recebidas SET status = 'ASSOCIADA', entidade_tipo = 'agencia', entidade_id = 'a1' WHERE id = ?",
                (first.json["item"]["id"],),
            )
            conn.commit()
        finally:
            conn.close()
        third = enviar({"revisaoManual": True, "valorTotal": 1.0})
        self.assertFalse(third.json["atualizada"])
        stored = database.get_nota_recebida(first.json["item"]["id"])
        self.assertEqual(stored["dados"]["valorTotal"], 99.9)
        self.assertEqual(stored["status"], "ASSOCIADA")

    def test_document_classifier_matches_sender_with_provider_email_or_domain(self):
        created = self.client.post("/api/locais/agencia/item", json={
            "nome": "Agência Remetente",
            "cidade": "Salvador",
        })
        local = created.json["item"]
        database.sync_locais("agencia", [{
            "id": local["id"],
            "nome": local["nome"],
            "cidade": local["cidade"],
            "provedores": [
                {"nome": "Fibra Exemplo", "email": "cobranca.exemplo.net.br"},
                {"nome": "Rede Teste", "email": "fatura@redeteste.com.br; financeiro@redeteste.com.br"},
            ],
        }])

        by_domain = self.client.post("/api/notas-recebidas/classificar", json={
            "texto": "Sua fatura chegou. Total a pagar R$ 99,90.",
            "assunto": "Sua fatura digital chegou",
            "remetente": "Financeiro <naoresponda@mail.cobranca.exemplo.net.br>",
        })
        by_address = self.client.post("/api/notas-recebidas/classificar", json={
            "texto": "Segue boleto do mês.",
            "remetente": "\"Rede\" <financeiro@redeteste.com.br>",
        })
        other_sender = self.client.post("/api/notas-recebidas/classificar", json={
            "texto": "Segue boleto do mês.",
            "remetente": "Loja <vendas@outrodominio.com.br>",
        })

        self.assertEqual(by_domain.json["classificacao"]["provedoresPorRemetente"], ["Fibra Exemplo"])
        self.assertEqual(by_domain.json["classificacao"]["categoria"], "FATURA_INTERNET")
        self.assertFalse(by_domain.json["classificacao"]["revisaoManual"])
        self.assertEqual(by_address.json["classificacao"]["provedoresPorRemetente"], ["Rede Teste"])
        self.assertGreaterEqual(by_address.json["classificacao"]["confianca"], 0.75)
        self.assertEqual(other_sender.json["classificacao"]["provedoresPorRemetente"], [])
        self.assertTrue(other_sender.json["classificacao"]["revisaoManual"])

    def test_received_invoice_updates_same_due_date_and_preserves_a_different_due_date(self):
        created_local = self.client.post("/api/locais/agencia/item", json={
            "nome": "Agência Centro",
            "cidade": "Salvador",
        })
        local_id = created_local.json["item"]["id"]

        def upload_and_associate(message_id, number, issue_date, due_date, amount, filename):
            uploaded = self.client.post("/api/notas-recebidas", data={
                "gmailMessageId": message_id,
                "dadosExtracao": json.dumps({
                    "emissorNome": "Provedor",
                    "numero": number,
                    "valorTotal": amount,
                    "dataEmissao": issue_date,
                    "dataVencimento": due_date,
                }),
                "arquivo": (BytesIO(f"%PDF-1.4 {filename}".encode()), filename),
            }, content_type="multipart/form-data")
            self.assertEqual(uploaded.status_code, 201, uploaded.json)
            associated = self.client.patch(f"/api/notas-recebidas/{uploaded.json['item']['id']}/associar", json={
                "entidadeTipo": "agencia",
                "entidadeId": local_id,
                "dados": {
                    "emissorNome": "Provedor",
                    "numero": number,
                    "valorTotal": amount,
                    "dataEmissao": issue_date,
                    "dataVencimento": due_date,
                },
            })
            if associated.status_code == 409 and associated.json.get("requiresConfirmation"):
                candidate_id = associated.json["comparacao"]["candidatas"][0]["notaDisponivelId"]
                associated = self.client.patch(
                    f"/api/notas-recebidas/{uploaded.json['item']['id']}/associar",
                    json={
                        "entidadeTipo": "agencia",
                        "entidadeId": local_id,
                        "dados": {
                            "emissorNome": "Provedor",
                            "numero": number,
                            "valorTotal": amount,
                            "dataEmissao": issue_date,
                            "dataVencimento": due_date,
                        },
                        "notaLancadaId": candidate_id,
                        "confirmarAtualizacao": True,
                    },
                )
            self.assertEqual(associated.status_code, 200, associated.json)
            return associated.json

        original = upload_and_associate(
            "gmail-same-due-1", "NF-100", "2026-10-01", "2026-10-20", 100, "original.pdf",
        )
        updated = upload_and_associate(
            "gmail-same-due-2", "NF-101", "2026-10-05", "2026-10-20", 125, "updated.pdf",
        )
        different_due = upload_and_associate(
            "gmail-different-due", "NF-102", "2026-11-01", "2026-11-20", 80, "second-period.pdf",
        )

        self.assertEqual(original["notaDisponivel"]["id"], updated["notaDisponivel"]["id"])
        self.assertEqual(updated["notaDisponivel"]["valor_total"], 125)
        self.assertNotEqual(updated["notaDisponivel"]["id"], different_due["notaDisponivel"]["id"])
        self.assertEqual(len(database.list_faturas_locais()), 2)
        self.assertEqual(len(database.list_nota_lancadas()), 0)
        current_invoice = next(
            invoice for invoice in database.list_faturas_locais()
            if invoice["nota_disponivel_id"] == updated["notaDisponivel"]["id"]
        )
        self.assertEqual(
            (Path(app_module.FATURAS_DIR) / current_invoice["arquivo_storage"]).read_bytes(),
            b"%PDF-1.4 updated.pdf",
        )
        sie = self.client.get("/api/sie/resumo?inicio=2026-10-01&fim=2026-11-30")
        self.assertEqual(sie.status_code, 200, sie.json)
        self.assertEqual(sie.json["indicadores"]["valorFechado"], 0)
        self.assertEqual(sie.json["notasRecebidas"], [])  # sem nota lançada do financeiro, a SIE não conta

    def test_legacy_received_gmail_table_migrates_to_per_attachment_deduplication(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        conn = sqlite3.connect(legacy_path)
        try:
            conn.execute(
                """
                CREATE TABLE notas_recebidas (
                    id TEXT PRIMARY KEY,
                    gmail_message_id TEXT NOT NULL UNIQUE,
                    gmail_thread_id TEXT NOT NULL DEFAULT '',
                    assunto TEXT NOT NULL DEFAULT '',
                    remetente TEXT NOT NULL DEFAULT '',
                    recebida_em TEXT NOT NULL DEFAULT '',
                    nome_arquivo TEXT NOT NULL,
                    arquivo_storage TEXT NOT NULL,
                    dados_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'AGUARDANDO_ASSOCIACAO',
                    entidade_tipo TEXT NOT NULL DEFAULT '',
                    entidade_id TEXT NOT NULL DEFAULT '',
                    etiqueta_gmail TEXT NOT NULL DEFAULT '',
                    etiqueta_status TEXT NOT NULL DEFAULT 'NAO_APLICAVEL',
                    operador TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX idx_notas_recebidas_status "
                "ON notas_recebidas(status, recebida_em DESC, created_at DESC)"
            )
            conn.execute(
                """
                INSERT INTO notas_recebidas (
                    id, gmail_message_id, nome_arquivo, arquivo_storage, created_at, updated_at
                ) VALUES ('legacy-note', 'gmail-legacy', 'legada.pdf', 'legacy.pdf', 'now', 'now')
                """
            )
            conn.commit()
        finally:
            conn.close()

        with patch.object(database, "DB_PATH", legacy_path):
            database.init_db()
            legacy_note = database.get_nota_recebida("legacy-note")
            second_attachment, created = database.save_nota_recebida(
                message_id="gmail-legacy",
                attachment_id="attachment-2",
                thread_id="",
                assunto="",
                remetente="",
                recebida_em="",
                nome_arquivo="segunda.pdf",
                arquivo_storage="second.pdf",
                dados={},
            )
            duplicate, duplicate_created = database.save_nota_recebida(
                message_id="gmail-legacy",
                attachment_id="attachment-2",
                thread_id="",
                assunto="",
                remetente="",
                recebida_em="",
                nome_arquivo="duplicada.pdf",
                arquivo_storage="duplicate.pdf",
                dados={},
            )
            conn = database.get_connection()
            try:
                columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(notas_recebidas)")
                }
                unique_keys = [
                    [
                        column["name"]
                        for column in conn.execute(f"PRAGMA index_info({index['name']})")
                    ]
                    for index in conn.execute("PRAGMA index_list(notas_recebidas)")
                    if index["unique"]
                ]
            finally:
                conn.close()

        self.assertEqual(legacy_note["id"], "legacy-note")
        self.assertEqual(legacy_note["gmail_attachment_id"], "default")
        self.assertIn("etiqueta_erro", columns)
        self.assertIn("nota_lancada_id", columns)
        self.assertTrue(created)
        self.assertEqual(second_attachment["gmail_attachment_id"], "attachment-2")
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate["id"], second_attachment["id"])
        self.assertIn(["gmail_message_id", "gmail_attachment_id"], unique_keys)
        self.assertNotIn(["gmail_message_id"], unique_keys)

    def test_received_gmail_pdf_rejects_non_pdf_and_invalid_location_association(self):
        not_pdf = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-message-invalid",
            "arquivo": (BytesIO(b"not pdf"), "nota.pdf"),
        }, content_type="multipart/form-data")
        self.assertEqual(not_pdf.status_code, 400)

        uploaded = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-message-2",
            "arquivo": (BytesIO(b"%PDF-1.4 inbox"), "nota.pdf"),
        }, content_type="multipart/form-data")
        wrong_location = self.client.patch(
            f"/api/notas-recebidas/{uploaded.json['item']['id']}/associar",
            json={"entidadeTipo": "agencia", "entidadeId": "missing"},
        )
        self.assertEqual(wrong_location.status_code, 404)
        self.assertEqual(database.get_nota_recebida(uploaded.json["item"]["id"])["status"], "AGUARDANDO_ASSOCIACAO")

    def test_gmail_label_failure_is_visible_and_retryable(self):
        created_local = self.client.post("/api/locais/agencia/item", json={
            "nome": "Agência Centro",
            "cidade": "Salvador",
        })
        uploaded = self.client.post("/api/notas-recebidas", data={
            "gmailMessageId": "gmail-message-label-failure",
            "dadosExtracao": json.dumps({
                "emissorNome": "Provedor", "numero": "NF-900", "valorTotal": 90,
                "dataEmissao": "2026-11-01", "dataVencimento": "2026-11-30",
            }),
            "arquivo": (BytesIO(b"%PDF-1.4 inbox"), "nota.pdf"),
        }, content_type="multipart/form-data")
        item_id = uploaded.json["item"]["id"]
        self.client.patch(f"/api/notas-recebidas/{item_id}/associar", json={
            "entidadeTipo": "agencia",
            "entidadeId": created_local.json["item"]["id"],
        })

        failure = self.client.post(
            f"/api/notas-recebidas/{item_id}/confirmar-etiqueta",
            json={"ok": False, "erro": "Gmail indisponível"},
        )
        self.assertEqual(failure.status_code, 200)
        self.assertEqual(failure.json["item"]["etiqueta_status"], "ERRO")
        self.assertEqual(failure.json["item"]["etiqueta_erro"], "Gmail indisponível")
        self.assertEqual(
            [item["id"] for item in self.client.get("/api/notas-recebidas?etiquetaPendente=1").json["items"]],
            [item_id],
        )

    def test_synthetic_xml_launch_payment_and_pdf_flow(self):
        xml = """<CompNfse><Nfse><InfNfse Id="NFSkey-xml-001">
          <Numero>88468</Numero><CodigoVerificacao>key-xml-001</CodigoVerificacao>
          <DataEmissao>2026-10-10</DataEmissao><DataVencimento>2026-10-20</DataVencimento>
          <ValorLiquidoNfse>100.00</ValorLiquidoNfse>
          <PrestadorServico><RazaoSocial>Provedor Demo</RazaoSocial></PrestadorServico>
          <TomadorServico><RazaoSocial>Unidade de Teste</RazaoSocial>
            <Endereco><xMun>Salvador</xMun></Endereco></TomadorServico>
          <InfDeclaracaoPrestacaoServico><Serie>A</Serie><Servico>
            <Discriminacao>Link de internet simulado</Discriminacao>
          </Servico></InfDeclaracaoPrestacaoServico>
        </InfNfse></Nfse></CompNfse>"""
        launch = self.client.post("/api/notas/lancadas", json={
            "id": "launch-xml-001", "source": "xml", "entidadeTipo": "agencia",
            "entidadeId": "local-1", "dados": xml,
        })
        self.assertEqual(launch.status_code, 200, launch.json)
        payment = self.client.post("/api/notas/pagas", json={
            "id": "payment-xml-001", "source": "xml", "entidadeTipo": "agencia",
            "entidadeId": "local-1", "valorPago": 100, "dataPagamento": "2026-10-11", "dados": xml,
        })
        self.assertEqual(payment.status_code, 200, payment.json)
        invoice = self.post_invoice(note_id="launch-xml-001", amount=100, issuer="Provedor Demo")
        self.assertEqual(invoice.status_code, 200, invoice.json)
        self.assertEqual(invoice.json["item"]["notaLancadaId"], "launch-xml-001")
        self.assertEqual(invoice.json["conciliacoes"][0]["conciliacoes"][0]["status"], "PENDENTE")

    def test_divergent_invoice_blocks_match(self):
        self.post_launch()
        self.post_invoice(amount=150.0)
        response = self.post_payment()
        self.assertEqual(response.json["conciliacao"]["status"], "DIVERGENCIA")

    def test_invoice_rule_can_be_disabled(self):
        with patch.object(app_module, "EXIGIR_FATURA", False):
            self.post_launch()
            self.assertEqual(self.post_payment().json["conciliacao"]["status"], "MATCH")

    def test_status_changes_are_queued_for_n8n_once(self):
        self.post_launch()
        self.post_payment()
        self.client.post("/api/notas/conciliar", json={"notaLancadaId": "launch-1", "notaPagaId": "payment-1"})
        queued = database.list_eventos()
        self.assertEqual([item["payload"]["status"] for item in queued], ["AGUARDANDO_FATURA"])
        self.post_invoice()
        statuses = sorted(item["payload"]["status"] for item in database.list_eventos())
        self.assertEqual(statuses, ["AGUARDANDO_FATURA", "MATCH"])

    # B1: desempate ---------------------------------------------------------------------------
    def test_latest_reconciliation_tie_prefers_most_advanced_status(self):
        rows = [
            {"nota_lancada_id": "n", "status": "PAGO_PARCIAL", "updated_at": "2026-10-10T00:49:51+00:00", "_ordem": 1},
            {"nota_lancada_id": "n", "status": "MATCH", "updated_at": "2026-10-10T00:49:51+00:00", "_ordem": 2},
        ]
        self.assertEqual(latest_reconciliations(rows)["n"]["status"], "MATCH")
        self.assertEqual(latest_reconciliations(list(reversed(rows)))["n"]["status"], "MATCH")

    # correção manual auditada -----------------------------------------------------------------
    def test_manual_correction_is_audited_and_reconciles_again(self):
        self.post_launch()
        launched = self.post_launch("launch-2")
        self.assertEqual(launched.status_code, 409)  # mesma chave
        self.post_payment()
        response = self.client.patch("/api/notas/lancadas/launch-1", json={
            "campos": {"valorTotal": 120.0}, "usuario": "fredson", "motivo": "valor digitado errado"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["alterados"], ["valor_total"])
        self.assertEqual(response.json["conciliacoes"][0]["status"], "DIVERGENCIA")
        history = self.client.get("/api/notas/lancadas/launch-1/correcoes").json["items"]
        self.assertEqual(history[0]["valor_anterior"], "100.0")
        self.assertEqual(history[0]["usuario"], "fredson")

    def test_manual_correction_requires_reason_and_blocks_duplicate_key(self):
        self.post_launch()
        other = make_note("launch-2") | {"chave": "outra-chave"}
        self.client.post("/api/notas/lancadas", json={"id": "launch-2", "dados": other, "entidadeId": "local-1"})
        self.assertEqual(self.client.patch("/api/notas/lancadas/launch-2", json={"campos": {"numero": "9"}}).status_code, 400)
        response = self.client.patch("/api/notas/lancadas/launch-2", json={
            "campos": {"chave": "chave-123"}, "usuario": "u", "motivo": "m"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.patch("/api/notas/lancadas/nao-existe", json={
            "campos": {"numero": "1"}, "usuario": "u", "motivo": "m"}).status_code, 404)

    def test_documents_without_identity_or_value_are_rejected(self):
        self.assertEqual(self.client.post("/api/notas/lancadas", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/notas/pagas", json={"valorPago": 10}).status_code, 400)
        zero = make_note("z") | {"valorTotal": 0}
        self.assertEqual(self.client.post("/api/notas/lancadas", json={"id": "z", "dados": zero}).status_code, 400)
        self.assertEqual(database.list_nota_lancadas(), [])

    # origem externa (Praxio/Globus) -----------------------------------------------------------
    def test_external_id_resend_updates_instead_of_duplicating(self):
        first = self.post_launch("praxio-a", origem="praxio", sistemaOrigem="praxio", idExterno="NF-77")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json["item"]["origem"], "praxio")
        again = self.post_launch("praxio-b", origem="praxio", sistemaOrigem="praxio", idExterno="NF-77")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json["item"]["id"], "praxio-a")
        self.assertEqual(len(database.list_nota_lancadas()), 1)

    # locais e alertas -------------------------------------------------------------------------
    def test_locais_sync_marks_missing_as_inactive(self):
        items = [{"id": "a1", "nome": "Centro", "cidade": "Itabuna", "provedores": [{"nome": "Algar", "diaVencimento": 10}]},
                 {"id": "a2", "nome": "Norte"}]
        self.assertEqual(self.client.put("/api/locais/agencia", json={"items": items}).json["recebidos"], 2)
        result = self.client.put("/api/locais/agencia", json={"items": items[:1]}).json
        self.assertEqual(result["inativados"], 1)
        listed = self.client.get("/api/locais?tipo=agencia").json["items"]
        self.assertEqual([item["id"] for item in listed], ["a1"])
        self.assertEqual(listed[0]["provedores"][0]["nome"], "Algar")
        self.assertEqual(self.client.put("/api/locais/invalido", json={"items": []}).status_code, 400)

    def test_provider_due_status_matches_browser_rule(self):
        today = date(2026, 10, 9)
        self.assertEqual(provider_due_status(5, "", today, 7)["status"], "VENCIDO")
        self.assertEqual(provider_due_status(9, "", today, 7)["status"], "VENCE_HOJE")
        # ciclo anterior (12/09) sem pagamento continua vencido, como no navegador
        self.assertEqual(provider_due_status(12, "", today, 7)["status"], "VENCIDO")
        self.assertEqual(provider_due_status(12, "2026-09-20", today, 7)["status"], "VENCE_EM_BREVE")
        self.assertIsNone(provider_due_status(5, "2026-11-01", today, 7))
        self.assertIsNone(provider_due_status(25, "2026-09-30", today, 7))

    def test_alerts_cover_due_dates_missing_invoice_and_divergence(self):
        locais = [{"id": "local-1", "tipo": "agencia", "nome": "Centro", "vencimento_fatura": "",
                   "provedores": [{"nome": "Algar", "diaVencimento": 5}]}]
        launched = [make_note("n1") | {"id": "n1", "entidade_tipo": "agencia", "entidade_id": "local-1",
                                       "valor_total": 100.0, "data_vencimento": "2026-10-01", "fatura_anexada": 0}]
        alerts = build_alerts(locais, launched, [], [{"nota_lancada_id": "n1", "status": "DIVERGENCIA", "updated_at": "x"}],
                              date(2026, 10, 9), 7)
        kinds = {(item["tipo"], item["origem"], item["status"]) for item in alerts}
        self.assertIn(("vencimento", "provedor", "VENCIDO"), kinds)
        self.assertIn(("vencimento", "nota", "VENCIDO"), kinds)
        self.assertIn(("fatura_ausente", "nota", "FATURA_AUSENTE"), kinds)
        self.assertIn(("divergencia", "conciliacao", "DIVERGENCIA"), kinds)
        self.assertEqual(self.client.get("/api/alertas?dias=abc").status_code, 400)
        self.assertEqual(self.client.get("/api/alertas?tipo=fatura_ausente").status_code, 200)

    def test_overdue_uses_today_not_end_of_filter(self):
        note = make_note("n") | {"id": "n", "data_emissao": "2026-10-01", "data_vencimento": "2026-10-20", "valor_total": 100}
        result = build_sig_summary([note], [], [], "2026-10-01", "2026-12-31", today=date(2026, 10, 9))
        self.assertEqual(result["indicadores"]["vencidas"], 0)
        result = build_sig_summary([note], [], [], "2026-10-01", "2026-12-31", today=date(2026, 10, 25))
        self.assertEqual(result["indicadores"]["vencidas"], 1)

    # SIE e análises ----------------------------------------------------------------------------
    def test_sie_summary_only_counts_closed_cycles_and_returns_analysis(self):
        self.post_launch()
        self.post_payment()
        empty = self.client.get("/api/sie/resumo?inicio=2026-10-01&fim=2026-10-31").json
        self.assertEqual(empty["indicadores"]["ciclosFechados"], 0)
        self.post_invoice()
        # C-04: ciclo fechado pela regra só entra na SIE depois que o gerente valida a análise no SIG.
        aguardando = self.client.get("/api/sie/resumo?inicio=2026-10-01&fim=2026-10-31").json
        self.assertEqual(aguardando["indicadores"]["ciclosFechados"], 0)
        self.assertEqual(aguardando["indicadores"]["aguardandoGerente"], 1)
        analise = self.client.post("/api/analises", json={
            "escopo": "SIG", "referencia": "launch-1", "conteudo": "Ciclo confere.", "dados": {"requerValidacao": True},
        }).json["item"]
        with patch.object(app_module.events, "webhook_url", lambda: ""):
            decisao = self.client.post("/api/sig/decisoes", json={"analiseId": analise["id"], "acao": "validar", "usuario": "gerente"})
        self.assertEqual(decisao.status_code, 200, decisao.json)
        saved = self.client.post("/api/analises", json={"escopo": "SIE", "conteudo": "Ciclo fechado sem ressalvas."})
        self.assertEqual(saved.status_code, 200)
        summary = self.client.get("/api/sie/resumo?inicio=2026-10-01&fim=2026-10-31").json
        self.assertEqual(summary["indicadores"]["ciclosFechados"], 1)
        self.assertEqual(summary["indicadores"]["aguardandoGerente"], 0)
        self.assertEqual(summary["indicadores"]["valorFechado"], 100.0)
        self.assertEqual(summary["analises"][0]["conteudo"], "Ciclo fechado sem ressalvas.")
        self.assertEqual(self.client.post("/api/analises", json={"escopo": "X", "conteudo": "a"}).status_code, 400)

    # autenticação e CORS -----------------------------------------------------------------------
    def test_api_key_required_for_writes_when_configured(self):
        with patch.object(app_module, "API_KEY", "segredo"):
            self.assertEqual(self.client.get("/api/health").status_code, 200)
            self.assertEqual(self.post_launch().status_code, 401)
            self.assertEqual(self.client.post("/api/auth/verify").status_code, 401)
            self.assertEqual(self.client.post(
                "/api/auth/verify", headers={"X-API-Key": "segredo"}
            ).status_code, 200)
            ok = self.client.post("/api/notas/lancadas", headers={"X-API-Key": "segredo"},
                                  json={"id": "x", "entidadeId": "local-1", "dados": make_note("x")})
            self.assertEqual(ok.status_code, 200)

    def test_cors_only_echoes_allowed_origins(self):
        allowed = self.client.get("/api/health", headers={"Origin": "http://127.0.0.1:8000"})
        self.assertEqual(allowed.headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:8000")
        other = self.client.get("/api/health", headers={"Origin": "http://malicioso.example"})
        self.assertIsNone(other.headers.get("Access-Control-Allow-Origin"))

    def test_healthcheck_returns_unavailable_when_sqlite_cannot_be_queried(self):
        with patch.object(app_module, "get_connection", side_effect=sqlite3.OperationalError("disk I/O error")):
            response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["status"], "error")


if __name__ == "__main__":
    unittest.main()
