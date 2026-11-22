"""Marcadores e grupos de localidades (backend/marcadores.py): migração dos marcadores antigos, catálogo, apelidos,
renomear/excluir em todos os locais (sem volta por cópia antiga da tela), grupos por regra do cadastro e permissão."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database, marcadores

ADMIN = {"X-API-Key": "chave-admin-teste"}
LOCAIS = {
    "agencia": [
        {"id": "a1", "nome": "Agência Itacaré", "cidade": "Itacaré", "marcadores": ["Regional Itabuna", "rota"],
         "provedores": [{"id": "p1", "nome": "HE-NET 100MB"}]},
        {"id": "a2", "nome": "Agência Jequié", "cidade": "Jequié", "marcadores": ["Regional Jequíe", "Cidade Sol", "CS"],
         "provedores": [{"id": "p2", "nome": "Brisanet"}, {"id": "p3", "nome": "Vox"}]},
        {"id": "a3", "nome": "AGENCIAS", "cidade": "x", "provedores": [{"id": "p4", "nome": "HE-NET"}]},
    ],
    "garagem": [{"id": "g1", "nome": "GRG Itabuna", "cidade": "Itabuna", "marcadores": ["Regional Itabuna"], "provedores": []}],
}


class MarcadoresTests(unittest.TestCase):
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
        for tipo, itens in LOCAIS.items():
            self.assertEqual(self.client.put(f"/api/locais/{tipo}", headers=ADMIN, json={"items": itens}).status_code, 200)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def cat(self, headers=ADMIN):
        r = self.client.get("/api/marcadores", headers=headers)
        self.assertEqual(r.status_code, 200, r.json)
        return {m["nome"]: m for m in r.json["items"]}

    def marc(self, local_id):
        return self.client.get(f"/api/locais/item/{local_id}", headers=ADMIN).json["item"].get("marcadores")

    def test_migracao_corrige_jequie_e_cria_catalogo_com_os_marcadores_antigos(self):
        # Banco com marcadores vindos do sistema antigo antes do catálogo existir.
        conn = database.get_connection()
        conn.execute("DROP TABLE marcadores")
        conn.execute("UPDATE locais SET dados_json = ? WHERE id = 'g1'", (json.dumps({"marcadores": ["Regional Jequíe", "Terceirizado", "Terceirizado"]}),))
        conn.commit()
        conn.close()
        marcadores.garantir_tabelas()
        self.assertEqual(self.marc("g1"), ["Regional Jequié", "Terceirizado"])
        nomes = {m["nome"]: m for m in marcadores.catalogo()}
        self.assertIn("Terceirizado", nomes)
        self.assertNotIn("Regional Jequíe", nomes)
        self.assertEqual(nomes["RT"]["descricao"], "Rota Transportes Rodoviários")
        self.assertIn("Rota", nomes["RT"]["apelidos"])

    def test_gravar_local_usa_grafia_do_catalogo_apelido_e_cria_marcador_novo(self):
        self.assertEqual(self.marc("a1"), ["Regional Itabuna", "RT"])  # "rota" é apelido de RT
        self.assertEqual(self.marc("a2"), ["Regional Jequié", "CS"])  # acento corrigido; Cidade Sol = CS, sem repetir
        c = self.cat()
        self.assertEqual((c["Regional Itabuna"]["locais"], c["RT"]["locais"]), (2, 1))
        self.assertEqual({m["id"] for m in c["Regional Itabuna"]["membros"]}, {"a1", "g1"})

    def test_renomear_e_excluir_valem_em_todos_os_locais_e_copia_antiga_nao_desfaz(self):
        mid = self.cat()["Regional Itabuna"]["id"]
        r = self.client.put(f"/api/marcadores/{mid}", headers=ADMIN, json={"nome": "Regional Sul", "tipo": "marcador", "cor": "#123456"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual((self.marc("a1"), self.marc("g1")), (["Regional Sul", "RT"], ["Regional Sul"]))
        # Cópia antiga da tela ainda com o nome antigo: vira o nome novo e não recria o antigo.
        self.client.put("/api/locais/garagem", headers=ADMIN, json={"items": [{**LOCAIS["garagem"][0]}]})
        self.assertEqual(self.marc("g1"), ["Regional Sul"])
        self.assertNotIn("Regional Itabuna", self.cat())
        rt = self.cat()["RT"]["id"]
        self.assertEqual(self.client.delete(f"/api/marcadores/{rt}", headers=ADMIN).json["locais"], 1)
        self.assertEqual(self.marc("a1"), ["Regional Sul"])
        self.client.put("/api/locais/agencia", headers=ADMIN, json={"items": LOCAIS["agencia"]})
        self.assertEqual(self.marc("a1"), ["Regional Sul"])  # "rota" (RT excluído) não volta
        self.assertNotIn("RT", self.cat())
        # Criar de novo um marcador excluído volta a valer.
        self.assertEqual(self.client.post("/api/marcadores", headers=ADMIN, json={"nome": "RT"}).status_code, 201)
        self.client.put("/api/locais/garagem", headers=ADMIN, json={"items": [{**LOCAIS["garagem"][0], "marcadores": ["RT"]}]})
        self.assertEqual(self.marc("g1"), ["RT"])

    def test_nome_repetido_e_grupo_sem_condicao_sao_recusados(self):
        self.assertEqual(self.client.post("/api/marcadores", headers=ADMIN, json={"nome": "regional itabuna"}).status_code, 400)
        r = self.client.post("/api/marcadores", headers=ADMIN, json={"nome": "Vazio", "tipo": "grupo", "regra": {"condicoes": []}})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/marcadores", headers=ADMIN, json={"nome": "X", "tipo": "grupo", "regra": {"condicoes": [{"campo": "sql", "valores": ["1"]}]}})
        self.assertEqual(r.status_code, 400)

    def test_grupo_por_provedor_reserva_e_marcador_com_previa(self):
        regra = {"condicoes": [{"campo": "provedor", "valores": ["He-Net"]}]}
        p = self.client.post("/api/marcadores/previa", headers=ADMIN, json={"regra": regra}).json
        self.assertEqual([m["id"] for m in p["membros"]], ["a1"])  # "AGENCIAS" (cabeçalho de planilha) não entra
        self.assertEqual(p["regraTexto"], "provedor é He-Net")
        self.assertEqual(self.client.post("/api/marcadores", headers=ADMIN, json={"nome": "He-Net", "tipo": "grupo", "regra": regra}).status_code, 201)
        regra2 = {"condicoes": [{"campo": "reserva", "valores": ["sim"]}, {"campo": "marcador", "valores": ["CS"]}]}
        self.client.post("/api/marcadores", headers=ADMIN, json={"nome": "CS com reserva", "tipo": "grupo", "regra": regra2})
        sem = {"condicoes": [{"campo": "sem_provedor", "valores": []}, {"campo": "tipo", "valores": ["garagem"]}]}
        self.client.post("/api/marcadores", headers=ADMIN, json={"nome": "Garagens sem link", "tipo": "grupo", "regra": sem})
        c = self.cat()
        self.assertEqual([m["id"] for m in c["He-Net"]["membros"]], ["a1"])
        self.assertEqual([m["id"] for m in c["CS com reserva"]["membros"]], ["a2"])
        self.assertEqual([m["id"] for m in c["Garagens sem link"]["membros"]], ["g1"])
        # Grupo acompanha o cadastro: trocar o provedor tira o local do grupo.
        self.client.put("/api/locais/agencia", headers=ADMIN, json={"items": [{**LOCAIS["agencia"][0], "provedores": [{"id": "p1", "nome": "Vox"}]}, LOCAIS["agencia"][1]]})
        self.assertEqual(self.cat()["He-Net"]["locais"], 0)

    def test_qualidade_aponta_marcador_com_nome_de_cidade_e_parecidos(self):
        locais = [{"id": "x1", "nome": "Ag Ilhéus", "cidade": "Ilhéus", "marcadores": ["Ilhéus", "Terceirizado"]},
                  {"id": "x2", "nome": "Ag Una", "cidade": "Una", "marcadores": ["Terceirizada"]}]
        probs = {(i["problema"], i["detalhe"].split(":")[0]) for i in marcadores.problemas(locais)}
        self.assertIn(("Marcador com nome de cidade", '"Ilhéus" (1 local(is))'), probs)
        self.assertIn(("Marcadores parecidos", '"Terceirizada" e "Terceirizado"'), probs)
        q = self.client.get("/api/base-conhecimento/qualidade", headers=ADMIN).json
        self.assertNotIn("Marcador com nome de cidade", q["resumo"])

    def test_alertas_trazem_a_regional_do_local(self):
        from datetime import date, timedelta
        venc = (date.today() - timedelta(days=5)).isoformat()
        itens = [{**LOCAIS["agencia"][0], "provedores": [{"id": "p1", "nome": "HE-NET", "dataVencimento": venc}]},
                 {**LOCAIS["agencia"][1], "provedores": [{"id": "p2", "nome": "Vox", "dataVencimento": venc}]}]
        self.client.put("/api/locais/agencia", headers=ADMIN, json={"items": itens})
        r = self.client.get("/api/alertas?dias=5", headers=ADMIN).json
        por_local = {a["entidadeId"]: a.get("regional") for a in r["items"] if a.get("status") == "VENCIDO"}
        self.assertEqual(por_local, {"a1": "Regional Itabuna", "a2": "Regional Jequié"})
        self.assertNotIn("regional", self.client.get("/api/locais/item/a1", headers=ADMIN).json["item"])

    def test_citado_na_pergunta_por_nome_e_apelido(self):
        self.assertEqual(marcadores.citado_na_pergunta("contas vencidas da Regional Itabuna")["nome"], "Regional Itabuna")
        self.assertEqual(marcadores.citado_na_pergunta("quais locais da Rota?")["nome"], "RT")
        self.assertEqual(marcadores.citado_na_pergunta("locais da Cidade Sol")["nome"], "CS")
        self.assertIsNone(marcadores.citado_na_pergunta("quantas agencias temos"))

    def test_permissao_ver_nao_edita(self):
        g = self.client.post("/api/acesso/grupos", headers=ADMIN, json={"nome": "Só ver", "permissoes": ["locais.ver"]}).json["item"]
        chave = {"X-API-Key": self.client.post("/api/acesso/usuarios", headers=ADMIN, json={"nome": "V", "grupoId": g["id"]}).json["chave"]}
        self.assertIn("RT", self.cat(chave))
        self.assertEqual(self.client.post("/api/marcadores", headers=chave, json={"nome": "Novo"}).status_code, 403)
        self.assertEqual(self.client.post("/api/marcadores/previa", headers=chave, json={"regra": {}}).status_code, 403)
        mid = self.cat()["RT"]["id"]
        self.assertEqual(self.client.delete(f"/api/marcadores/{mid}", headers=chave).status_code, 403)


if __name__ == "__main__":
    unittest.main()
