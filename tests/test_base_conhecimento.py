"""Base de conhecimento das unidades (backend/base_conhecimento.py): normalização de provedor, regra de redundância,
rede/IPs só com permissão (inclusive ao gravar), qualidade do cadastro e as ferramentas novas do assistente."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import assistente
from backend import base_conhecimento as bc
from backend import database

ADMIN = {"X-API-Key": "chave-admin-teste"}
LOCAIS = {
    "rodoviaria": [{"id": "r1", "nome": "ROD. FEIRA DE SANTANA", "cidade": "Feira de Santana", "endereco": "Rodoviária de Feira",
                    "redes": ["RODFSA - 10.0.0.10"], "responsaveis": [{"nome": "Jadson Fictício", "telefone": "(75) 90000-0000"}],
                    "provedores": [{"nome": "FS Online 200Mb"}, {"nome": "FS Online 400Mb CS"}]}],
    "agencia": [
        {"id": "a1", "nome": "Agência Itacaré", "cidade": "Itacaré", "endereco": "R. Joaquim Vieira",
         "provedores": [{"nome": "vox"}, {"nome": "ITS TELECOMUNICAÇÕES LTDA", "valor": "174.00", "diaVencimento": "10"}]},
        {"id": "a2", "nome": "BOM DESPACHO", "cidade": "Vera Cruz", "endereco": "BOM DESPACHO",
         "obs": "TERCERIZADA - responsavel quem paga a conexão.", "provedores": [{"nome": "RAMOS NET"}]},
        {"id": "a3", "nome": "TEIXEIRA DE FREITAS TREVO", "cidade": "Teixeira de Freitas", "endereco": "",
         "obs": "empresa paga a conexão, desconta do agente - endereço não confirmado",
         "provedores": [{"nome": "CNEXÃOBA"}, {"nome": "Suporte / Whatsapp"}]},
        {"id": "a4", "nome": "AGENCIAS", "cidade": "x"},
    ],
    "garagem": [{"id": "g1", "nome": "GRG ITN ROTA", "cidade": "Itabuna", "endereco": "Av. Amélia Amado",
                 "provedores": [{"nome": "LKTELECOM"}, {"nome": "CONEXÃOBA"}]}],
}


class NormalizacaoTests(unittest.TestCase):
    def test_variantes_reais_viram_um_provedor_so(self):
        casos = {"Brisanet Telecomunicações 200MB+IP": ("BRISANET", "200MB+IP"), "Brisanet": ("BRISANET", None),
                 "ITS": ("ITS TELECOM", None), "ITS TELECOMUNICAÇÕES LTDA": ("ITS TELECOM", None),
                 "LKTELECOM": ("LK TELECOM", None), "CNEXÃOBA": ("CONEXÃOBA", None), "CONEXÃOBA": ("CONEXÃOBA", None),
                 "OPIX SERVICOS DE TECNOLOGIA EIRELI": ("OPIX", None), "Opix 300Mb": ("OPIX", "300Mb"), "OPIX INTERNET": ("OPIX", None),
                 "VCA Telecomunicacoes LTDA": ("VCA TELECOMUNICAÇÕES", None), "claro": ("CLARO", None), "CLARO 500Mb": ("CLARO", "500Mb"),
                 "VOX 10Mb Dedicado": ("VOX", "10Mb Dedicado"), "FS Online 400Mb CS": ("FS ONLINE", "400Mb CS"),
                 "SANTA INÊS NET": ("SANTA INÊS NET", None), "HE-NET": ("HE-NET", None)}
        for bruto, esperado in casos.items():
            self.assertEqual(bc.normalizar_provedor(bruto), esperado, bruto)

    def test_nome_invalido_nao_e_provedor(self):
        for bruto in ("Suporte / Whatsapp", "(73) 99999-0000", "73900000011", "", "CONSULTAR"):
            self.assertIsNone(bc.normalizar_provedor(bruto)[0], bruto)


class BaseConhecimentoTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp),
            patch.object(app_module, "API_KEY", ADMIN["X-API-Key"]),
            patch.object(app_module, "_lista_alertas", lambda hoje, janela, tipos=None: []),
            patch.object(assistente, "entender_por_llm", lambda pergunta: (None, "")),
        ]
        for item in self.patches:
            item.start()
        assistente._PROVEDORES_CONHECIDOS.clear()
        database.init_db()
        self.client = app_module.app.test_client()
        for tipo, itens in LOCAIS.items():
            self.assertEqual(self.client.put(f"/api/locais/{tipo}", headers=ADMIN, json={"items": itens}).status_code, 200)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        assistente._PROVEDORES_CONHECIDOS.clear()
        self.temp_dir.cleanup()

    def chave_de(self, permissoes):
        g = self.client.post("/api/acesso/grupos", headers=ADMIN, json={"nome": f"G{len(permissoes)}{id(permissoes)}", "permissoes": permissoes}).json["item"]
        return {"X-API-Key": self.client.post("/api/acesso/usuarios", headers=ADMIN, json={"nome": f"U{id(permissoes)}", "grupoId": g["id"]}).json["chave"]}

    def test_base_no_formato_rag_com_regras_de_links_e_redundancia(self):
        base = self.client.get("/api/base-conhecimento", headers=ADMIN).get_json()
        m = base["metricas_consolidadas"]
        # AGENCIAS (cabeçalho de planilha) fica fora; "Suporte / Whatsapp" não é link.
        self.assertEqual((m["total_unidades_validas"], m["total_links_internet"]), (5, 8))
        self.assertEqual(m["provedores_unicos"], ["CONEXÃOBA", "FS ONLINE", "ITS TELECOM", "LK TELECOM", "RAMOS NET", "VOX"])
        resumo = base["documentos_rag"][0]["dados_estruturados"]
        self.assertEqual(resumo["contagem_por_tipo"], {"Garagens": 1, "Rodoviárias": 1, "Agências": 3})
        # Dois links do mesmo provedor (FS Online) contam como reserva: cada link é uma conta.
        self.assertEqual(sorted(resumo["unidades_com_redundancia"]), ["Agência Itacaré", "GRG ITN ROTA", "ROD. FEIRA DE SANTANA"])
        rod = next(d for d in base["documentos_rag"] if d["metadata"].get("local_id") == "r1")
        self.assertEqual([p["plano_velocidade"] for p in rod["dados_estruturados"]["infraestrutura"]["provedores"]], ["200Mb", "400Mb CS"])
        self.assertIn("Rede/Gateway: RODFSA - 10.0.0.10", rod["texto_para_embedding"])
        self.assertTrue(base["rede_incluida"])

    def test_rede_e_ip_so_com_permissao_e_quem_nao_ve_nao_apaga(self):
        sem = self.chave_de(["locais.ver", "locais.editar", "assistente.usar"])
        base = self.client.get("/api/base-conhecimento", headers=sem).get_json()
        rod = next(d for d in base["documentos_rag"] if d["metadata"].get("local_id") == "r1")
        self.assertNotIn("10.0.0.10", str(base))
        self.assertIn("restrito", rod["dados_estruturados"]["infraestrutura"]["redes_ips"])
        locais = self.client.get("/api/locais?tipo=rodoviaria", headers=sem).json["items"]
        self.assertEqual((locais[0]["redes"], locais[0]["redesOcultas"]), ([], True))
        self.assertNotIn("10.0.0.10", str(locais))  # nem no registro bruto "dados"
        self.assertEqual(self.client.get("/api/locais/item/r1", headers=sem).json["item"]["redes"], [])
        # Grava sem as redes (como a tela faria): as redes continuam lá.
        r = self.client.put("/api/locais/rodoviaria", headers=sem, json={"items": [{**locais[0], "redes": [], "endereco": "Novo endereço"}]})
        self.assertEqual(r.status_code, 200)
        item = self.client.get("/api/locais/item/r1", headers=ADMIN).json["item"]
        self.assertEqual((item["redes"], item["endereco"]), (["RODFSA - 10.0.0.10"], "Novo endereço"))
        # Assistente: pergunta de IP sem permissão
        r = self.client.post("/api/assistente/perguntar", headers=sem, json={"pergunta": "qual o IP da rodoviária de Feira de Santana?"}).json
        self.assertEqual((r["ferramenta"], r["parametros"]["assunto"]), ("buscar_local", "rede"))
        self.assertIn("não pode ver rede e IPs", r["resposta"])
        com = self.client.post("/api/assistente/perguntar", headers=ADMIN, json={"pergunta": "qual o IP da rodoviária de Feira de Santana?"}).json
        self.assertIn("RODFSA - 10.0.0.10", com["resposta"])

    def test_qualidade_do_cadastro(self):
        q = self.client.get("/api/base-conhecimento/qualidade", headers=ADMIN).json
        resumo = q["resumo"]
        self.assertEqual(resumo["Unidade inválida"], 1)
        self.assertEqual(resumo["Nome de provedor inválido"], 1)
        self.assertEqual(resumo["Endereço genérico"], 1)  # BOM DESPACHO repete o nome
        self.assertEqual(resumo["Endereço não confirmado"], 1)
        self.assertNotIn("Whatsapp", str(q).replace("Suporte / Whatsapp", ""))
        variantes = [i["detalhe"] for i in q["itens"] if i["problema"] == "Nome de provedor com variantes"]
        self.assertEqual(variantes, ["CNEXAOBA, CONEXAOBA → unificar como CONEXÃOBA"])

    def test_assistente_resumo_redundancia_provedor_e_busca_nas_observacoes(self):
        def perguntar(texto):
            return self.client.post("/api/assistente/perguntar", headers=ADMIN, json={"pergunta": texto}).json
        r = perguntar("quantos provedores de internet temos?")
        self.assertEqual(r["ferramenta"], "resumo_geral")
        self.assertIn("Hoje temos 5 unidades: 3 agências, 1 rodoviárias e 1 garagens. São 8 links", r["resposta"])
        self.assertIn("de 6 provedores diferentes", r["resposta"])
        r = perguntar("quais unidades têm link reserva?")
        self.assertEqual((r["ferramenta"], r["parametros"]["redundancia"]), ("listar_locais", "sim"))
        self.assertIn("ROD. FEIRA DE SANTANA (Feira de Santana) · 2 links: FS ONLINE, FS ONLINE", r["resposta"])
        r = perguntar("quais locais usam a LK Telecom?")
        self.assertEqual((r["ferramenta"], r["parametros"]["provedor"]), ("listar_locais", "LK TELECOM"))
        self.assertIn("GRG ITN ROTA", r["resposta"])
        r = perguntar("onde está a conexaoba?")  # variante sem acento
        self.assertEqual(r["total"], 2)
        r = perguntar("quais agências são terceirizadas?")
        self.assertEqual(r["ferramenta"], "buscar_texto")
        self.assertIn("BOM DESPACHO (Vera Cruz): Observações: TERCERIZADA", r["resposta"])  # acha mesmo com o erro de digitação
        self.assertIsNone(r["artefato"])  # um resultado só fica no balão
        r = perguntar("onde a empresa paga a conexão?")
        self.assertIn("TEIXEIRA DE FREITAS TREVO", r["resposta"])
        self.assertIn("BOM DESPACHO", r["resposta"])  # "quem paga a conexão" também conta
        self.assertEqual(r["artefato"]["colunas"][3]["nome"], "Fonte")
        r = perguntar("como está a qualidade do cadastro?")
        self.assertEqual((r["ferramenta"], r["artefato"]["titulo"]), ("qualidade_cadastro", "Qualidade do cadastro"))
        r = perguntar("gere um relatório da qualidade do cadastro")
        self.assertEqual((r["ferramenta"], r["parametros"]["base"], len(r["arquivos"])), ("gerar_relatorio", "qualidade", 2))
        r = perguntar("qual a internet da agência de Itacaré?")
        self.assertIn("Tem 2 links (redundância).", r["resposta"])
        self.assertIn("ITS TELECOM", r["resposta"])


if __name__ == "__main__":
    unittest.main()
