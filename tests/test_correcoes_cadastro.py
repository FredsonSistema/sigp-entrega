"""Correções do cadastro (backend/correcoes_cadastro.py): prévia, unificar nomes de provedor (sem desfazer por cópia
antiga da tela), dia de vencimento com sugestão, desativar unidade inválida, backup antes e permissão."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database

ADMIN = {"X-API-Key": "chave-admin-teste"}
LOCAIS = {
    "agencia": [
        {"id": "a1", "nome": "Agência Itacaré", "cidade": "Itacaré", "provedores": [
            {"id": "p1", "nome": "ITS TELECOMUNICAÇÕES LTDA"}, {"id": "p2", "nome": "vox", "diaVencimento": "15"}]},
        {"id": "a2", "nome": "TEIXEIRA CENTRO", "cidade": "Teixeira de Freitas", "provedores": [{"id": "p3", "nome": "CNEXÃOBA"}]},
        {"id": "a3", "nome": "TEIXEIRA TREVO", "cidade": "Teixeira de Freitas", "provedores": [{"id": "p4", "nome": "CONEXÃOBA"}]},
        {"id": "a4", "nome": "AGENCIAS", "cidade": "x"},
    ],
    "garagem": [{"id": "g1", "nome": "GRG ITN ROTA", "cidade": "Itabuna", "provedores": [
        {"id": "p5", "nome": "ITS"}, {"id": "p6", "nome": "Brisanet Telecomunicações 200MB+IP"}, {"id": "p7", "nome": "DStech"}]}],
}


class CorrecoesCadastroTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp),
            patch.object(app_module, "API_KEY", ADMIN["X-API-Key"]),
            patch.object(app_module, "_backup_dir", lambda: temp / "backups"),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()
        for tipo, itens in LOCAIS.items():
            self.assertEqual(self.client.put(f"/api/locais/{tipo}", headers=ADMIN, json={"items": itens}).status_code, 200)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def previa(self, headers=ADMIN):
        r = self.client.get("/api/cadastro/correcoes", headers=headers)
        self.assertEqual(r.status_code, 200, r.json)
        return r.json

    def provedores(self, local_id):
        return {p["id"]: p for p in self.client.get(f"/api/locais/item/{local_id}", headers=ADMIN).json["item"]["provedores"]}

    def test_previa_unificar_com_plano_e_sem_mexer_no_que_ja_esta_certo(self):
        p = self.previa()
        grupos = {g["provedor"]: [(i["de"], i["para"]) for i in g["itens"]] for g in p["unificar"]}
        self.assertEqual(grupos["ITS TELECOM"], [("ITS TELECOMUNICAÇÕES LTDA", "ITS TELECOM"), ("ITS", "ITS TELECOM")])
        self.assertEqual(grupos["CONEXÃOBA"], [("CNEXÃOBA", "CONEXÃOBA")])
        self.assertNotIn("BRISANET", grupos)  # um nome só (sem variantes): não entra
        self.assertNotIn("VOX", grupos)  # "vox" é o único nome do VOX: só caixa, não é variante
        self.assertEqual([u["unidade"] for u in p["unidadesInvalidas"]], ["Agência AGENCIAS"])

    def test_unificar_aplica_faz_backup_e_copia_antiga_da_tela_nao_desfaz(self):
        itens = [i for g in self.previa()["unificar"] for i in g["itens"]]
        r = self.client.post("/api/cadastro/correcoes/unificar", headers=ADMIN, json={"itens": itens})
        self.assertEqual((r.status_code, r.json["aplicados"]), (200, 3))
        self.assertTrue(r.json["backup"])
        self.assertEqual(self.provedores("a1")["p1"]["nome"], "ITS TELECOM")
        self.assertEqual(self.provedores("a2")["p3"]["nome"], "CONEXÃOBA")
        self.assertEqual(self.previa()["unificar"], [])
        # Uma aba aberta antes da correção regrava o local com o nome antigo: o nome unificado continua.
        antiga = [{**l, "provedores": [dict(p) for p in l.get("provedores", [])]} for l in LOCAIS["agencia"]]
        self.client.put("/api/locais/agencia", headers=ADMIN, json={"items": antiga})
        self.assertEqual(self.provedores("a1")["p1"]["nome"], "ITS TELECOM")

    def test_unificar_nao_aceita_nome_vindo_da_tela_e_confere_a_previa(self):
        itens = [{"localId": "a1", "provedorId": "p1", "de": "ITS TELECOMUNICAÇÕES LTDA", "para": "QUALQUER COISA"},
                 {"localId": "a2", "provedorId": "p3", "de": "nome que mudou", "para": "X"}]
        r = self.client.post("/api/cadastro/correcoes/unificar", headers=ADMIN, json={"itens": itens})
        self.assertEqual(r.json["aplicados"], 1)
        self.assertEqual(self.provedores("a1")["p1"]["nome"], "ITS TELECOM")  # calculado no servidor
        self.assertEqual(self.provedores("a2")["p3"]["nome"], "CNEXÃOBA")  # não bateu com a prévia: intocado

    def test_dia_de_vencimento_com_sugestao_e_protecao_contra_copia_antiga(self):
        for n in range(2):
            database.save_nota_recebida(f"m{n}", f"x{n}", f"t{n}", "Fatura", "faturas@dstech.exemplo", "2026-11-01T10:00:00",
                                        f"f{n}.pdf", f"f{n}.pdf", {"emissorNome": "DSTECH TELECOM LTDA", "dataVencimento": f"2026-1{n}-10"})
        v = {(x["localId"], x["provedorId"]): x for x in self.previa()["vencimento"]}
        self.assertEqual(v[("g1", "p7")]["sugestao"], 10)
        self.assertIn("provedor só neste local", v[("g1", "p7")]["fonte"])
        self.assertNotIn(("a1", "p2"), v)  # VOX já tem dia
        r = self.client.post("/api/cadastro/correcoes/vencimento", headers=ADMIN,
                             json={"itens": [{"localId": "g1", "provedorId": "p7", "dia": 10}, {"localId": "g1", "provedorId": "p5", "dia": 40}]})
        self.assertEqual(r.json["aplicados"], 1)  # dia 40 é recusado
        self.assertEqual(self.provedores("g1")["p7"]["diaVencimento"], "10")
        self.client.put("/api/locais/garagem", headers=ADMIN, json={"items": LOCAIS["garagem"]})  # cópia antiga, sem o dia
        self.assertEqual(self.provedores("g1")["p7"]["diaVencimento"], "10")

    def test_desativar_so_unidade_invalida(self):
        self.assertEqual(self.client.post("/api/cadastro/correcoes/desativar", headers=ADMIN, json={"localId": "a1"}).status_code, 400)
        r = self.client.post("/api/cadastro/correcoes/desativar", headers=ADMIN, json={"localId": "a4"})
        self.assertEqual((r.status_code, r.json["aplicados"]), (200, 1))
        ativos = [l["id"] for l in self.client.get("/api/locais?tipo=agencia", headers=ADMIN).json["items"]]
        self.assertNotIn("a4", ativos)
        self.client.put("/api/locais/agencia", headers=ADMIN, json={"items": LOCAIS["agencia"]})  # cópia antiga com a "AGENCIAS"
        self.assertNotIn("a4", [l["id"] for l in self.client.get("/api/locais?tipo=agencia", headers=ADMIN).json["items"]])

    def test_so_quem_edita_locais(self):
        g = self.client.post("/api/acesso/grupos", headers=ADMIN, json={"nome": "Só ver", "permissoes": ["locais.ver"]}).json["item"]
        chave = {"X-API-Key": self.client.post("/api/acesso/usuarios", headers=ADMIN, json={"nome": "V", "grupoId": g["id"]}).json["chave"]}
        self.assertEqual(self.client.get("/api/cadastro/correcoes", headers=chave).status_code, 403)
        self.assertEqual(self.client.post("/api/cadastro/correcoes/unificar", headers=chave, json={"itens": []}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
