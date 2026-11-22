"""Login no servidor (backend/sessoes.py): primeiro administrador, pessoa criada pelo administrador com senha
temporária, troca obrigatória, bloqueio por tentativas, sessão encerrada e nenhum caminho para "inventar" usuário."""
import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as app_module
from backend import database, sessoes

CHAVE_ENV = "chave-admin-teste"
ADMIN_ENV = {"X-API-Key": CHAVE_ENV}
SENHA_ADMIN = "Senha-do-dono-2026"


class SessoesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp = Path(self.temp_dir.name)
        self.patches = [
            patch.object(database, "DB_PATH", temp / "test.db"),
            patch.object(app_module, "FATURAS_DIR", temp),
            patch.object(app_module, "NOTAS_RECEBIDAS_DIR", temp),
            patch.object(app_module, "API_KEY", CHAVE_ENV),
        ]
        for item in self.patches:
            item.start()
        database.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    # ------------------------------------------------------------ ajudantes
    def primeiro_admin(self):
        r = self.client.post("/api/auth/primeiro-admin", json={"chave": CHAVE_ENV, "usuario": "fredson.santos",
                                                               "nome": "Fredson", "senha": SENHA_ADMIN})
        self.assertEqual(r.status_code, 201, r.json)

    def entrar(self, usuario, senha):
        return self.client.post("/api/auth/login", json={"usuario": usuario, "senha": senha})

    def sessao(self, usuario, senha):
        r = self.entrar(usuario, senha)
        self.assertEqual(r.status_code, 200, r.json)
        return {"Authorization": f"Bearer {r.json['token']}"}

    def pessoa(self, usuario, grupo, admin_h):
        r = self.client.post("/api/acesso/usuarios", headers=admin_h, json={"tipo": "pessoa", "nome": usuario, "usuario": usuario, "grupoId": grupo})
        self.assertEqual(r.status_code, 201, r.json)
        return r.json["item"], r.json["senhaTemporaria"]

    # ------------------------------------------------------------ testes
    def test_primeiro_acesso_exige_a_chave_do_env_e_so_funciona_uma_vez(self):
        self.assertTrue(self.client.get("/api/auth/estado").json["precisaPrimeiroAdmin"])
        r = self.client.post("/api/auth/primeiro-admin", json={"chave": "chute", "usuario": "invasor", "senha": "qualquer-coisa-123"})
        self.assertEqual(r.status_code, 401)
        self.primeiro_admin()
        self.assertFalse(self.client.get("/api/auth/estado").json["precisaPrimeiroAdmin"])
        r = self.client.post("/api/auth/primeiro-admin", json={"chave": CHAVE_ENV, "usuario": "outro", "senha": "Outra-senha-2026"})
        self.assertEqual(r.status_code, 409)
        eu = self.client.get("/api/acesso/eu", headers=self.sessao("fredson.santos", SENHA_ADMIN)).json
        self.assertEqual((eu["perfil"], eu["usuario"], eu["trocarSenha"]), ("administrador", "fredson.santos", False))

    def test_usuario_inventado_nao_entra_e_senha_fica_so_como_hash(self):
        self.primeiro_admin()
        self.assertEqual(self.entrar("teste", "senha1234").status_code, 401)
        self.assertEqual(self.entrar("fredson.santos", "errada-123").json["error"], "Usuário ou senha incorretos.")
        with closing(sqlite3.connect(database.DB_PATH)) as conn, conn:
            guardado = conn.execute("SELECT senha_hash FROM acesso_usuarios WHERE usuario = 'fredson.santos'").fetchone()[0]
            tokens = [r[0] for r in conn.execute("SELECT token_hash FROM acesso_sessoes")]
        self.assertTrue(guardado.startswith("scrypt$") and SENHA_ADMIN not in guardado)
        token = self.entrar("fredson.santos", SENHA_ADMIN).json["token"]
        with closing(sqlite3.connect(database.DB_PATH)) as conn, conn:
            tokens = [r[0] for r in conn.execute("SELECT token_hash FROM acesso_sessoes")]
        self.assertNotIn(token, tokens)

    def test_pessoa_criada_com_senha_temporaria_e_obrigada_a_trocar(self):
        self.primeiro_admin()
        admin = self.sessao("fredson.santos", SENHA_ADMIN)
        item, temp = self.pessoa("maciel", "grp-operador", admin)
        self.assertTrue(item["trocarSenha"])
        self.assertEqual((item["tipo"], item["chavePrefixo"]), ("pessoa", ""))
        r = self.entrar("maciel", temp)
        self.assertTrue(r.json["trocarSenha"])
        h = {"Authorization": f"Bearer {r.json['token']}"}
        # Antes de trocar: nada funciona, nem leitura.
        bloqueado = self.client.get("/api/locais", headers=h)
        self.assertEqual((bloqueado.status_code, bloqueado.json.get("trocarSenha")), (403, True))
        self.assertEqual(self.client.get("/api/acesso/eu", headers=h).status_code, 200)
        # Regras da senha nova.
        for nova, trecho in (("curta", "8 caracteres"), ("maciel-2026", "nome de usuário"), ("aaaaaaaa", "fácil")):
            r = self.client.post("/api/auth/trocar-senha", headers=h, json={"senhaAtual": temp, "novaSenha": nova})
            self.assertEqual(r.status_code, 400)
            self.assertIn(trecho, r.json["error"])
        self.assertEqual(self.client.post("/api/auth/trocar-senha", headers=h, json={"senhaAtual": "errada", "novaSenha": "Nova-senha-99"}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/trocar-senha", headers=h, json={"senhaAtual": temp, "novaSenha": "Nova-senha-99"}).status_code, 200)
        self.assertEqual(self.client.get("/api/locais", headers=h).status_code, 200)
        self.assertEqual(self.client.post("/api/sig/decisoes", headers=h, json={}).status_code, 403)  # operador não decide
        self.assertEqual(self.entrar("maciel", temp).status_code, 401)  # a temporária deixou de valer

    def test_cinco_erros_bloqueiam_e_o_administrador_redefine(self):
        self.primeiro_admin()
        admin = self.sessao("fredson.santos", SENHA_ADMIN)
        item, temp = self.pessoa("jonatas", "grp-leitura", admin)
        for _ in range(sessoes.MAX_TENTATIVAS):
            self.entrar("jonatas", "chute-errado")
        r = self.entrar("jonatas", temp)
        self.assertEqual(r.status_code, 401)
        self.assertIn("Muitas tentativas", r.json["error"])
        r = self.client.post(f"/api/acesso/usuarios/{item['id']}/redefinir-senha", headers=admin)
        self.assertEqual(r.status_code, 200)
        nova_temp = r.json["senhaTemporaria"]
        self.assertTrue(self.entrar("jonatas", nova_temp).json["trocarSenha"])

    def test_sair_desativar_e_redefinir_encerram_a_sessao(self):
        self.primeiro_admin()
        admin = self.sessao("fredson.santos", SENHA_ADMIN)
        item, temp = self.pessoa("aeverton", "grp-gerente", admin)
        h = self.sessao("aeverton", temp)
        self.client.post("/api/auth/trocar-senha", headers=h, json={"senhaAtual": temp, "novaSenha": "Senha-forte-77"})
        self.assertEqual(self.client.get("/api/locais", headers=h).status_code, 200)
        self.client.post("/api/auth/sair", headers=h)
        self.assertEqual(self.client.get("/api/locais", headers=h).status_code, 401)
        h = self.sessao("aeverton", "Senha-forte-77")
        self.client.put(f"/api/acesso/usuarios/{item['id']}", headers=admin, json={"ativo": False})
        self.assertEqual(self.client.get("/api/locais", headers=h).status_code, 401)
        self.assertIn("desativado", self.entrar("aeverton", "Senha-forte-77").json["error"])

    def test_unico_administrador_nao_pode_ser_rebaixado_nem_desativado(self):
        self.primeiro_admin()
        admin = self.sessao("fredson.santos", SENHA_ADMIN)
        eu = [u for u in self.client.get("/api/acesso/usuarios", headers=admin).json["items"] if u["usuario"] == "fredson.santos"][0]
        self.assertEqual(eu["grupoNome"], "Administrador")
        r = self.client.put(f"/api/acesso/usuarios/{eu['id']}", headers=admin, json={"ativo": False})
        self.assertEqual(r.status_code, 400)
        self.assertIn("único administrador", r.json["error"])

    def test_integracao_continua_com_chave_e_pessoa_nao_tem_chave(self):
        self.primeiro_admin()
        admin = self.sessao("fredson.santos", SENHA_ADMIN)
        r = self.client.post("/api/acesso/usuarios", headers=admin, json={"tipo": "integracao", "nome": "Outro sistema", "grupoId": "grp-integracao"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.get("/api/locais", headers={"X-API-Key": r.json["chave"]}).status_code, 200)
        item, _ = self.pessoa("maria", "grp-leitura", admin)
        self.assertEqual(self.client.post(f"/api/acesso/usuarios/{item['id']}/nova-chave", headers=admin).status_code, 404)
        # A chave do .env (n8n) continua sendo administrador.
        self.assertEqual(self.client.get("/api/acesso/usuarios", headers=ADMIN_ENV).status_code, 200)

    def test_sessao_inventada_ou_expirada_e_recusada(self):
        self.assertEqual(self.client.get("/api/locais", headers={"Authorization": "Bearer inventado"}).status_code, 401)
        self.primeiro_admin()
        h = self.sessao("fredson.santos", SENHA_ADMIN)
        with closing(sqlite3.connect(database.DB_PATH)) as conn, conn:
            conn.execute("UPDATE acesso_sessoes SET expira_em = '2000-01-01T00:00:00+00:00'")
        r = self.client.get("/api/locais", headers=h)
        self.assertEqual((r.status_code, r.json.get("sessao")), (401, "expirada"))

    def test_autor_da_decisao_e_o_usuario_da_sessao_nao_o_nome_enviado(self):
        self.primeiro_admin()
        admin = self.sessao("fredson.santos", SENHA_ADMIN)
        analise = self.client.post("/api/analises", headers=ADMIN_ENV, json={
            "escopo": "SIG", "titulo": "Teste", "referencia": "ref-autor", "conteudo": "Análise fictícia.",
            "dados": {"status": "MATCH", "requerValidacao": True}}).json["item"]
        r = self.client.post("/api/sig/decisoes", headers=admin, json={
            "analiseId": analise["id"], "acao": "validar", "justificativa": "Confere com o comprovante.", "usuario": "outra.pessoa"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["decisao"]["usuario"], "fredson.santos")

    def test_administrador_corrige_o_nome_de_usuario(self):
        self.client.post("/api/auth/primeiro-admin", json={"chave": CHAVE_ENV, "usuario": "fredsoon.santos", "senha": SENHA_ADMIN})
        admin = self.sessao("fredsoon.santos", SENHA_ADMIN)
        eu = [u for u in self.client.get("/api/acesso/usuarios", headers=admin).json["items"] if u["usuario"] == "fredsoon.santos"][0]
        r = self.client.put(f"/api/acesso/usuarios/{eu['id']}", headers=admin, json={"usuario": "Fredson.Santos"})
        self.assertEqual((r.status_code, r.json["item"]["usuario"]), (200, "fredson.santos"))
        self.assertEqual(self.entrar("fredsoon.santos", SENHA_ADMIN).status_code, 401)
        self.assertEqual(self.entrar("fredson.santos", SENHA_ADMIN).status_code, 200)  # mesma senha
        self.assertEqual(self.client.get("/api/acesso/eu", headers=admin).json["usuario"], "fredson.santos")  # sessão aberta continua
        _, temp = self.pessoa("maria", "grp-leitura", admin)
        maria = [u for u in self.client.get("/api/acesso/usuarios", headers=admin).json["items"] if u["usuario"] == "maria"][0]
        r = self.client.put(f"/api/acesso/usuarios/{maria['id']}", headers=admin, json={"usuario": "fredson.santos"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Já existe", r.json["error"])
        r = self.client.put(f"/api/acesso/usuarios/{maria['id']}", headers=admin, json={"usuario": "x"})
        self.assertIn("3 a 40", r.json["error"])

    def test_login_e_falhas_vao_para_a_auditoria(self):
        self.primeiro_admin()
        self.entrar("fredson.santos", "errada-123")
        admin = self.sessao("fredson.santos", SENHA_ADMIN)
        itens = self.client.get("/api/acesso/auditoria", headers=admin).json["items"]
        resultados = [i["resultado"].split(" ")[0] for i in itens if i["funcionalidade"] == "login"]
        self.assertIn("recusado", resultados)
        self.assertIn("entrou", resultados)


if __name__ == "__main__":
    unittest.main()
