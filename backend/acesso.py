"""Perfis e permissões (Configurações > Perfis e permissões).

- Administrador = a chave SIGP_API_KEY do .env: tudo, fixo, não editável (é a do dono do sistema e a do n8n).
- Usuários: cada um com chave própria (gerada aqui, mostrada uma vez; o banco guarda só o hash SHA-256),
  um grupo de permissões e ajustes individuais (permitir/negar uma funcionalidade).
- A regra vale na API: cada rota pertence a uma funcionalidade do catálogo abaixo. A tela só esconde abas.
- Pessoas entram com usuário e senha (backend/sessoes.py); chaves de API são só para integrações e a chave do .env.
- Sem login nem chave: nada além das rotas públicas (SIGP_EXIGIR_CHAVE_LEITURA=0 reabre a leitura, só para diagnóstico).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend import database

ADMIN = "administrador"

# Catálogo: área -> funcionalidades. Cada funcionalidade lista as rotas (método, regra do Flask) que ela libera
# e as abas da tela que dependem dela.
CATALOGO: List[Dict[str, Any]] = [
    {"area": "Cadastros", "funcionalidades": [
        {"id": "locais.ver", "nome": "Ver agências, rodoviárias e garagens (e a base de conhecimento delas)", "abas": ["agencias", "rv", "gr"],
         "rotas": [("GET", "/api/locais"), ("GET", "/api/locais/item/<local_id>"), ("GET", "/api/base-conhecimento"),
                   ("GET", "/api/base-conhecimento/qualidade"), ("GET", "/api/marcadores")]},
        {"id": "rede.ver", "nome": "Ver rede e IPs das unidades (dado sensível de infraestrutura)"},
        {"id": "locais.editar", "nome": "Criar e editar locais e provedores (inclui importar CSV)",
         "rotas": [("PUT", "/api/locais/<tipo>"), ("POST", "/api/locais/<tipo>/item"), ("GET", "/api/cadastro/correcoes"),
                   ("POST", "/api/cadastro/correcoes/unificar"), ("POST", "/api/cadastro/correcoes/vencimento"),
                   ("POST", "/api/cadastro/correcoes/desativar"), ("POST", "/api/marcadores"), ("PUT", "/api/marcadores/<marcador_id>"),
                   ("DELETE", "/api/marcadores/<marcador_id>"), ("POST", "/api/marcadores/previa")]},
    ]},
    {"area": "Notas recebidas (Gmail)", "funcionalidades": [
        {"id": "notas_recebidas.ver", "nome": "Ver a caixa de notas recebidas, PDFs e XMLs", "abas": ["notas-recebidas"],
         "rotas": [("GET", "/api/notas-recebidas"), ("GET", "/api/notas-recebidas/triagem"), ("GET", "/api/notas-recebidas/<item_id>/arquivo"),
                   ("GET", "/api/notas-recebidas/<item_id>/xml")]},
        {"id": "notas_recebidas.associar", "nome": "Validar e associar nota a um local; adicionar documento à mão (PDF/XML); reler PDF; vincular aviso",
         "rotas": [("POST", "/api/notas-recebidas/<item_id>/comparar"), ("PATCH", "/api/notas-recebidas/<item_id>/associar"),
                   ("POST", "/api/notas-recebidas/manual"),
                   ("POST", "/api/notas-recebidas/<item_id>/extrair"), ("POST", "/api/notas-recebidas/<item_id>/vincular-aviso")]},
        {"id": "notas_recebidas.triagem", "nome": "Descartar, restaurar, pôr em análise e revisar ignorados pela IA",
         "rotas": [("PATCH", "/api/notas-recebidas/<item_id>/descartar"), ("PATCH", "/api/notas-recebidas/<item_id>/restaurar"),
                   ("PATCH", "/api/notas-recebidas/<item_id>/analise"), ("PATCH", "/api/notas-recebidas/<item_id>/liberar"),
                   ("PATCH", "/api/notas-recebidas/<item_id>/resgatar"), ("POST", "/api/notas-recebidas/ignorados/confirmar")]},
        {"id": "notas_recebidas.importar", "nome": "Importar documentos do Gmail (uso do n8n)",
         "rotas": [("POST", "/api/notas-recebidas"), ("POST", "/api/notas-recebidas/aviso"), ("POST", "/api/notas-recebidas/classificar"),
                   ("POST", "/api/notas-recebidas/<item_id>/confirmar-etiqueta"), ("GET", "/api/llm/exemplos"),
                   ("GET", "/api/notas-recebidas/<item_id>/entrada-manual")]},
    ]},
    {"area": "Notas fiscais e pagamentos", "funcionalidades": [
        {"id": "notas.ver", "nome": "Ver notas lançadas, pagas, conciliações e correções", "abas": ["notas"],
         "rotas": [("GET", "/api/notas/lancadas"), ("GET", "/api/notas/pagas"), ("GET", "/api/notas/conciliacoes"),
                   ("GET", "/api/notas/lancadas/<nota_id>/correcoes"), ("GET", "/api/notas/pagas/<nota_id>/correcoes"),
                   ("GET", "/api/notas/lancadas/<nota_id>/xml"), ("GET", "/api/notas/lancadas/<nota_id>/fatura"),
                   ("GET", "/api/notas/lancadas/<nota_id>/fatura/arquivo")]},
        {"id": "notas.lancar", "nome": "Lançar e corrigir nota lançada",
         "rotas": [("POST", "/api/notas/lancadas"), ("PATCH", "/api/notas/lancadas/<nota_id>")]},
        {"id": "notas.pagar", "nome": "Registrar e corrigir pagamento (nota paga)",
         "rotas": [("POST", "/api/notas/pagas"), ("PATCH", "/api/notas/pagas/<nota_id>")]},
        {"id": "notas.conciliar", "nome": "Conciliar e reconciliar notas",
         "rotas": [("POST", "/api/notas/conciliar"), ("POST", "/api/notas/reconciliar")]},
        {"id": "notas.fatura", "nome": "Anexar ou remover a fatura PDF de uma nota",
         "rotas": [("POST", "/api/notas/lancadas/<nota_id>/fatura"), ("DELETE", "/api/notas/lancadas/<nota_id>/fatura")]},
    ]},
    {"area": "Faturas de provedores", "funcionalidades": [
        {"id": "faturas.ver", "nome": "Ver faturas, notas disponíveis (documentos do e-mail) e baixar PDFs e XMLs", "abas": ["faturas"],
         "rotas": [("GET", "/api/faturas"), ("GET", "/api/faturas/<fatura_id>/arquivo"), ("GET", "/api/faturas/<fatura_id>/xml"),
                   ("GET", "/api/notas-disponiveis")]},
        {"id": "faturas.editar", "nome": "Enviar, vincular e remover faturas; extrair texto do PDF",
         "rotas": [("POST", "/api/faturas"), ("DELETE", "/api/faturas/<fatura_id>"), ("POST", "/api/faturas/<fatura_id>/vincular"),
                   ("POST", "/api/extracao/texto")]},
    ]},
    {"area": "Gestão (SIG e SIE)", "funcionalidades": [
        {"id": "sig.ver", "nome": "Ver SIG, alertas, análises e o Dashboard", "abas": ["sig", "geral"],
         "rotas": [("GET", "/api/sig/resumo"), ("GET", "/api/sig/decisoes"), ("GET", "/api/alertas"), ("GET", "/api/analises")]},
        {"id": "sig.decidir", "nome": "Decidir no SIG (validar ciclo, pedir correção)", "rotas": [("POST", "/api/sig/decisoes")]},
        {"id": "sie.ver", "nome": "Ver o SIE (visão executiva)", "abas": ["sie"], "rotas": [("GET", "/api/sie/resumo")]},
        {"id": "analises.gravar", "nome": "Gravar análises da IA e eventos do SIE (uso do n8n)",
         "rotas": [("POST", "/api/analises"), ("POST", "/api/sie/webhook")]},
    ]},
    {"area": "Operação do dia a dia", "funcionalidades": [
        {"id": "os.usar", "nome": "Ordens de serviço", "abas": ["os"], "estado": ["sigp_os_v1", "sigp_os_contador_v1", "sigp_os_empresa_v1"]},
        {"id": "agenda_servicos.usar", "nome": "Agenda de serviços", "abas": ["agenda-servicos"], "estado": ["sigp_eventos_v1"]},
        {"id": "agenda_pessoal.usar", "nome": "Agenda pessoal", "abas": ["agenda-pessoal"], "estado": ["sigp_eventos_pessoal_v1"]},
        {"id": "sistemas.usar", "nome": "Sistemas de TI e referência de rede", "abas": ["sys"], "estado": ["ti_sistemas_v1", "ti_rederef_v1"]},
        {"id": "tela.basico", "nome": "Recados, histórico de atividades e lembrete de backup da tela",
         "estado": ["sigp_notes_v1", "sigp_activity_log_v1", "sigp_backup_history_v1"]},
    ]},
    {"area": "IA e banco de dados", "funcionalidades": [
        {"id": "ia.ver", "nome": "Ver o Painel da IA (métricas)", "abas": ["ia"], "rotas": [("GET", "/api/llm/metricas")]},
        {"id": "banco.ver", "nome": "Ver saúde do banco, integração e eventos",
         "rotas": [("GET", "/api/saude/banco"), ("GET", "/api/integracao/estado"), ("GET", "/api/eventos")]},
        {"id": "banco.manter", "nome": "Fazer backup, manutenção e reenviar eventos",
         "rotas": [("POST", "/api/saude/banco/backup"), ("POST", "/api/saude/banco/manutencao"), ("POST", "/api/eventos/reenviar")]},
    ]},
    {"area": "Assistente da IA", "funcionalidades": [
        {"id": "assistente.usar", "nome": "Conversar com o assistente da IA, avaliar respostas e baixar os relatórios dele",
         "abas": ["assistente"],
         "rotas": [("POST", "/api/assistente/perguntar"), ("POST", "/api/assistente/avaliar"), ("GET", "/api/assistente/historico"),
                   ("GET", "/api/assistente/relatorios/<rel_id>/<formato>"), ("GET", "/api/assistente/conhecimento"),
                   ("GET", "/api/assistente/conversas"), ("GET", "/api/assistente/conversas/<conversa_id>"),
                   ("PATCH", "/api/assistente/conversas/<conversa_id>"), ("DELETE", "/api/assistente/conversas/<conversa_id>")]},
        {"id": "assistente.ensinar", "nome": "Ensinar o assistente: termos novos, revisar respostas reprovadas e exportar o dataset de treino",
         "rotas": [("POST", "/api/assistente/termos"), ("GET", "/api/assistente/treinamento"), ("GET", "/api/assistente/dataset.jsonl")]},
    ]},
    {"area": "Configurações", "funcionalidades": [
        {"id": "config.alertas", "nome": "Ver e alterar os e-mails que recebem os alertas diários",
         "rotas": [("GET", "/api/configuracoes/alertas"), ("PUT", "/api/configuracoes/alertas")]},
        {"id": "config.email_faturas", "nome": "Ver e alterar os remetentes da busca de faturas no Gmail",
         "rotas": [("GET", "/api/configuracoes/email-faturas"), ("PUT", "/api/configuracoes/email-faturas")]},
        {"id": "config.cofre", "nome": "Gravar e apagar chaves de integração no cofre (o valor nunca é mostrado)",
         "rotas": [("GET", "/api/cofre"), ("PUT", "/api/cofre/<nome>"), ("DELETE", "/api/cofre/<nome>")]},
    ]},
]
# Leitura que sempre exige chave, mesmo com a leitura aberta (dados pessoais e administração).
LEITURA_PROTEGIDA = {"admin", "config.alertas", "config.email_faturas", "config.cofre"}
ROTAS_PUBLICAS = {("GET", "/api/health"), ("POST", "/api/auth/verify"), ("GET", "/api/acesso/eu"), ("GET", "/api/auth/estado"),
                  ("POST", "/api/auth/primeiro-admin"), ("POST", "/api/auth/login"), ("POST", "/api/auth/sair"),
                  ("POST", "/api/auth/trocar-senha")}
ESTADO_LEITURA = ("GET", "/api/app-state")
ESTADO_ESCRITA = {("PUT", "/api/app-state/<state_key>"), ("DELETE", "/api/app-state/<state_key>")}

FUNCIONALIDADES = {f["id"]: {**f, "area": a["area"]} for a in CATALOGO for f in a["funcionalidades"]}
TODAS = list(FUNCIONALIDADES)
# Módulos da instalação (SIGP_MODULOS no .env): "completo" (padrão, o sistema inteiro) ou "gestao" (pacote da entrega
# acadêmica: só o fluxo de gestão de contas de provedores: busca de notas, associação, IA, assistente e banco). Uma funcionalidade
# desligada some das abas, das permissões e do catálogo, e as rotas dela respondem 404 para todos, inclusive o administrador.
MODULOS_DESLIGADOS = {
    "completo": set(),
    # O assistente fica ligado: as respostas avaliadas (👍/👎) e os termos ensinados são o material de treino da IA.
    "gestao": {"sig.decidir", "sie.ver", "os.usar", "agenda_servicos.usar", "agenda_pessoal.usar", "sistemas.usar"},
}
# Abas escondidas sem desligar as rotas: os alertas de vencimento (GET /api/alertas, de sig.ver) e a gravação das análises
# (POST /api/analises) fazem parte do fluxo: o WF-06 e o selo "situação da conta" dos locais usam. Só os painéis somem.
ABAS_ESCONDIDAS = {"completo": set(), "gestao": {"sig", "geral"}}


def modulo() -> str:
    nome = os.environ.get("SIGP_MODULOS", "completo").strip().lower() or "completo"
    return nome if nome in MODULOS_DESLIGADOS else "completo"


def desligada(funcionalidade: Optional[str]) -> bool:
    return bool(funcionalidade) and funcionalidade in MODULOS_DESLIGADOS[modulo()]


def ativas(permissoes: List[str]) -> List[str]:
    return [p for p in permissoes if not desligada(p)]


def abas_da_instalacao() -> Optional[List[str]]:
    """Abas do administrador: todas (None) no sistema completo; só as dos módulos ligados nos outros."""
    return None if modulo() == "completo" else abas_permitidas(TODAS)
_ROTA_PARA = {(m, r): f["id"] for f in FUNCIONALIDADES.values() for m, r in f.get("rotas", [])}
_ESTADO_PARA = {k: f["id"] for f in FUNCIONALIDADES.values() for k in f.get("estado", [])}

_VER = [i for i in TODAS if i.endswith(".ver")]
GRUPO_ADMIN = "admin"  # perfil Administrador para pessoas (todas as permissões); não é um grupo editável
GRUPOS_PADRAO = [
    {"id": "grp-gerente", "nome": "Gerente", "descricao": "Tudo do operador, mais as decisões do SIG e a manutenção do banco.",
     "permissoes": [i for i in TODAS if i not in ("notas_recebidas.importar", "analises.gravar")]},
    {"id": "grp-operador", "nome": "Operador", "descricao": "Trabalha a caixa de notas, cadastros, notas, faturas e a operação do dia a dia.",
     "permissoes": _VER + ["locais.editar", "notas_recebidas.associar", "notas_recebidas.triagem", "notas.lancar", "notas.pagar",
                           "notas.conciliar", "notas.fatura", "faturas.editar", "os.usar", "agenda_servicos.usar", "agenda_pessoal.usar",
                           "sistemas.usar", "tela.basico", "assistente.usar"]},
    {"id": "grp-leitura", "nome": "Leitura", "descricao": "Só consulta: auditoria e demonstração. Não grava nada.",
     "permissoes": _VER + ["tela.basico", "assistente.usar"]},
    {"id": "grp-integracao", "nome": "Integração (n8n)", "descricao": "Para outro sistema ou automação gravar documentos e análises.",
     "permissoes": ["locais.ver", "notas_recebidas.ver", "notas_recebidas.importar", "notas.ver", "notas.lancar", "notas.pagar",
                    "sig.ver", "analises.gravar", "banco.ver", "banco.manter"]},
]


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def garantir_tabelas() -> None:
    conn = database.get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS acesso_grupos (
                id TEXT PRIMARY KEY, nome TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '',
                permissoes_json TEXT NOT NULL DEFAULT '[]', padrao INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS acesso_usuarios (
                id TEXT PRIMARY KEY, nome TEXT NOT NULL, grupo_id TEXT NOT NULL DEFAULT '',
                ajustes_json TEXT NOT NULL DEFAULT '{}', chave_hash TEXT NOT NULL UNIQUE, chave_prefixo TEXT NOT NULL DEFAULT '',
                ativo INTEGER NOT NULL DEFAULT 1, ultimo_uso TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS acesso_auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT, em TEXT NOT NULL, usuario TEXT NOT NULL, metodo TEXT NOT NULL,
                rota TEXT NOT NULL, funcionalidade TEXT NOT NULL DEFAULT '', resultado TEXT NOT NULL, status INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_acesso_auditoria_em ON acesso_auditoria(em DESC);
        """)
        agora = _agora()
        for g in GRUPOS_PADRAO:
            conn.execute(
                "INSERT OR IGNORE INTO acesso_grupos (id, nome, descricao, permissoes_json, padrao, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
                (g["id"], g["nome"], g["descricao"], json.dumps(g["permissoes"]), agora, agora),
            )
        conn.commit()
    finally:
        conn.close()
    from backend import sessoes  # import aqui: sessoes depende deste módulo
    sessoes.garantir_tabelas()


