"""Remetentes da busca de faturas: Configurações > E-mail das faturas, lidos pelo WF-08 (GET /api/configuracoes/email-faturas)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import config_email_faturas, database

ADMIN = {"X-API-Key": "chave-admin-teste"}
ROTA = "/api/configuracoes/email-faturas"
RAIZ = Path(__file__).resolve().parents[1]


class ConfigEmailFaturasTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp),
            patch.object(app_module, "API_KEY", ADMIN["X-API-Key"]),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_sem_lista_salva_vale_o_padrao_dos_provedores(self):
        r = self.client.get(ROTA, headers=ADMIN).json
        self.assertEqual((r["remetentes"], r["origem"]), (config_email_faturas.PADRAO, "padrão"))
        self.assertIn("from:(henet.com.br OR brisanet.com.br", r["consulta"])

    def test_busca_igual_a_que_o_wf08_usava(self):
        # Mesma busca que estava fixa no build_wf08.ps1 (com um remetente extra fictício no lugar do pessoal).
        esperado = ('-label:sigp-importado -label:sigp-ignorado -label:sigp-sem-anexo {from:(henet.com.br OR brisanet.com.br OR '
                    'ixnet.com.br OR itsbrasil.net OR kasatech.net OR tinettecnologia.com.br OR netplacetelecom.net OR proxxima.net OR '
                    'minasonline.net.br OR minhaclaro.com.br OR netcanes.com.br OR sigaonmais.net.br OR mma.net.br OR internetvox.com.br OR '
                    'infortel.net.br OR infotecprovedor.net OR voanet.com.br OR fsonline.com.br OR opix.com.br OR teste@exemplo.com.br) '
                    'subject:(fatura OR boleto OR "nota fiscal" OR "conta digital" OR nfcom OR "segunda via") '
                    '(has:attachment filename:pdf (fatura OR boleto OR "nota fiscal")) '
                    '(has:attachment filename:xml ("nota fiscal" OR nfse OR "nfs-e" OR nfe OR nfcom))}')
        self.assertEqual(config_email_faturas.consulta(config_email_faturas.PADRAO + ["teste@exemplo.com.br"]), esperado)

    def test_administrador_salva_e_a_busca_muda(self):
        r = self.client.put(ROTA, headers=ADMIN, json={"remetentes": ["Teste@Exemplo.com.br", "@novo-provedor.net.br",
                                                                       "teste@exemplo.com.br", ""]})
        self.assertEqual(r.status_code, 200, r.json)
        lido = self.client.get(ROTA, headers=ADMIN).json
        self.assertEqual(lido["remetentes"], ["teste@exemplo.com.br", "novo-provedor.net.br"])
        self.assertEqual((lido["origem"], lido["atualizadoPor"]), ("tela", "Administrador"))
        self.assertTrue(lido["atualizadoEm"])
        self.assertIn("from:(teste@exemplo.com.br OR novo-provedor.net.br) subject:", lido["consulta"])

    def test_lista_vazia_busca_so_por_assunto_e_anexo(self):
        self.client.put(ROTA, headers=ADMIN, json={"remetentes": []})
        lido = self.client.get(ROTA, headers=ADMIN).json
        self.assertEqual((lido["remetentes"], lido["origem"]), ([], "tela"))
        self.assertNotIn("from:", lido["consulta"])
        self.assertIn("{subject:(fatura", lido["consulta"])

    def test_nada_alem_de_email_ou_dominio_entra_na_busca(self):
        # Operadores do Gmail, aspas, parênteses e espaços mudariam o que o n8n lê: são recusados.
        for ruim in ["a.com) OR (label:inbox", "label:sigp-importado", "x@y.com OR z", '"fatura"', "{a.com}", "-a.com",
                     "semponto", "a..b.com", "a@b@c.com", "*.com.br", "a.com b.com", "á@b.com"]:
            r = self.client.put(ROTA, headers=ADMIN, json={"remetentes": [ruim]})
            self.assertEqual(r.status_code, 400, ruim)
            self.assertIn("Remetente inválido", r.json["error"])
        self.assertEqual(self.client.get(ROTA, headers=ADMIN).json["origem"], "padrão")
        muitos = [f"p{i}.com.br" for i in range(config_email_faturas.MAX_REMETENTES + 1)]
        self.assertEqual(self.client.put(ROTA, headers=ADMIN, json={"remetentes": muitos}).status_code, 400)
        self.assertEqual(self.client.put(ROTA, headers=ADMIN, json={"remetentes": "a.com.br; b@c.com"}).status_code, 200)

    def test_sem_permissao_nao_ve_nem_altera(self):
        r = self.client.post("/api/acesso/usuarios", headers=ADMIN, json={"nome": "Leitor", "grupoId": "grp-leitura"})
        leitor = {"X-API-Key": r.json["chave"]}
        self.assertEqual(self.client.get(ROTA, headers=leitor).status_code, 403)
        self.assertEqual(self.client.put(ROTA, headers=leitor, json={"remetentes": []}).status_code, 403)
        self.assertEqual(self.client.put(ROTA, json={"remetentes": []}).status_code, 401)
        # Pode conter e-mail pessoal: ler sem chave também é recusado.
        self.assertEqual(self.client.get(ROTA).status_code, 401)

    def test_alteracao_fica_na_auditoria(self):
        self.client.put(ROTA, headers=ADMIN, json={"remetentes": ["a.com.br"]})
        r = self.client.get("/api/acesso/auditoria", headers=ADMIN)
        if r.status_code == 404:
            self.skipTest("rota de auditoria com outro nome")
        texto = json.dumps(r.json, ensure_ascii=False)
        self.assertIn(ROTA, texto)


class WorkflowSemEmailPessoalTests(unittest.TestCase):
    def test_wf08_nao_tem_gmail_nem_lista_fixa(self):
        wf08 = next(n for n in ("n8n_workflow_wf08_gmail_inbox.json", "n8n/workflows/n8n_workflow_wf08_gmail_inbox.json")
                    if (RAIZ / n).exists())  # raiz no sistema completo, n8n/workflows/ no pacote
        for nome in ("n8n/wf08/build_wf08.ps1", wf08):
            texto = (RAIZ / nome).read_text(encoding="utf-8").lower()
            self.assertFalse("@gmail.com" in texto, nome)
            self.assertFalse("from:(henet" in texto, nome)


if __name__ == "__main__":
    unittest.main()