# ---------------------------------------------------------------- grupos
def _grupo(row) -> Dict[str, Any]:
    return {"id": row["id"], "nome": row["nome"], "descricao": row["descricao"], "padrao": bool(row["padrao"]),
            "permissoes": [p for p in json.loads(row["permissoes_json"] or "[]") if p in FUNCIONALIDADES]}


def listar_grupos() -> List[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        grupos = [_grupo(r) for r in conn.execute("SELECT * FROM acesso_grupos ORDER BY padrao DESC, nome")]
        uso = dict(conn.execute("SELECT grupo_id, COUNT(*) FROM acesso_usuarios GROUP BY grupo_id").fetchall())
    finally:
        conn.close()
    for g in grupos:
        g["usuarios"] = uso.get(g["id"], 0)
    return grupos


def _validar_permissoes(permissoes: Any) -> List[str]:
    if not isinstance(permissoes, list) or any(p not in FUNCIONALIDADES for p in permissoes):
        raise ValueError("Permissões inválidas: use os códigos do catálogo de funcionalidades.")
    return sorted(set(permissoes), key=TODAS.index)


def salvar_grupo(dados: Dict[str, Any], grupo_id: Optional[str] = None) -> Dict[str, Any]:
    nome = str(dados.get("nome") or "").strip()[:80]
    if not nome:
        raise ValueError("Informe o nome do grupo.")
    permissoes = _validar_permissoes(dados.get("permissoes") or [])
    descricao = str(dados.get("descricao") or "").strip()[:300]
    conn = database.get_connection()
    try:
        if grupo_id:
            if not conn.execute("SELECT 1 FROM acesso_grupos WHERE id = ?", (grupo_id,)).fetchone():
                raise LookupError("Grupo não encontrado.")
            conn.execute("UPDATE acesso_grupos SET nome = ?, descricao = ?, permissoes_json = ?, updated_at = ? WHERE id = ?",
                         (nome, descricao, json.dumps(permissoes), _agora(), grupo_id))
        else:
            grupo_id = f"grp-{secrets.token_hex(6)}"
            conn.execute("INSERT INTO acesso_grupos (id, nome, descricao, permissoes_json, padrao, created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
                         (grupo_id, nome, descricao, json.dumps(permissoes), _agora(), _agora()))
        conn.commit()
        return _grupo(conn.execute("SELECT * FROM acesso_grupos WHERE id = ?", (grupo_id,)).fetchone())
    finally:
        conn.close()


def excluir_grupo(grupo_id: str) -> None:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT padrao FROM acesso_grupos WHERE id = ?", (grupo_id,)).fetchone()
        if not row:
            raise LookupError("Grupo não encontrado.")
        if row["padrao"]:
            raise ValueError("Os grupos padrão não podem ser excluídos (podem ser ajustados).")
        if conn.execute("SELECT COUNT(*) FROM acesso_usuarios WHERE grupo_id = ?", (grupo_id,)).fetchone()[0]:
            raise ValueError("Há usuários neste grupo: mude o grupo deles antes de excluir.")
        conn.execute("DELETE FROM acesso_grupos WHERE id = ?", (grupo_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- usuários
def _usuario(row) -> Dict[str, Any]:
    chaves = row.keys()
    tipo = row["tipo"] if "tipo" in chaves else "integracao"
    return {"id": row["id"], "nome": row["nome"], "grupoId": row["grupo_id"], "ajustes": json.loads(row["ajustes_json"] or "{}"),
            "chavePrefixo": row["chave_prefixo"] if tipo == "integracao" else "", "ativo": bool(row["ativo"]),
            "ultimoUso": row["ultimo_uso"], "criadoEm": row["created_at"], "tipo": tipo,
            "usuario": row["usuario"] if "usuario" in chaves else "",
            "trocarSenha": bool(row["trocar_senha"]) if "trocar_senha" in chaves else False,
            "bloqueadoAte": row["bloqueado_ate"] if "bloqueado_ate" in chaves else ""}


def listar_usuarios() -> List[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        usuarios = [_usuario(r) for r in conn.execute("SELECT * FROM acesso_usuarios ORDER BY nome")]
    finally:
        conn.close()
    grupos = {g["id"]: g for g in listar_grupos()}
    for u in usuarios:
        if u["grupoId"] == GRUPO_ADMIN:
            u["permissoes"], u["grupoNome"] = list(TODAS), "Administrador"
            continue
        u["permissoes"] = efetivas(u, grupos.get(u["grupoId"]))
        u["grupoNome"] = (grupos.get(u["grupoId"]) or {}).get("nome", "—")
    return usuarios


def _validar_ajustes(ajustes: Any) -> Dict[str, bool]:
    if not isinstance(ajustes, dict):
        raise ValueError("Ajustes individuais inválidos.")
    limpos = {}
    for k, v in ajustes.items():
        if k not in FUNCIONALIDADES or not isinstance(v, bool):
            raise ValueError("Ajuste individual inválido: use o código da funcionalidade e permitir/negar.")
        limpos[k] = v
    return limpos


def nova_chave() -> str:
    return f"sigp_{secrets.token_urlsafe(24)}"


def criar_usuario(dados: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    nome = str(dados.get("nome") or "").strip()[:80]
    if not nome:
        raise ValueError("Informe o nome do usuário.")
    grupo_id = str(dados.get("grupoId") or "")
    ajustes = _validar_ajustes(dados.get("ajustes") or {})
    chave = nova_chave()
    conn = database.get_connection()
    try:
        if not conn.execute("SELECT 1 FROM acesso_grupos WHERE id = ?", (grupo_id,)).fetchone():
            raise ValueError("Escolha um grupo de permissões.")
        usuario_id = f"usr-{secrets.token_hex(6)}"
        conn.execute(
            "INSERT INTO acesso_usuarios (id, nome, grupo_id, ajustes_json, chave_hash, chave_prefixo, ativo, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (usuario_id, nome, grupo_id, json.dumps(ajustes), _hash(chave), chave[:9], _agora(), _agora()))
        conn.commit()
    finally:
        conn.close()
    return next(u for u in listar_usuarios() if u["id"] == usuario_id), chave


def atualizar_usuario(usuario_id: str, dados: Dict[str, Any]) -> Dict[str, Any]:
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM acesso_usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if not row:
            raise LookupError("Usuário não encontrado.")
        nome = str(dados.get("nome") if dados.get("nome") is not None else row["nome"]).strip()[:80] or row["nome"]
        grupo_id = str(dados.get("grupoId") or row["grupo_id"])
        pessoa = row["tipo"] == "pessoa"
        if grupo_id == GRUPO_ADMIN and not pessoa:
            raise ValueError("Só pessoas (com usuário e senha) podem ser administradoras; integrações usam um grupo.")
        if grupo_id != GRUPO_ADMIN and not conn.execute("SELECT 1 FROM acesso_grupos WHERE id = ?", (grupo_id,)).fetchone():
            raise ValueError("Grupo de permissões inválido.")
        ajustes = _validar_ajustes(dados["ajustes"]) if "ajustes" in dados else json.loads(row["ajustes_json"] or "{}")
        ativo = bool(dados["ativo"]) if "ativo" in dados else bool(row["ativo"])
        login = row["usuario"]
        if pessoa and dados.get("usuario") is not None and str(dados["usuario"]).strip().lower() != row["usuario"]:
            from backend import sessoes  # import aqui: sessoes depende deste módulo
            login = sessoes.validar_usuario(dados["usuario"])
            if conn.execute("SELECT 1 FROM acesso_usuarios WHERE usuario = ? AND id != ?", (login, usuario_id)).fetchone():
                raise ValueError("Já existe um usuário com esse nome de usuário.")
        era_admin = pessoa and row["grupo_id"] == GRUPO_ADMIN and row["ativo"]
        if era_admin and (grupo_id != GRUPO_ADMIN or not ativo):
            outros = conn.execute("SELECT COUNT(*) FROM acesso_usuarios WHERE tipo = 'pessoa' AND grupo_id = ? AND ativo = 1 AND id != ?",
                                  (GRUPO_ADMIN, usuario_id)).fetchone()[0]
            if not outros:
                raise ValueError("Este é o único administrador: crie outro administrador antes de mudar o perfil dele ou desativá-lo.")
        conn.execute("UPDATE acesso_usuarios SET nome = ?, grupo_id = ?, ajustes_json = ?, ativo = ?, usuario = ?, updated_at = ? WHERE id = ?",
                     (nome, grupo_id, json.dumps(ajustes), int(ativo), login, _agora(), usuario_id))
        if not ativo:
            conn.execute("DELETE FROM acesso_sessoes WHERE usuario_id = ?", (usuario_id,))
        conn.commit()
    finally:
        conn.close()
    return next(u for u in listar_usuarios() if u["id"] == usuario_id)


def trocar_chave(usuario_id: str) -> Tuple[Dict[str, Any], str]:
    chave = nova_chave()
    conn = database.get_connection()
    try:
        n = conn.execute("UPDATE acesso_usuarios SET chave_hash = ?, chave_prefixo = ?, updated_at = ? WHERE id = ? AND tipo != 'pessoa'",
                         (_hash(chave), chave[:9], _agora(), usuario_id)).rowcount
        conn.commit()
    finally:
        conn.close()
    if not n:
        raise LookupError("Integração não encontrada (pessoas entram com usuário e senha, sem chave).")
    return next(u for u in listar_usuarios() if u["id"] == usuario_id), chave


def efetivas(usuario: Dict[str, Any], grupo: Optional[Dict[str, Any]]) -> List[str]:
    base = set((grupo or {}).get("permissoes") or [])
    for perm, permitir in (usuario.get("ajustes") or {}).items():
        (base.add if permitir else base.discard)(perm)
    return [p for p in TODAS if p in base]


# ---------------------------------------------------------------- identificação e decisão
def identificar(chave: str, chave_admin: str) -> Optional[Dict[str, Any]]:
    """Quem é o dono desta chave: administrador, usuário ativo, ou None (chave inválida ou usuário inativo)."""
    import hmac
    if chave_admin and hmac.compare_digest(chave.encode(), chave_admin.encode()):
        return {"perfil": ADMIN, "nome": "Administrador", "id": ADMIN, "grupo": "Administrador", "permissoes": TODAS}
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT * FROM acesso_usuarios WHERE chave_hash = ? AND tipo != 'pessoa'", (_hash(chave),)).fetchone()
        if not row or not row["ativo"]:
            return None
        grupo_row = conn.execute("SELECT * FROM acesso_grupos WHERE id = ?", (row["grupo_id"],)).fetchone()
        # "Último uso" no máximo uma vez por minuto (não grava a cada requisição).
        if str(row["ultimo_uso"] or "")[:16] != _agora()[:16]:
            conn.execute("UPDATE acesso_usuarios SET ultimo_uso = ? WHERE id = ?", (_agora(), row["id"]))
            conn.commit()
    finally:
        conn.close()
    usuario = _usuario(row)
    grupo = _grupo(grupo_row) if grupo_row else None
    return {"perfil": "usuario", "nome": usuario["nome"], "id": usuario["id"], "grupo": (grupo or {}).get("nome", "—"),
            "permissoes": efetivas(usuario, grupo)}


def funcionalidade_da_rota(metodo: str, regra: str, state_key: str = "") -> Optional[str]:
    """Funcionalidade exigida pela rota. None = rota pública; "admin" = só o administrador."""
    if (metodo, regra) in ROTAS_PUBLICAS or metodo in ("OPTIONS", "HEAD"):
        return None
    if regra.startswith("/api/acesso/"):
        return "admin"
    if (metodo, regra) == ESTADO_LEITURA:
        return "tela.basico"
    if (metodo, regra) in ESTADO_ESCRITA:
        return _ESTADO_PARA.get(state_key, "admin")
    return _ROTA_PARA.get((metodo, regra), "admin")


def abas_permitidas(permissoes: List[str]) -> List[str]:
    abas = {"config"}
    for p in permissoes:
        if not desligada(p):
            abas.update(a for a in FUNCIONALIDADES[p].get("abas", []) if a not in ABAS_ESCONDIDAS[modulo()])
    return sorted(abas)


def registrar(usuario: str, metodo: str, rota: str, funcionalidade: str, resultado: str, status: int) -> None:
    try:
        conn = database.get_connection()
        try:
            conn.execute("INSERT INTO acesso_auditoria (em, usuario, metodo, rota, funcionalidade, resultado, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (_agora(), usuario[:80], metodo, rota[:200], funcionalidade or "", resultado, status))
            conn.execute("DELETE FROM acesso_auditoria WHERE id <= (SELECT MAX(id) - 5000 FROM acesso_auditoria)")
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 (auditoria nunca derruba a requisição)
        pass


def auditoria(limite: int = 200) -> List[Dict[str, Any]]:
    conn = database.get_connection()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM acesso_auditoria ORDER BY id DESC LIMIT ?", (limite,))]
    finally:
        conn.close()


def catalogo_publico() -> List[Dict[str, Any]]:
    return [{"area": a["area"], "funcionalidades": [
        {"id": f["id"], "nome": f["nome"], "abas": f.get("abas", []),
         "rotas": [f"{m} {r}" for m, r in f.get("rotas", [])] + [f"dados da tela: {k}" for k in f.get("estado", [])]}
        for f in a["funcionalidades"] if not desligada(f["id"])]} for a in CATALOGO
        if any(not desligada(f["id"]) for f in a["funcionalidades"])]
