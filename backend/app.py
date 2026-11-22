from __future__ import annotations

import hmac
import json
import urllib.request
import os
import re
import sqlite3
import shutil
import sys
import unicodedata
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from flask import Flask, g, jsonify, request, send_file
from werkzeug.utils import secure_filename

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import events
from backend.alerts import build_alerts
from backend.campos import (
    VALOR_PADRAO, aplicar_data_emissao, aplicar_padrao_identificacao, aplicar_prioridade_xml, eh_padrao, mesclar_identificacao,
    motivo_chave_invalida, motivo_numero_invalido,
)
from backend.provedores import competencia, marca_provedor, mesma_empresa
from backend import acesso, assistente, avisos_provedor, base_conhecimento, cofre, correcoes_cadastro, config_alertas, config_email_faturas, fatura_esperada, identificadores, marcadores, metricas_llm, notas_disponiveis, saude_banco, sessoes
from backend import database as _database
from backend.database import (
    aplicar_fatura_no_local, descartar_nota_recebida, registrar_feedback_extracao, restaurar_nota_recebida,
    colocar_em_analise, retirar_de_analise, resgatar_ignorado, resumo_triagem, casos_decididos, historico_remetente,
    listar_feedback, marcar_provedor_pago, vincular_aviso_nota_recebida, aprender_codigos_cliente,
    list_decisoes_gerente, registrar_decisao_gerente,
    LOCAL_TIPOS, DuplicateDocumentError, confirmar_etiqueta_nota_recebida,
    correct_document, create_local, delete_fatura_local, delete_fatura_provedor,
    get_fatura_local, get_fatura_provedor, get_local, get_nota_recebida,
    get_app_state, get_connection, get_nota_lancada, get_nota_paga, init_db, latest_fatura_for_nota, list_analises, list_conciliacoes,
    list_conciliacoes_da_nota, list_conciliacoes_da_paga, list_correcoes, list_eventos, list_faturas_locais,
    integrar_nota_recebida, list_notas_recebidas, get_nota_recebida_por_gmail, atualizar_extracao_nota_recebida,
    link_fatura_local, list_locais, list_nota_lancadas, list_nota_pagas, log_event, save_analise, save_conciliacao, save_fatura_local,
    save_app_state, save_fatura_provedor, save_nota_lancada, save_nota_paga, save_nota_recebida, sync_locais,
    delete_app_state,
)
from backend.dashboard import ELIGIBLE_PAYMENT_STATUSES, build_sig_summary, default_period
from backend.executive import build_sie_summary, validacao_por_nota
from backend.normalizer import normalize_nota
from backend.reconciliation import compare_reconciliation, payment_belongs_to_invoice

app = Flask(__name__)
MAX_FATURA_SIZE = 15 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_FATURA_SIZE + 64 * 1024
APP_STATE_KEYS = {
    "sigp_activity_log_v1",
    "sigp_notes_v1",
    "sigp_os_v1",
    "sigp_os_contador_v1",
    "sigp_os_empresa_v1",
    "sigp_eventos_v1",
    "sigp_eventos_pessoal_v1",
    "ti_sistemas_v1",
    "ti_rederef_v1",
    "sigp_backup_history_v1",
}
FATURAS_DIR = Path(__file__).resolve().parent / "data" / "faturas"
FATURAS_DIR.mkdir(parents=True, exist_ok=True)
NOTAS_RECEBIDAS_DIR = Path(__file__).resolve().parent / "data" / "notas_recebidas"
NOTAS_RECEBIDAS_DIR.mkdir(parents=True, exist_ok=True)
OCR_URL = os.environ.get("SIGP_OCR_URL", "http://ocr:5002/extract").strip()
OCR_TIMEOUT_SECONDS = 180
init_db()

# Configuração por variáveis de ambiente (ver README, seção "Configuração da API").
API_KEY = os.environ.get("SIGP_API_KEY", "").strip()
CORS_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get("SIGP_CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000").split(",")
    if origin.strip()
}
# MATCH completo exige lançada + paga + fatura conferida; sem fatura o status é AGUARDANDO_FATURA.
EXIGIR_FATURA = os.environ.get("SIGP_EXIGIR_FATURA", "1").strip().lower() not in {"0", "false", "nao", "não"}


def normalize_company_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", without_accents)


# Leitura sem login/chave: desligada por padrão desde o login no servidor (SIGP_EXIGIR_CHAVE_LEITURA=0 reabre, só para diagnóstico).
EXIGIR_CHAVE_LEITURA = os.environ.get("SIGP_EXIGIR_CHAVE_LEITURA", "1").strip() != "0"
# Com a senha temporária (ou trocada pelo administrador), só estas rotas funcionam até a pessoa definir a própria senha.
_ROTAS_TROCA_SENHA = {("POST", "/api/auth/trocar-senha"), ("POST", "/api/auth/sair"), ("GET", "/api/acesso/eu")}


@app.before_request
def require_api_key():
    """Perfis e permissões (backend/acesso.py). Chave do .env (SIGP_API_KEY) = administrador (tudo; é a do n8n).
    Chave de integração = permissões do grupo + ajustes individuais. Sem chave nem sessão: recusado (
    SIGP_EXIGIR_CHAVE_LEITURA=0 reabre a leitura, só diagnóstico). Sessão (Authorization: Bearer) = pessoa com login.
    Sem SIGP_API_KEY definida (desenvolvimento), nada é exigido."""
    if request.method == "OPTIONS" or not API_KEY or request.url_rule is None or not request.path.startswith("/api/"):
        return None
    regra = request.url_rule.rule
    funcionalidade = acesso.funcionalidade_da_rota(request.method, regra, (request.view_args or {}).get("state_key", ""))
    if acesso.desligada(funcionalidade):
        return jsonify({"ok": False, "error": f"Esta funcionalidade não faz parte desta instalação (SIGP_MODULOS={acesso.modulo()}).",
                        "modulo": acesso.modulo()}), 404
    token = _token_sessao()
    if token:
        # Pessoa com login (usuário e senha). Sessão inválida ou expirada: 401 (a tela volta para o login).
        quem = sessoes.identificar_sessao(token)
        if not quem:
            if funcionalidade is None:
                return None  # rota pública (login, estado): um token vencido no navegador não atrapalha
            return jsonify({"ok": False, "error": "Sessão expirada ou encerrada. Entre de novo.", "sessao": "expirada"}), 401
        g.acesso = quem
        g.acesso_funcionalidade = funcionalidade or ""
        if quem.get("trocarSenha") and (request.method, regra) not in _ROTAS_TROCA_SENHA:
            return jsonify({"ok": False, "error": "Troque a senha temporária antes de continuar.", "trocarSenha": True}), 403
        if funcionalidade is None or quem["perfil"] == acesso.ADMIN or funcionalidade in quem["permissoes"]:
            return None
        nome = "administrar perfis e permissões" if funcionalidade == "admin" else acesso.FUNCIONALIDADES[funcionalidade]["nome"].lower()
        acesso.registrar(quem["usuario"], request.method, regra, funcionalidade, "negado", 403)
        return jsonify({"ok": False, "error": f"Seu perfil ({quem['grupo']}) não tem permissão para {nome}.", "permissao": funcionalidade}), 403
    supplied = request.headers.get("X-API-Key", "")
    if not supplied:
        if funcionalidade is None or (request.method in ("GET", "HEAD") and not EXIGIR_CHAVE_LEITURA and funcionalidade not in acesso.LEITURA_PROTEGIDA):
            return None
        return jsonify({"ok": False, "error": "Chave de API ausente ou inválida (cabeçalho X-API-Key)."}), 401
    quem = acesso.identificar(supplied, API_KEY)
    if not quem and request.method in ("GET", "HEAD") and not EXIGIR_CHAVE_LEITURA and funcionalidade not in acesso.LEITURA_PROTEGIDA:
        # Leitura com chave inválida (ex.: chave antiga guardada no navegador) vale como "sem chave": a tela abre
        # e pede a chave nova. Gravação com chave inválida continua recusada.
        return None
    if not quem:
        acesso.registrar("chave inválida", request.method, regra, funcionalidade or "", "recusado", 401)
        return jsonify({"ok": False, "error": "Chave de API ausente ou inválida (cabeçalho X-API-Key)."}), 401
    g.acesso = quem
    g.acesso_funcionalidade = funcionalidade or ""
    if funcionalidade is None or quem["perfil"] == acesso.ADMIN or funcionalidade in quem["permissoes"]:
        return None
    nome = "administrar perfis e permissões" if funcionalidade == "admin" else acesso.FUNCIONALIDADES[funcionalidade]["nome"].lower()
    acesso.registrar(quem["nome"], request.method, regra, funcionalidade, "negado", 403)
    return jsonify({"ok": False, "error": f"Seu perfil ({quem['grupo']}) não tem permissão para {nome}.",
                    "permissao": funcionalidade}), 403


@app.after_request
def auditar_acesso(response):
    # Toda gravação com chave fica na auditoria (quem, o quê, quando, resultado); leituras não, pelo volume.
    quem = getattr(g, "acesso", None)
    if quem and request.method not in ("GET", "HEAD", "OPTIONS") and response.status_code != 403:
        acesso.registrar(quem["nome"], request.method, request.url_rule.rule if request.url_rule else request.path,
                         getattr(g, "acesso_funcionalidade", ""), "permitido" if response.status_code < 400 else "erro", response.status_code)
    return response


@app.after_request
def add_cors_headers(response):
    origin = (request.headers.get("Origin") or "").rstrip("/")
    if origin and ("*" in CORS_ORIGINS or origin in CORS_ORIGINS):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return response


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"ok": False, "error": "O PDF excede o limite de 15 MiB."}), 413


@app.get("/api/health")
def health():
    try:
        conn = get_connection()
        try:
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        app.logger.exception("Falha ao consultar SQLite no healthcheck.")
        return jsonify({
            "status": "error",
            "database": "sqlite",
            "service": "sigp-backend",
            "error": "SQLite indisponível.",
        }), 503

    return jsonify({
        "status": "ok",
        "database": "sqlite",
        "service": "sigp-backend",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "autenticacao": bool(API_KEY),
        "exigirFatura": EXIGIR_FATURA,
        "eventosN8n": bool(events.webhook_url()),
    })


def _autor(informado: Any, limite: int = 120) -> str:
    """Quem fez a ação: com login, o usuário da sessão (não dá para se passar por outro);
    para o n8n e integrações, o nome que eles informam."""
    quem = getattr(g, "acesso", None) or {}
    return str(quem.get("usuario") or informado or "").strip()[:limite]


def _token_sessao() -> str:
    cabecalho = request.headers.get("Authorization", "")
    return cabecalho[7:].strip() if cabecalho.lower().startswith("bearer ") else ""


def _ip() -> str:
    return (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",")[0].strip()[:45]


@app.get("/api/auth/estado")
def auth_estado_route():
    """Pública: diz à tela se já existe administrador (senão, mostra o primeiro acesso)."""
    return jsonify({"ok": True, "precisaPrimeiroAdmin": bool(API_KEY) and not sessoes.existe_administrador(),
                    "loginObrigatorio": bool(API_KEY)})


@app.post("/api/auth/primeiro-admin")
def auth_primeiro_admin_route():
    """Primeiro acesso: só funciona enquanto não há administrador, e exige a chave do .env (prova de que é o dono)."""
    payload = request.get_json(silent=True) or {}
    chave = str(payload.get("chave") or "")
    if not API_KEY or not hmac.compare_digest(chave.encode(), API_KEY.encode()):
        acesso.registrar("primeiro acesso", "POST", "/api/auth/primeiro-admin", "admin", "recusado", 401)
        return jsonify({"ok": False, "error": "Chave do servidor incorreta (SIGP_API_KEY do arquivo .env)."}), 401
    if sessoes.existe_administrador():
        return jsonify({"ok": False, "error": "O administrador já foi criado. Entre com usuário e senha."}), 409
    try:
        item, _ = sessoes.criar_pessoa(payload.get("nome") or "", payload.get("usuario"), sessoes.GRUPO_ADMIN,
                                       senha=payload.get("senha"), trocar=False)
    except ValueError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 400
    acesso.registrar(item["usuario"], "POST", "/api/auth/primeiro-admin", "admin", "administrador criado", 201)
    return jsonify({"ok": True, "item": item}), 201


@app.post("/api/auth/login")
def auth_login_route():
    payload = request.get_json(silent=True) or {}
    usuario = str(payload.get("usuario") or "")[:60]
    try:
        token, quem = sessoes.entrar(usuario, str(payload.get("senha") or ""))
    except sessoes.LoginRecusado as erro:
        acesso.registrar(usuario.strip().lower() or "(vazio)", "POST", "/api/auth/login", "login", f"recusado {_ip()}", 401)
        return jsonify({"ok": False, "error": str(erro)}), 401
    acesso.registrar(quem["usuario"], "POST", "/api/auth/login", "login", f"entrou {_ip()}", 200)
    return jsonify({"ok": True, "token": token, "expiraEm": quem["sessaoExpiraEm"], "trocarSenha": quem["trocarSenha"],
                    "perfil": quem["perfil"], "nome": quem["nome"], "usuario": quem["usuario"], "grupo": quem["grupo"]})


@app.post("/api/auth/sair")
def auth_sair_route():
    token = _token_sessao()
    if token:
        quem = sessoes.identificar_sessao(token)
        sessoes.sair(token)
        if quem:
            acesso.registrar(quem["usuario"], "POST", "/api/auth/sair", "login", "saiu", 200)
    return jsonify({"ok": True})


@app.post("/api/auth/trocar-senha")
def auth_trocar_senha_route():
    quem = getattr(g, "acesso", None) or {}
    if not quem.get("usuario"):
        return jsonify({"ok": False, "error": "Entre com usuário e senha para trocar a senha."}), 401
    payload = request.get_json(silent=True) or {}
    try:
        sessoes.trocar_senha(quem["id"], str(payload.get("senhaAtual") or ""), payload.get("novaSenha"), _token_sessao())
    except ValueError as erro:
        acesso.registrar(quem["usuario"], "POST", "/api/auth/trocar-senha", "login", "troca recusada", 400)
        return jsonify({"ok": False, "error": str(erro)}), 400
    acesso.registrar(quem["usuario"], "POST", "/api/auth/trocar-senha", "login", "senha trocada", 200)
    return jsonify({"ok": True})


@app.post("/api/auth/verify")
def verify_api_key():
    """Confere a chave informada na tela e devolve o perfil (administrador ou usuário)."""
    if not API_KEY:
        return jsonify({"ok": True, "perfil": acesso.ADMIN, "nome": "Administrador", "grupo": "Administrador"})
    quem = acesso.identificar(request.headers.get("X-API-Key", ""), API_KEY)
    if not quem:
        return jsonify({"ok": False, "error": "Chave de API ausente ou inválida (cabeçalho X-API-Key)."}), 401
    return jsonify({"ok": True, "perfil": quem["perfil"], "nome": quem["nome"], "grupo": quem["grupo"]})


@app.get("/api/acesso/eu")
def acesso_eu_route():
    """Quem está usando a tela: perfil, permissões e abas liberadas (a tela esconde o resto)."""
    chave = request.headers.get("X-API-Key", "")
    quem = getattr(g, "acesso", None) if _token_sessao() else None
    if not quem:
        quem = (acesso.identificar(chave, API_KEY) if chave else None) if API_KEY else \
            {"perfil": acesso.ADMIN, "nome": "Administrador", "grupo": "Administrador", "permissoes": acesso.TODAS}
    if not quem:
        return jsonify({"ok": True, "perfil": "anonimo", "nome": "", "grupo": "", "permissoes": [], "abas": None})
    return jsonify({"ok": True, **{k: quem[k] for k in ("perfil", "nome", "grupo")}, "permissoes": acesso.ativas(quem["permissoes"]),
                    "usuario": quem.get("usuario", ""), "trocarSenha": bool(quem.get("trocarSenha")), "modulo": acesso.modulo(),
                    "abas": acesso.abas_da_instalacao() if quem["perfil"] == acesso.ADMIN else acesso.abas_permitidas(quem["permissoes"])})


def _erro_acesso(erro: Exception):
    return jsonify({"ok": False, "error": str(erro)}), 404 if isinstance(erro, LookupError) else 400


@app.get("/api/acesso/catalogo")
def acesso_catalogo_route():
    return jsonify({"ok": True, "areas": acesso.catalogo_publico()})


@app.get("/api/acesso/grupos")
def acesso_grupos_route():
    return jsonify({"ok": True, "items": acesso.listar_grupos()})


@app.post("/api/acesso/grupos")
def acesso_criar_grupo_route():
    try:
        return jsonify({"ok": True, "item": acesso.salvar_grupo(request.get_json(silent=True) or {})}), 201
    except (ValueError, LookupError) as erro:
        return _erro_acesso(erro)


@app.put("/api/acesso/grupos/<grupo_id>")
def acesso_editar_grupo_route(grupo_id: str):
    try:
        return jsonify({"ok": True, "item": acesso.salvar_grupo(request.get_json(silent=True) or {}, grupo_id)})
    except (ValueError, LookupError) as erro:
        return _erro_acesso(erro)


@app.delete("/api/acesso/grupos/<grupo_id>")
def acesso_excluir_grupo_route(grupo_id: str):
    try:
        acesso.excluir_grupo(grupo_id)
        return jsonify({"ok": True})
    except (ValueError, LookupError) as erro:
        return _erro_acesso(erro)


@app.get("/api/acesso/usuarios")
def acesso_usuarios_route():
    return jsonify({"ok": True, "items": acesso.listar_usuarios()})


@app.post("/api/acesso/usuarios")
def acesso_criar_usuario_route():
    """Pessoa (tipo "pessoa"): nome, usuário e perfil; devolve a senha temporária uma única vez.
    Integração (tipo "integracao"): nome e grupo; devolve a chave de API uma única vez."""
    dados = request.get_json(silent=True) or {}
    try:
        if dados.get("tipo") == "pessoa":  # sem tipo: integração (compatível com quem já usa a API)
            usuario, senha = sessoes.criar_pessoa(dados.get("nome") or "", dados.get("usuario"), str(dados.get("grupoId") or ""),
                                                  dados.get("ajustes") or {})
            return jsonify({"ok": True, "item": usuario, "senhaTemporaria": senha}), 201
        usuario, chave = acesso.criar_usuario(dados)
        return jsonify({"ok": True, "item": usuario, "chave": chave}), 201
    except (ValueError, LookupError) as erro:
        return _erro_acesso(erro)


@app.post("/api/acesso/usuarios/<usuario_id>/redefinir-senha")
def acesso_redefinir_senha_route(usuario_id: str):
    try:
        usuario, senha = sessoes.redefinir_senha(usuario_id)
        return jsonify({"ok": True, "item": usuario, "senhaTemporaria": senha})
    except (ValueError, LookupError) as erro:
        return _erro_acesso(erro)


@app.put("/api/acesso/usuarios/<usuario_id>")
def acesso_editar_usuario_route(usuario_id: str):
    try:
        return jsonify({"ok": True, "item": acesso.atualizar_usuario(usuario_id, request.get_json(silent=True) or {})})
    except (ValueError, LookupError) as erro:
        return _erro_acesso(erro)


@app.post("/api/acesso/usuarios/<usuario_id>/nova-chave")
def acesso_nova_chave_route(usuario_id: str):
    try:
        usuario, chave = acesso.trocar_chave(usuario_id)
        return jsonify({"ok": True, "item": usuario, "chave": chave})
    except (ValueError, LookupError) as erro:
        return _erro_acesso(erro)


@app.get("/api/acesso/auditoria")
def acesso_auditoria_route():
    try:
        limite = min(max(int(request.args.get("limite") or 200), 1), 1000)
    except ValueError:
        limite = 200
    return jsonify({"ok": True, "items": acesso.auditoria(limite)})


@app.get("/api/notas/lancadas")
def get_notas_lancadas():
    return jsonify({"items": list_nota_lancadas()})


@app.get("/api/notas/pagas")
def get_notas_pagas():
    return jsonify({"items": list_nota_pagas()})


@app.get("/api/notas/conciliacoes")
def get_conciliacoes():
    return jsonify({"items": list_conciliacoes()})


@app.get("/api/sig/resumo")
def get_sig_summary():
    default_start, default_end = default_period()
    start_date = str(request.args.get("inicio") or default_start).strip()
    end_date = str(request.args.get("fim") or default_end).strip()
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Informe datas válidas no formato AAAA-MM-DD."}), 400
    if end < start:
        return jsonify({"ok": False, "error": "A data final deve ser igual ou posterior à data inicial."}), 400
    if (end - start).days > 1100:
        return jsonify({"ok": False, "error": "O período máximo do SIG é de 36 meses."}), 400

    result = build_sig_summary(
        list_nota_lancadas(),
        list_nota_pagas(),
        list_conciliacoes(),
        start.isoformat(),
        end.isoformat(),
        str(request.args.get("entidadeTipo") or "").strip(),
        str(request.args.get("provedor") or "").strip(),
        str(request.args.get("status") or "").strip(),
    )
    return jsonify({"ok": True, **result})


@app.get("/api/faturas")
def get_faturas_locais_route():
    entidade_tipo = str(request.args.get("entidadeTipo") or "").strip().lower()
    entidade_id = str(request.args.get("entidadeId") or "").strip()
    if entidade_tipo and entidade_tipo not in {"agencia", "rodoviaria", "garagem"}:
        return jsonify({"ok": False, "error": "Tipo de local inválido."}), 400
    return jsonify({"items": list_faturas_locais(entidade_tipo, entidade_id)})


@app.delete("/api/faturas/<fatura_id>")
def excluir_fatura_local(fatura_id: str):
    deleted = delete_fatura_local(fatura_id)
    if not deleted:
        return jsonify({"ok": False, "error": "Fatura não encontrada."}), 404

    reconciled = reconcile_note(deleted["nota_lancada_id"]) if deleted["nota_lancada_id"] else []
    try:
        (FATURAS_DIR / deleted["arquivo_storage"]).unlink(missing_ok=True)
    except OSError:
        log_event("fatura_local_excluida", {
            "faturaId": fatura_id,
            "notaLancadaId": deleted["nota_lancada_id"],
            "pdfExcluido": False,
        })
        return jsonify({
            "ok": False,
            "error": "A fatura foi removida e a conciliação atualizada, mas não foi possível excluir o PDF.",
        }), 500

    log_event("fatura_local_excluida", {
        "faturaId": fatura_id,
        "notaLancadaId": deleted["nota_lancada_id"],
        "pdfExcluido": True,
    })
    return jsonify({"ok": True, "conciliacoes": reconciled})


@app.post("/api/faturas/<fatura_id>/vincular")
def vincular_fatura_local(fatura_id: str):
    payload = request.get_json(silent=True) or {}
    nota_lancada_id = str(payload.get("notaLancadaId") or "").strip()
    descricao = str(payload.get("descricao") or "").strip()
    if not nota_lancada_id:
        return jsonify({"ok": False, "error": "Selecione a nota lançada para vincular."}), 400
    if not descricao:
        return jsonify({"ok": False, "error": "Informe e revise a descrição do serviço da fatura."}), 400
    if len(descricao) > 1000:
        return jsonify({"ok": False, "error": "A descrição do serviço excede 1000 caracteres."}), 400

    invoice = get_fatura_local(fatura_id)
    if not invoice:
        return jsonify({"ok": False, "error": "Fatura não encontrada."}), 404
    note = get_nota_lancada(nota_lancada_id)
    if not note:
        return jsonify({"ok": False, "error": "Nota lançada não encontrada."}), 404
    if (
        note.get("entidade_tipo") != invoice.get("entidade_tipo")
        or str(note.get("entidade_id") or "") != str(invoice.get("entidade_id") or "")
    ):
        return jsonify({"ok": False, "error": "A nota selecionada não pertence ao local da fatura."}), 400
    if invoice.get("nota_lancada_id") and invoice["nota_lancada_id"] != nota_lancada_id:
        return jsonify({"ok": False, "error": "A fatura já está vinculada a outra nota."}), 409

    data = invoice.get("dados") or {}
    issuer = str(data.get("emissorNome") or invoice.get("provedor_nome") or "").strip()
    expected_issuer = str(note.get("provedor_nome") or "").strip()
    normalized_issuer = normalize_company_name(issuer)
    normalized_expected_issuer = normalize_company_name(expected_issuer)
    issuer_match = bool(
        normalized_issuer
        and normalized_expected_issuer
        and (
            normalized_issuer in normalized_expected_issuer
            or normalized_expected_issuer in normalized_issuer
        )
    )
    try:
        amount = float(data.get("valorTotal") or 0)
        note_amount = float(note.get("valor_total") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "A fatura ou a nota contém um valor inválido."}), 400
    if not isfinite(amount) or amount < 0 or not isfinite(note_amount) or note_amount < 0:
        return jsonify({"ok": False, "error": "A fatura ou a nota contém um valor inválido."}), 400
    due_date = str(data.get("dataVencimento") or "").strip()
    note_due_date = str(note.get("data_vencimento") or "").strip()
    comparison = {
        "emissorConfere": issuer_match,
        "valorConfere": abs(note_amount - amount) < 0.01 if note_amount > 0 else None,
        "vencimentoConfere": due_date == note_due_date if note_due_date else None,
    }
    data["descricao"] = descricao
    data["comparacao"] = comparison
    data["statusComparacao"] = (
        "DIVERGENTE" if any(value is False for value in comparison.values())
        else "CONFERE" if all(value is True for value in comparison.values())
        else "SEM_REFERENCIA"
    )
    data["provedorEsperado"] = expected_issuer

    try:
        saved = link_fatura_local(fatura_id, nota_lancada_id, data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    if not saved:
        return jsonify({"ok": False, "error": "Fatura não encontrada."}), 404

    reconciled = reconcile_note(nota_lancada_id)
    log_event("fatura_local_vinculada_nota", {
        "faturaId": fatura_id,
        "notaLancadaId": nota_lancada_id,
        "comparacao": comparison,
    })
    return jsonify({
        "ok": True,
        "item": {
            "id": saved["id"],
            "notaLancadaId": saved["nota_lancada_id"],
            "dados": saved["dados"],
        },
        "conciliacoes": reconciled,
    })


def _atualizar_provedor_do_local(
    entidade_id: str, nome: str, valor: Any, data_vencimento: str, fatura_id: str = "", provedor_id: str = "",
) -> Dict[str, Any]:
    """Regra única (todos os fluxos): nota ou fatura associada ao local preenche o provedor de internet
    com nome, valor, data/dia de vencimento e fatura atual. Nunca derruba a gravação principal."""
    try:
        amount = float(valor)
    except (TypeError, ValueError):
        amount = 0.0
    nome = str(nome or "").strip()
    data_vencimento = str(data_vencimento or "").strip()[:10]
    if not entidade_id or not nome or not isfinite(amount) or amount <= 0 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_vencimento):
        return {"provedor": None, "acao": "ignorado", "aviso": ""}
    try:
        return aplicar_fatura_no_local(
            entidade_id, nome=nome, valor=amount, data_vencimento=data_vencimento,
            fatura_id=fatura_id, provedor_id=provedor_id,
        )
    except sqlite3.Error:
        app.logger.exception("Não foi possível atualizar o provedor do local %s.", entidade_id)
        return {"provedor": None, "acao": "erro", "aviso": "O provedor do local não foi atualizado."}


def _resposta_provedor(resultado: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "provedor": resultado.get("provedor"),
        "provedorAcao": resultado.get("acao"),
        "provedorAviso": resultado.get("aviso", ""),
    }


@app.post("/api/faturas")
def upload_fatura_local():
    entidade_tipo = str(request.form.get("entidadeTipo") or "").strip().lower()
    entidade_id = str(request.form.get("entidadeId") or "").strip()
    nota_lancada_id = str(request.form.get("notaLancadaId") or "").strip()
    provedor_id = str(request.form.get("provedorId") or "").strip()
    if entidade_tipo not in {"agencia", "rodoviaria", "garagem"} or not entidade_id:
        return jsonify({"ok": False, "error": "Selecione uma agência, rodoviária ou garagem cadastrada."}), 400

    nota = get_nota_lancada(nota_lancada_id) if nota_lancada_id else None
    if nota_lancada_id and not nota:
        return jsonify({"ok": False, "error": "A nota vinculada não foi encontrada."}), 404
    if nota and (nota.get("entidade_tipo") != entidade_tipo or nota.get("entidade_id") != entidade_id):
        return jsonify({"ok": False, "error": "A nota selecionada não pertence ao local escolhido."}), 400

    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify({"ok": False, "error": "Selecione o PDF da fatura."}), 400
    safe_name = secure_filename(Path(arquivo.filename).name)
    if not safe_name.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "O arquivo precisa ser PDF."}), 400
    arquivo.stream.seek(0, 2)
    file_size = arquivo.stream.tell()
    arquivo.stream.seek(0)
    if file_size > MAX_FATURA_SIZE:
        return jsonify({"ok": False, "error": "O PDF excede o limite de 15 MiB."}), 413
    if arquivo.stream.read(5) != b"%PDF-":
        return jsonify({"ok": False, "error": "O arquivo selecionado não é um PDF válido."}), 400
    arquivo.stream.seek(0)

    try:
        extracted = json.loads(request.form.get("dadosExtracao") or "{}")
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "Dados extraídos inválidos."}), 400
    if not isinstance(extracted, dict):
        return jsonify({"ok": False, "error": "Dados extraídos devem ser um objeto JSON."}), 400
    description = str(extracted.get("descricao") or "").strip()
    if len(description) > 1000:
        return jsonify({"ok": False, "error": "A descrição do serviço excede 1000 caracteres."}), 400
    if description:
        extracted["descricao"] = description
    issuer = str(extracted.get("emissorNome") or "").strip()
    due_date = str(extracted.get("dataVencimento") or "").strip()
    expected_issuer = str(request.form.get("provedorEsperado") or (nota or {}).get("provedor_nome") or "").strip()
    amount = extracted.get("valorTotal")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0
    if not issuer or not due_date or amount <= 0 or not isfinite(amount) or extracted.get("emissorConfirmado") is not True:
        return jsonify({
            "ok": False,
            "error": "Revise emissor, vencimento e valor da fatura antes de salvar.",
        }), 400
    try:
        datetime.strptime(due_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "error": "Informe um vencimento válido."}), 400
    issued_date = str(extracted.get("dataEmissao") or "").strip()
    if issued_date:
        try:
            datetime.strptime(issued_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"ok": False, "error": "Informe uma data de emissão válida."}), 400

    normalized_expected_issuer = normalize_company_name(expected_issuer)
    normalized_issuer = normalize_company_name(issuer)
    issuer_match = (
        bool(
            normalized_expected_issuer
            and normalized_issuer
            and (
                normalized_expected_issuer in normalized_issuer
                or normalized_issuer in normalized_expected_issuer
            )
        )
        if expected_issuer else None
    )
    expected_amount = float(nota.get("valor_total") or 0) if nota else 0
    expected_due_date = str(nota.get("data_vencimento") or "") if nota else ""
    comparison = {
        "emissorConfere": issuer_match,
        "valorConfere": abs(expected_amount - amount) < 0.01 if expected_amount > 0 else None,
        "vencimentoConfere": due_date == expected_due_date if expected_due_date else None,
    }
    extracted["comparacao"] = comparison
    extracted["statusComparacao"] = (
        "DIVERGENTE" if any(value is False for value in comparison.values())
        else "CONFERE" if all(value is True for value in comparison.values())
        else "SEM_REFERENCIA"
    )
    extracted["provedorEsperado"] = expected_issuer
    extracted["provedorId"] = provedor_id

    stored_name = f"{uuid4().hex}.pdf"
    storage_path = FATURAS_DIR / stored_name
    arquivo.save(storage_path)
    fatura_id = str(uuid4())
    try:
        saved = save_fatura_local(
            fatura_id, entidade_tipo, entidade_id, nota_lancada_id,
            safe_name, stored_name, extracted, provedor_id, expected_issuer,
        )
    except sqlite3.Error:
        storage_path.unlink(missing_ok=True)
        raise
    log_event("fatura_local_anexada", {
        "faturaId": fatura_id,
        "entidadeTipo": entidade_tipo,
        "entidadeId": entidade_id,
        "notaLancadaId": nota_lancada_id,
        "comparacao": comparison,
    })
    related_notes = [nota] if nota else [
        item for item in list_nota_lancadas()
        if item.get("entidade_tipo") == entidade_tipo
        and str(item.get("entidade_id") or "") == entidade_id
        and normalize_company_name(str(item.get("provedor_nome") or "")) == normalize_company_name(expected_issuer)
    ] if expected_issuer else []
    reconciled = [
        {"notaLancadaId": item["id"], "conciliacoes": reconcile_note(item["id"])}
        for item in related_notes
    ]
    provider_update = _atualizar_provedor_do_local(
        entidade_id, expected_issuer or issuer, amount, due_date, fatura_id, provedor_id,
    )
    return jsonify({
        "ok": True,
        **_resposta_provedor(provider_update),
        "conciliacoes": reconciled,
        "item": {
            "id": saved["id"],
            "entidadeTipo": saved["entidade_tipo"],
            "entidadeId": saved["entidade_id"],
            "provedorId": saved["provedor_id"],
            "provedorNome": saved["provedor_nome"],
            "notaLancadaId": saved["nota_lancada_id"],
            "nomeArquivo": saved["nome_arquivo"],
            "dados": saved["dados"],
            "createdAt": saved["created_at"],
            "downloadUrl": f"/api/faturas/{fatura_id}/arquivo",
        },
    })


@app.get("/api/faturas/<fatura_id>/arquivo")
def download_fatura_local(fatura_id: str):
    saved = get_fatura_local(fatura_id)
    if not saved:
        return jsonify({"ok": False, "error": "Fatura não encontrada."}), 404
    path = FATURAS_DIR / saved["arquivo_storage"]
    if not path.is_file():
        return jsonify({"ok": False, "error": "O arquivo da fatura não foi encontrado no armazenamento."}), 404
    return send_file(path, mimetype="application/pdf", as_attachment=True, download_name=saved["nome_arquivo"])


@app.post("/api/notas/lancadas/<nota_id>/fatura")
def upload_fatura_provedor(nota_id: str):
    nota = get_nota_lancada(nota_id)
    if not nota:
        return jsonify({"ok": False, "error": "Nota lançada não encontrada."}), 404

    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify({"ok": False, "error": "Selecione o PDF da fatura."}), 400
    safe_name = secure_filename(Path(arquivo.filename).name)
    if not safe_name.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "O arquivo precisa ser PDF."}), 400

    arquivo.stream.seek(0, 2)
    file_size = arquivo.stream.tell()
    arquivo.stream.seek(0)
    if file_size > MAX_FATURA_SIZE:
        return jsonify({"ok": False, "error": "O PDF excede o limite de 15 MiB."}), 413

    header = arquivo.stream.read(5)
    arquivo.stream.seek(0)
    if header != b"%PDF-":
        return jsonify({"ok": False, "error": "O arquivo selecionado não é um PDF válido."}), 400

    try:
        extracted = json.loads(request.form.get("dadosExtracao") or "{}")
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "Dados extraídos inválidos."}), 400
    if not isinstance(extracted, dict):
        return jsonify({"ok": False, "error": "Dados extraídos devem ser um objeto JSON."}), 400
    description = str(extracted.get("descricao") or "").strip()
    if len(description) > 1000:
        return jsonify({"ok": False, "error": "A descrição do serviço excede 1000 caracteres."}), 400
    if description:
        extracted["descricao"] = description

    issuer = str(extracted.get("emissorNome") or "").strip()
    due_date = str(extracted.get("dataVencimento") or "").strip()
    amount = extracted.get("valorTotal")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0
    if (
        not issuer
        or not due_date
        or amount <= 0
        or not isfinite(amount)
        or extracted.get("emissorConfirmado") is not True
    ):
        return jsonify({
            "ok": False,
            "error": "Confirme o emissor e revise o vencimento e o valor da fatura antes de salvar.",
        }), 400
    try:
        datetime.strptime(due_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "error": "Informe um vencimento válido."}), 400

    expected_issuer = normalize_company_name(str(nota.get("provedor_nome") or ""))
    normalized_issuer = normalize_company_name(issuer)
    issuer_match = bool(
        expected_issuer
        and normalized_issuer
        and (expected_issuer in normalized_issuer or normalized_issuer in expected_issuer)
    )
    if not issuer_match:
        return jsonify({
            "ok": False,
            "error": "O emissor não corresponde ao provedor cadastrado na nota. Revise o emissor ou atualize o cadastro antes de anexar.",
        }), 400
    expected_amount = float(nota.get("valor_total") or 0)
    expected_due_date = str(nota.get("data_vencimento") or "")
    extracted["comparacao"] = {
        "emissorConfere": issuer_match,
        "valorConfere": expected_amount > 0 and abs(expected_amount - amount) < 0.01,
        "vencimentoConfere": not expected_due_date or expected_due_date == due_date,
    }

    stored_name = f"{uuid4().hex}.pdf"
    storage_path = FATURAS_DIR / stored_name
    arquivo.save(storage_path)
    previous = get_fatura_provedor(nota_id)
    try:
        saved = save_fatura_provedor(nota_id, safe_name, stored_name, extracted)
    except sqlite3.Error:
        storage_path.unlink(missing_ok=True)
        raise
    if previous and previous.get("arquivo_storage") != stored_name:
        (FATURAS_DIR / previous["arquivo_storage"]).unlink(missing_ok=True)

    log_event("fatura_provedor_anexada", {
        "notaLancadaId": nota_id,
        "arquivo": safe_name,
        "comparacao": extracted["comparacao"],
    })
    reconcile_note(nota_id)
    provider_update = _atualizar_provedor_do_local(
        str(nota.get("entidade_id") or ""), nota.get("provedor_nome") or issuer, amount, due_date,
    )
    return jsonify({
        "ok": True,
        **_resposta_provedor(provider_update),
        "fatura": {
            "notaLancadaId": saved["nota_lancada_id"],
            "nomeArquivo": saved["nome_arquivo"],
            "dados": saved["dados_extracao"],
            "downloadUrl": f"/api/notas/lancadas/{nota_id}/fatura/arquivo",
            "vencimentoNota": due_date if not expected_due_date else expected_due_date,
        },
    })


@app.get("/api/notas/lancadas/<nota_id>/fatura")
def get_fatura_provedor_route(nota_id: str):
    saved = get_fatura_provedor(nota_id)
    if not saved:
        return jsonify({"ok": False, "error": "Nenhuma fatura anexada a esta nota."}), 404
    return jsonify({
        "ok": True,
        "fatura": {
            "notaLancadaId": saved["nota_lancada_id"],
            "nomeArquivo": saved["nome_arquivo"],
            "dados": saved["dados_extracao"],
            "downloadUrl": f"/api/notas/lancadas/{nota_id}/fatura/arquivo",
        },
    })


@app.delete("/api/notas/lancadas/<nota_id>/fatura")
def excluir_fatura_provedor(nota_id: str):
    deleted = delete_fatura_provedor(nota_id)
    if not deleted:
        return jsonify({"ok": False, "error": "Nenhuma fatura anexada a esta nota."}), 404

    reconciled = reconcile_note(nota_id)
    try:
        (FATURAS_DIR / deleted["arquivo_storage"]).unlink(missing_ok=True)
    except OSError:
        log_event("fatura_provedor_excluida", {
            "notaLancadaId": nota_id,
            "pdfExcluido": False,
        })
        return jsonify({
            "ok": False,
            "error": "A fatura foi removida e a conciliação atualizada, mas não foi possível excluir o PDF.",
        }), 500

    log_event("fatura_provedor_excluida", {
        "notaLancadaId": nota_id,
        "pdfExcluido": True,
    })
    return jsonify({"ok": True, "conciliacoes": reconciled})


@app.get("/api/notas/lancadas/<nota_id>/fatura/arquivo")
def download_fatura_provedor(nota_id: str):
    saved = get_fatura_provedor(nota_id)
    if not saved:
        return jsonify({"ok": False, "error": "Nenhuma fatura anexada a esta nota."}), 404
    path = FATURAS_DIR / saved["arquivo_storage"]
    if not path.is_file():
        return jsonify({"ok": False, "error": "O arquivo da fatura não foi encontrado no armazenamento."}), 404
    return send_file(path, mimetype="application/pdf", as_attachment=True, download_name=saved["nome_arquivo"])


@app.post("/api/sie/webhook")
def webhook_sie():
    payload = request.get_json(silent=True) or {}
    evento = str(payload.get("evento") or "").strip()
    if not evento:
        return jsonify({"ok": False, "error": "Campo 'evento' obrigatório."}), 400
    log_event(f"sie:{evento}", payload)
    return jsonify({"ok": True, "evento": evento, "recebido": True})


def _external_fields(payload: Dict[str, Any], nota: Dict[str, Any], raw: Any, source: str) -> None:
    """Campos do contrato v2: origem, sistemaOrigem e idExterno (raiz do payload ou dentro de dados/documento)."""
    nested = raw.get("documento") if isinstance(raw, dict) and isinstance(raw.get("documento"), dict) else raw
    nested = nested if isinstance(nested, dict) else {}
    nested_origin = str(nested.get("origem") or "").strip()
    nota["origem"] = payload.get("origem") or nested_origin or source
    nota["sistemaOrigem"] = str(payload.get("sistemaOrigem") or nested.get("sistemaOrigem") or "").strip()
    nota["idExterno"] = str(payload.get("idExterno") or nested.get("idExterno") or "").strip()


@app.post("/api/notas/lancadas")
def create_nota_lancada():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "O corpo deve ser um objeto JSON."}), 400
    source = str(payload.get("source") or payload.get("tipo") or "json").lower()
    raw = payload.get("dados") if "dados" in payload else payload
    try:
        nota = normalize_nota(raw, source)
    except Exception as exc:  # pragma: no cover - validation fallback
        return jsonify({"ok": False, "error": str(exc)}), 400

    if not str(nota.get("chave") or "").strip() and not str(nota.get("numero") or "").strip():
        # Regra do usuário: sem chave e número, vale o valor padrão; o provedor continua obrigatório.
        if not str(nota.get("provedorNome") or "").strip():
            return jsonify({"ok": False, "error": "Informe o provedor da nota (sem chave e número, ele identifica a cobrança)."}), 400
        nota["numero"] = VALOR_PADRAO
    nota["id"] = str(payload.get("id") or nota.get("chave") or f"lancada-{uuid4().hex}")
    if nota["id"].startswith("gmail-") or str(payload.get("origem") or "").lower() == "gmail":
        # Documento que chegou por e-mail é NOTA DISPONÍVEL (já está no local); nota lançada é só do financeiro.
        return jsonify({"ok": False, "codigo": "nota_disponivel",
                        "error": "Esta nota chegou por e-mail: é nota disponível, não nota lançada. Nota lançada vem do financeiro."}), 409
    nota["status"] = str(payload.get("status") or nota.get("status") or "PENDENTE").upper()
    nota["entidadeTipo"] = payload.get("entidadeTipo") or "agencia"
    nota["entidadeId"] = payload.get("entidadeId") or ""
    try:
        launched_total = float(nota.get("valor") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "O valor total da nota lançada é inválido."}), 400
    if not isfinite(launched_total) or launched_total <= 0:
        return jsonify({"ok": False, "error": "O valor total da nota lançada deve ser maior que zero."}), 400
    _external_fields(payload, nota, raw, source)
    nota["arquivoOrigem"] = payload.get("arquivoOrigem") or ""
    nota["createdAt"] = datetime.now(timezone.utc).isoformat()
    nota["updatedAt"] = datetime.now(timezone.utc).isoformat()

    try:
        saved = save_nota_lancada(nota)
    except DuplicateDocumentError as exc:
        return jsonify({"ok": False, "error": str(exc), "existingId": exc.existing_id}), 409
    log_event("nota_lancada", saved)
    # Liga à nota disponível (documentos do e-mail) do mesmo local/provedor/mês: a fatura entra na conciliação.
    disponivel_id = notas_disponiveis.vincular_lancada(saved)
    reconciled = reconcile_note(saved["id"])
    provider_update = _atualizar_provedor_do_local(
        str(saved.get("entidade_id") or ""), saved.get("provedor_nome"), saved.get("valor_total"),
        str(saved.get("data_vencimento") or ""),
    )
    return jsonify({"ok": True, "item": saved, "conciliacoes": reconciled, "notaDisponivelId": disponivel_id or "",
                    **_resposta_provedor(provider_update)})


@app.post("/api/notas/pagas")
def create_nota_paga():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "O corpo deve ser um objeto JSON."}), 400
    source = str(payload.get("source") or payload.get("tipo") or "json").lower()
    raw = payload.get("dados") if "dados" in payload else payload
    try:
        nota = normalize_nota(raw, source)
    except Exception as exc:  # pragma: no cover - validation fallback
        return jsonify({"ok": False, "error": str(exc)}), 400

    if not str(nota.get("chave") or "").strip() and not str(nota.get("numero") or "").strip():
        # Regra do usuário: sem chave e número, vale o valor padrão, desde que o pagamento seja identificável
        # pelo provedor ou pela nota lançada vinculada.
        if not str(nota.get("provedorNome") or "").strip() and not str(payload.get("notaLancadaId") or "").strip():
            return jsonify({"ok": False, "error": "Informe o provedor ou a nota lançada deste pagamento."}), 400
        nota["numero"] = VALOR_PADRAO
    nota["id"] = str(payload.get("id") or f"paga-{uuid4().hex}")
    try:
        paid_value = payload.get("valorPago")
        if paid_value in (None, ""):
            paid_value = payload.get("valor_pago")
        if paid_value in (None, ""):
            paid_value = nota.get("valor") or 0
        nota["valorPago"] = float(paid_value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Informe um valor pago válido."}), 400
    if nota["valorPago"] <= 0 or not isfinite(nota["valorPago"]):
        return jsonify({"ok": False, "error": "O valor pago deve ser maior que zero."}), 400
    if not isfinite(float(nota.get("valor") or 0)) or float(nota.get("valor") or 0) < 0:
        return jsonify({"ok": False, "error": "O valor total da nota paga é inválido."}), 400
    nota["dataPagamento"] = payload.get("dataPagamento") or payload.get("data_pagamento") or datetime.now(timezone.utc).date().isoformat()
    nota["status"] = (
        "PAGO_PARCIAL"
        if nota.get("valor") and nota["valorPago"] < float(nota["valor"]) - 0.01
        else str(payload.get("status") or "PAGA").upper()
    )
    if nota["status"] == "PAGA" and nota.get("dataVencimento") and nota["dataPagamento"] > nota["dataVencimento"]:
        nota["status"] = "PAGO_COM_ATRASO"
    nota["entidadeTipo"] = payload.get("entidadeTipo") or "agencia"
    nota["entidadeId"] = payload.get("entidadeId") or ""
    _external_fields(payload, nota, raw, source)
    nota["arquivoOrigem"] = payload.get("arquivoOrigem") or ""
    nota["createdAt"] = datetime.now(timezone.utc).isoformat()
    nota["updatedAt"] = datetime.now(timezone.utc).isoformat()

    try:
        saved = save_nota_paga({
            **nota,
            "valorTotal": nota.get("valor"),
            "valorPago": nota.get("valorPago"),
            "dataPagamento": nota.get("dataPagamento"),
        })
    except DuplicateDocumentError as exc:
        return jsonify({"ok": False, "error": str(exc), "existingId": exc.existing_id}), 409
    log_event("nota_paga", saved)

    # Conciliação automática: com notaLancadaId explícito ou, sem ele, quando só uma nota lançada corresponde.
    launched_id = str(payload.get("notaLancadaId") or "").strip()
    if launched_id and not get_nota_lancada(launched_id):
        return jsonify({"ok": True, "item": saved, "conciliacao": None,
                        "aviso": "Pagamento gravado, mas a nota lançada informada não existe."})
    if not launched_id:
        candidates = [n for n in list_nota_lancadas() if payment_belongs_to_invoice(n, saved)]
        if len(candidates) == 1:
            launched_id = candidates[0]["id"]
        else:
            aviso = (
                "Pagamento salvo; aguardando a importação da nota lançada correspondente."
                if not candidates
                else "Pagamento salvo; há mais de uma nota lançada correspondente e a associação exige revisão manual."
            )
            return jsonify({"ok": True, "item": saved, "conciliacao": None, "aviso": aviso})
    reconciliation = run_conciliation(get_nota_lancada(launched_id), saved) if launched_id else None
    return jsonify({"ok": True, "item": saved, "conciliacao": reconciliation})


def _total_paid(nota_lancada: Dict[str, Any]) -> float:
    return sum(
        float(item.get("valor_pago") or 0)
        for item in list_nota_pagas()
        if str(item.get("status") or "").upper() in ELIGIBLE_PAYMENT_STATUSES
        and payment_belongs_to_invoice(nota_lancada, item)
    )


def run_conciliation(nota_lancada: Dict[str, Any], nota_paga: Dict[str, Any]) -> Dict[str, Any]:
    """Concilia as notas e usa a fatura atual do provedor como referência principal."""
    previous = next(
        (row for row in list_conciliacoes_da_nota(nota_lancada["id"]) if row.get("nota_paga_id") == nota_paga["id"]),
        None,
    )
    fatura = latest_fatura_for_nota(nota_lancada["id"])
    invoice_data = (fatura or {}).get("dados") or {}
    try:
        invoice_amount = float(invoice_data.get("valorTotal")) if fatura else None
    except (TypeError, ValueError):
        invoice_amount = None
    comparison_result = compare_reconciliation(
        nota_lancada,
        nota_paga,
        _total_paid(nota_lancada),
        invoice_amount,
    )
    status = comparison_result["status"]
    observacao = comparison_result["observacao"]
    comparacao = dict(comparison_result["comparacao"])

    fatura_match = None
    if fatura:
        expected_provider = normalize_company_name(str(nota_lancada.get("provedor_nome") or ""))
        invoice_provider = normalize_company_name(str(
            invoice_data.get("provedorEsperado") or fatura.get("provedor_nome") or ""
        ))
        issuer = normalize_company_name(str(invoice_data.get("emissorNome") or ""))
        amount = invoice_amount or 0
        paid_total = float(comparison_result["valorPagoAcumulado"] or 0)
        due_date = str(invoice_data.get("dataVencimento") or "")[:10]
        note_due_date = str(nota_lancada.get("data_vencimento") or "")[:10]
        invoice_checks = (invoice_data.get("comparacao") or {}) if amount <= 0 else {
            "provedor": (
                expected_provider in invoice_provider or invoice_provider in expected_provider
            ) if expected_provider and invoice_provider else None,
            "emissor": (
                expected_provider in issuer or issuer in expected_provider
            ) if expected_provider and issuer else None,
            "notaLancada": abs(float(nota_lancada.get("valor_total") or 0) - amount) < 0.01,
            "pagamento": abs(paid_total - amount) < 0.01 if paid_total > 0 else None,
            "vencimento": due_date == note_due_date if due_date and note_due_date else None,
        }
        fatura_match = not any(value is False for value in invoice_checks.values())
        comparacao["faturaDetalhe"] = invoice_checks
    comparacao["fatura"] = fatura_match
    if fatura and fatura_match is False:
        status = "DIVERGENCIA"
        observacao = "A nota ou o pagamento diverge da fatura PDF atual do provedor."
    elif status == "MATCH" and EXIGIR_FATURA and not fatura:
        status = "AGUARDANDO_FATURA"
        observacao = "Nota lançada e pagamento conferem; aguardando a fatura PDF do provedor."

    result = save_conciliacao(nota_lancada, nota_paga, status, observacao, comparacao,
                              fatura_id=(fatura or {}).get("id", ""), fatura_match=fatura_match)
    log_event("conciliacao", result)
    if not previous or str(previous.get("status")) != status:
        events.emit("conciliacao_atualizada", {
            "status": status,
            "statusAnterior": (previous or {}).get("status"),
            "observacao": observacao,
            "comparacao": comparacao,
            "valorPagoAcumulado": comparison_result["valorPagoAcumulado"],
            "notaLancada": nota_lancada,
            "notaPaga": nota_paga,
            "fatura": fatura,
            "local": get_local(str(nota_lancada.get("entidade_id") or "")),
        })
    return {
        "ok": True,
        "resultado": result,
        "status": status,
        "comparacao": comparacao,
        "valorPagoAcumulado": comparison_result["valorPagoAcumulado"],
        "notaLancada": nota_lancada,
        "notaPaga": nota_paga,
        "fatura": fatura,
    }


def reconcile_note(nota_lancada_id: str) -> List[Dict[str, Any]]:
    """Atualiza conciliações existentes e associa pagamentos anteriores só quando a correspondência é única."""
    nota = get_nota_lancada(nota_lancada_id)
    if not nota:
        return []
    results = []
    reconciled_payment_ids = set()
    for row in list_conciliacoes_da_nota(nota_lancada_id):
        paga = get_nota_paga(str(row.get("nota_paga_id") or ""))
        if paga:
            results.append({"notaPagaId": paga["id"], "status": run_conciliation(nota, paga)["status"]})
            reconciled_payment_ids.add(paga["id"])

    launched_notes = list_nota_lancadas()
    for paga in list_nota_pagas():
        if paga["id"] in reconciled_payment_ids:
            continue
        candidates = [item for item in launched_notes if payment_belongs_to_invoice(item, paga)]
        if len(candidates) == 1 and candidates[0]["id"] == nota_lancada_id:
            results.append({"notaPagaId": paga["id"], "status": run_conciliation(nota, paga)["status"]})
    return results


@app.post("/api/notas/conciliar")
def conciliar_notas():
    payload = request.get_json(silent=True) or {}
    nota_lancada = get_nota_lancada(str(payload.get("notaLancadaId") or payload.get("nota_lancada_id") or ""))
    nota_paga = get_nota_paga(str(payload.get("notaPagaId") or payload.get("nota_paga_id") or ""))
    if not nota_lancada or not nota_paga:
        return jsonify({"ok": False, "error": "Informe IDs válidos de nota lançada e nota paga."}), 404
    return jsonify(run_conciliation(nota_lancada, nota_paga))


@app.post("/api/notas/reconciliar")
def reconciliar_todas():
    """Reaplica a regra atual (3 vias) a todas as conciliações existentes; útil após mudar a regra ou importar faturas."""
    results = [
        {"notaLancadaId": note["id"], "conciliacoes": reconcile_note(note["id"])}
        for note in list_nota_lancadas()
    ]
    return jsonify({"ok": True, "items": [item for item in results if item["conciliacoes"]]})


def _correct(table: str, document_id: str):
    payload = request.get_json(silent=True) or {}
    campos = payload.get("campos") if isinstance(payload.get("campos"), dict) else {}
    usuario = _autor(payload.get("usuario"))
    motivo = str(payload.get("motivo") or "").strip()
    if not campos:
        return jsonify({"ok": False, "error": "Informe os campos corrigidos em 'campos'."}), 400
    if not usuario or not motivo:
        return jsonify({"ok": False, "error": "Correção manual exige 'usuario' e 'motivo'."}), 400
    try:
        result = correct_document(table, document_id, campos, usuario, motivo)
    except KeyError:
        return jsonify({"ok": False, "error": "Documento não encontrado."}), 404
    except DuplicateDocumentError as exc:
        return jsonify({"ok": False, "error": str(exc), "existingId": exc.existing_id}), 409
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    log_event(f"correcao:{table}", {"id": document_id, "alterados": result["alterados"], "usuario": usuario, "motivo": motivo})
    if table == "notas_lancadas":
        reconciled = reconcile_note(document_id)
    else:
        reconciled = [
            {"notaLancadaId": row["nota_lancada_id"], "status": run_conciliation(get_nota_lancada(row["nota_lancada_id"]), result["item"])["status"]}
            for row in list_conciliacoes_da_paga(document_id) if get_nota_lancada(row["nota_lancada_id"])
        ]
    return jsonify({"ok": True, **result, "conciliacoes": reconciled})


@app.patch("/api/notas/lancadas/<nota_id>")
def patch_nota_lancada(nota_id: str):
    return _correct("notas_lancadas", nota_id)


@app.patch("/api/notas/pagas/<nota_id>")
def patch_nota_paga(nota_id: str):
    return _correct("notas_pagas", nota_id)


@app.get("/api/notas/lancadas/<nota_id>/correcoes")
def get_correcoes_lancada(nota_id: str):
    return jsonify({"items": list_correcoes("notas_lancadas", nota_id)})


@app.get("/api/notas/pagas/<nota_id>/correcoes")
def get_correcoes_paga(nota_id: str):
    return jsonify({"items": list_correcoes("notas_pagas", nota_id)})


def _serialize_nota_recebida_api(item: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(item)
    result["notaLancadaId"] = result.pop("nota_lancada_id", "")
    result["notaDisponivelId"] = result.pop("nota_disponivel_id", "")
    result["downloadUrl"] = f"/api/notas-recebidas/{item['id']}/arquivo"
    dados_item = item.get("dados") or {}
    # Leitura feita por regras antigas (ou sem versão): o cartão avisa e "Extrair dados do PDF" relê e grava.
    result["leituraDesatualizada"] = (
        item.get("status") in ("REVISAO", "AGUARDANDO_ASSOCIACAO", "EM_ANALISE")
        and not dados_item.get("semPdf")
        and int(dados_item.get("versaoRegras") or 0) < REGRAS_EXTRACAO_VERSAO
    )
    if ((item.get("dados") or {}).get("xmlArquivo") or {}).get("storage"):
        result["xmlUrl"] = f"/api/notas-recebidas/{item['id']}/xml"
    if item.get("entidade_id"):
        local = _locais_da_requisicao()["por_id"].get(str(item["entidade_id"])) or get_local(str(item["entidade_id"]))
        result["local"] = local
    elif item.get("dados"):
        data = item["dados"]
        company_name = str(
            data.get("empresaDestinataria") or data.get("destinatarioNome")
            or data.get("tomadorNome") or data.get("localNome") or ""
        ).strip()
        company_cnpj = re.sub(
            r"\D", "", str(
                data.get("cnpjDestinatario") or data.get("cnpjTomador")
                or data.get("cnpjLocal") or ""
            ),
        )
        normalized_name = normalize_company_name(company_name)
        candidates = []
        if normalized_name or company_cnpj:
            for local in _locais_da_requisicao()["ativos"]:
                details = local.get("dados") if isinstance(local.get("dados"), dict) else {}
                names = [
                    str(local.get("nome") or ""),
                    str(details.get("razaoSocial") or ""),
                    str(details.get("empresa") or ""),
                    str(details.get("nomeEmpresa") or ""),
                ]
                identifiers = [
                    re.sub(r"\D", "", str(value or ""))
                    for value in (details.get("cnpj"), details.get("cnpjEmpresa"), details.get("cnpjLocal"))
                ]
                name_match = bool(normalized_name and any(
                    normalize_company_name(name) == normalized_name for name in names if name
                ))
                cnpj_match = bool(company_cnpj and company_cnpj in identifiers)
                if name_match or cnpj_match:
                    candidates.append({
                        "id": local["id"],
                        "tipo": local["tipo"],
                        "nome": local["nome"],
                        "cidade": local["cidade"],
                        "motivo": "CNPJ" if cnpj_match else "Nome exato",
                    })
        # Situações 3 a 5: código do cliente/contrato já aprendido identifica o local (vem antes de tudo).
        codigos_nota = set(identificadores.codigos(data.get("identificadoresCliente")))
        por_codigo = []
        locais_do_provedor = set()
        emissor_nota = str(data.get("emissorNome") or "")
        for local in _locais_da_requisicao()["ativos"]:
            for prov in local.get("provedores") or []:
                if not isinstance(prov, dict):
                    continue
                if emissor_nota and mesma_empresa(prov.get("nome"), emissor_nota):
                    locais_do_provedor.add(local["id"])
                comuns = codigos_nota & set(identificadores.codigos_do_provedor(prov))
                if comuns and local["id"] not in {c["id"] for c in por_codigo}:
                    por_codigo.append({"id": local["id"], "tipo": local["tipo"], "nome": local["nome"], "cidade": local["cidade"],
                                       "motivo": f"Código do cliente/contrato {sorted(comuns)[0]} de {prov.get('nome')} cadastrado neste local"})
        candidates = por_codigo + [c for c in candidates if c["id"] not in {p["id"] for p in por_codigo}]
        if not por_codigo and len(locais_do_provedor) > 1:
            result["provedorEmVariosLocais"] = len(locais_do_provedor)
        # Notas recorrentes: o mesmo provedor (ou o mesmo remetente) já associado a um local sugere esse local.
        vistos = {candidate["id"] for candidate in candidates}
        for sugestao in _sugestoes_por_historico(str(data.get("emissorNome") or ""), str(item.get("remetente") or "")):
            if sugestao["id"] not in vistos:
                candidates.append(sugestao)
                vistos.add(sugestao["id"])
        result["sugestoesLocal"] = candidates
    return result


def _locais_da_requisicao() -> Dict[str, Any]:
    """Locais lidos uma vez por requisição (a lista de notas recebidas consultava o banco para cada nota)."""
    if "sigp_locais" not in g:
        todos = list_locais(incluir_inativos=True)
        g.sigp_locais = {"ativos": [l for l in todos if l.get("ativo", True)], "por_id": {str(l["id"]): l for l in todos}}
    return g.sigp_locais


def _disponiveis_para_historico() -> List[Dict[str, Any]]:
    try:
        return notas_disponiveis.listar()
    except sqlite3.Error:
        return []


def _indice_historico() -> Dict[str, Any]:
    """Provedores já vistos em cada local ativo (notas lançadas + provedores cadastrados), uma vez por requisição."""
    if "sigp_historico" in g:
        return g.sigp_historico
    locais = {str(local["id"]): local for local in _locais_da_requisicao()["ativos"]}
    # Histórico: notas lançadas do financeiro e notas disponíveis (documentos do e-mail já associados ao local).
    por_nota: list[tuple[str, str]] = [
        (str(note.get("provedor_nome") or ""), str(note.get("entidade_id") or ""))
        for note in [*list_nota_lancadas(), *_disponiveis_para_historico()] if str(note.get("entidade_id") or "") in locais
    ]
    g.sigp_historico = {"locais": locais, "notas": por_nota}
    return g.sigp_historico


def _sugestoes_por_historico(emissor: str, remetente: str) -> List[Dict[str, Any]]:
    indice = _indice_historico()
    contagem: Dict[str, int] = {}
    motivo: Dict[str, str] = {}
    if emissor.strip():
        for provedor, local_id in indice["notas"]:
            if mesma_empresa(provedor, emissor):
                contagem[local_id] = contagem.get(local_id, 0) + 1
                motivo[local_id] = f"Histórico: {contagem[local_id]} nota(s) de {provedor} neste local"
    endereco = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", remetente)
    email = endereco.group(0).lower() if endereco else ""
    for local_id, local in indice["locais"].items():
        for provedor in local.get("provedores") or []:
            if not isinstance(provedor, dict):
                continue
            cadastrados = [e.strip().lstrip("@").lower() for e in re.split(r"[,;\s]+", str(provedor.get("email") or "")) if e.strip()]
            por_email = bool(email and any(email == e or ("@" not in e and email.split("@")[-1].endswith(e)) for e in cadastrados))
            por_nome = bool(emissor.strip() and mesma_empresa(provedor.get("nome"), emissor))
            if (por_email or por_nome) and local_id not in contagem:
                contagem[local_id] = 0
                motivo[local_id] = f"Provedor {provedor.get('nome')} cadastrado neste local" + (" (e-mail do remetente)" if por_email else "")
    ordem = sorted(contagem, key=lambda local_id: -contagem[local_id])
    return [
        {"id": local_id, "tipo": indice["locais"][local_id]["tipo"], "nome": indice["locais"][local_id]["nome"],
         "cidade": indice["locais"][local_id]["cidade"], "motivo": motivo[local_id]}
        for local_id in ordem
    ]


def _compare_received_invoice(dados: Dict[str, Any], entidade_tipo: str, entidade_id: str) -> Dict[str, Any]:
    incoming_provider = normalize_company_name(str(dados.get("emissorNome") or ""))
    # O valor padrão (999999999) não identifica nota: conta como "sem chave/número" na comparação.
    incoming_key = "" if eh_padrao(dados.get("chave")) else re.sub(r"\W", "", str(dados.get("chave") or "").casefold())
    incoming_number = "" if eh_padrao(dados.get("numero")) else re.sub(r"\W", "", str(dados.get("numero") or "").casefold())
    incoming_due = str(dados.get("dataVencimento") or "")
    fields = (
        ("chave", "Chave", "chave"),
        ("numero", "Número", "numero"),
        ("serie", "Série", "serie"),
        ("provedor_nome", "Provedor", "emissorNome"),
        ("valor_total", "Valor", "valorTotal"),
        ("data_emissao", "Data de emissão", "dataEmissao"),
        ("data_vencimento", "Data de vencimento", "dataVencimento"),
        ("observacao", "Descrição", "descricaoServico"),
    )
    candidates = []
    other_provider_notes = []
    # Compara com as NOTAS DISPONÍVEIS do local (documentos já associados); nota lançada é só do financeiro.
    for existing in notas_disponiveis.listar(entidade_tipo, entidade_id):
        if existing.get("entidade_tipo") != entidade_tipo or str(existing.get("entidade_id")) != entidade_id:
            continue
        # Mesma empresa com nomes diferentes (ex.: "OPIX INTERNET" x "OPIX SERVICOS...") conta como o mesmo provedor.
        same_provider = bool(incoming_provider and mesma_empresa(existing.get("provedor_nome"), dados.get("emissorNome")))
        if same_provider:
            other_provider_notes.append(existing)
        existing_key = "" if eh_padrao(existing.get("chave")) else re.sub(r"\W", "", str(existing.get("chave") or "").casefold())
        existing_number = "" if eh_padrao(existing.get("numero")) else re.sub(r"\W", "", str(existing.get("numero") or "").casefold())
        same_key = bool(incoming_key and existing_key and incoming_key == existing_key)
        same_number = bool(
            incoming_number and existing_number and incoming_number == existing_number and same_provider
        )
        # Recorrência: mesmo mês de vencimento = mesma cobrança (atualiza a nota em vez de criar outra).
        same_period = bool(
            same_provider and incoming_due and competencia(existing.get("data_vencimento")) == competencia(incoming_due)
        )
        if not (same_key or same_number or same_period):
            continue

        differences = []
        for field, label, incoming_key_name in fields:
            old_value = existing.get(field)
            new_value = dados.get(incoming_key_name)
            if new_value in (None, ""):
                continue
            # Não são diferenças reais: número/chave padrão (não lido) e a mesma empresa com outro nome.
            if field in ("chave", "numero") and eh_padrao(new_value):
                continue
            if field == "provedor_nome" and mesma_empresa(old_value, new_value):
                continue
            if field == "valor_total":
                try:
                    same_value = abs(float(old_value or 0) - float(new_value)) < 0.005
                except (TypeError, ValueError):
                    same_value = False
            else:
                same_value = str(old_value or "").strip().casefold() == str(new_value).strip().casefold()
            if not same_value:
                differences.append({"campo": label, "atual": old_value, "recebida": new_value})

        candidates.append({
            "notaDisponivelId": existing["id"],
            "numero": existing.get("numero", ""),
            "chave": existing.get("chave", ""),
            "provedor": existing.get("provedor_nome", ""),
            "valorTotal": existing.get("valor_total"),
            "dataEmissao": existing.get("data_emissao", ""),
            "dataVencimento": existing.get("data_vencimento", ""),
            "descricaoServico": existing.get("observacao", ""),
            "faturaAnexada": bool(existing.get("fatura_anexada")),
            "diferencas": differences,
        })

    candidates.sort(key=lambda candidate: (candidate["dataVencimento"], candidate["notaDisponivelId"]), reverse=True)
    other_periods = [
        {
            "notaDisponivelId": note["id"],
            "numero": note.get("numero", ""),
            "valorTotal": note.get("valor_total"),
            "dataVencimento": note.get("data_vencimento", ""),
        }
        for note in other_provider_notes
        if all(candidate["notaDisponivelId"] != note["id"] for candidate in candidates)
    ]
    return {
        "candidatas": candidates,
        "outrasNotasMesmoProvedor": other_periods,
        "criaNovaNota": not candidates,
    }


@app.get("/api/notas-recebidas")
def get_notas_recebidas():
    status = str(request.args.get("status") or "").strip().upper()
    valid_statuses = {"AGUARDANDO_ASSOCIACAO", "ASSOCIADA", "REVISAO", "EM_ANALISE", "DESCARTADA", "IGNORADA_IA", "AVISO"}
    if status and status not in valid_statuses:
        return jsonify({"ok": False, "error": "Status de nota recebida inválido."}), 400
    items = list_notas_recebidas(
        status, request.args.get("etiquetaPendente") == "1", incluir_descartadas=False,
    )
    return jsonify({"items": [_serialize_nota_recebida_api(item) for item in items]})


@app.post("/api/notas-recebidas/<item_id>/comparar")
def comparar_nota_recebida_route(item_id: str):
    payload = request.get_json(silent=True) or {}
    entidade_tipo = str(payload.get("entidadeTipo") or "").strip().lower()
    entidade_id = str(payload.get("entidadeId") or "").strip()
    if entidade_tipo not in LOCAL_TIPOS or not entidade_id:
        return jsonify({"ok": False, "error": "Selecione uma agência, rodoviária ou garagem."}), 400
    local = get_local(entidade_id)
    if not local or local.get("tipo") != entidade_tipo or not local.get("ativo"):
        return jsonify({"ok": False, "error": "O local selecionado não existe, está inativo ou pertence a outro tipo."}), 404
    item = get_nota_recebida(item_id)
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    dados = dict(item.get("dados") or {})
    corrections = payload.get("dados") if isinstance(payload.get("dados"), dict) else {}
    allowed = {
        "emissorNome", "dataEmissao", "dataVencimento", "valorTotal", "chave",
        "numero", "serie", "descricaoServico",
    }
    dados.update({key: value for key, value in corrections.items() if key in allowed})
    if not str(dados.get("emissorNome") or "").strip():
        return jsonify({"ok": False, "error": "Revise e informe o emissor/provedor antes de comparar."}), 400
    return jsonify({
        "ok": True,
        "local": {"id": local["id"], "tipo": local["tipo"], "nome": local["nome"], "cidade": local["cidade"]},
        "comparacao": _compare_received_invoice(dados, entidade_tipo, entidade_id),
    })


@app.post("/api/notas-recebidas/classificar")
def classificar_documento_recebido_route():
    payload = request.get_json(silent=True) or {}
    text = " ".join(
        str(payload.get(key) or "")
        for key in ("texto", "assunto", "remetente", "nomeArquivo", "corpo")
    ).strip()
    if not text:
        return jsonify({"ok": False, "error": "Informe texto OCR ou metadados para classificar."}), 400
    if len(text) > 120_000:
        return jsonify({"ok": False, "error": "O texto para classificação excede 120000 caracteres."}), 413

    normalized_text = normalize_company_name(text)
    fiscal_terms = (
        "nota fiscal", "nfs-e", "nfse", "fatura", "conta de internet",
        "boleto", "cobranca", "valor total da nota", "documento fiscal",
    )
    internet_terms = (
        "servico de internet", "internet", "banda larga", "fibra optica", "link dedicado",
        "telecom", "comunicacao de dados", "provedor", "scm", "wi-fi", "wifi",
    )
    matched_fiscal = [term for term in fiscal_terms if normalize_company_name(term) in normalized_text]
    matched_internet = [term for term in internet_terms if normalize_company_name(term) in normalized_text]
    sender_match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", str(payload.get("remetente") or ""))
    sender_address = sender_match.group(0).lower() if sender_match else ""
    provider_names = set()
    provider_emails: Dict[str, str] = {}
    for location in list_locais():
        for provider in location.get("provedores", []):
            if isinstance(provider, str):
                name = provider.strip()
                emails = ""
            elif isinstance(provider, dict):
                name = str(provider.get("nome") or provider.get("provedorNome") or "").strip()
                emails = str(provider.get("email") or "")
            else:
                continue
            normalized_name = normalize_company_name(name)
            if normalized_name and len(normalized_name) >= 4:
                provider_names.add((normalized_name, name))
            # O campo e-mail do provedor aceita endereço completo ou domínio, separados por vírgula/ponto e vírgula.
            for email in re.split(r"[,;\s]+", emails.lower()):
                email = email.strip().lstrip("@")
                if email and name:
                    provider_emails[email] = name
    matched_providers = [
        name for normalized_name, name in sorted(provider_names)
        if normalized_name in normalized_text
    ]
    sender_domain = sender_address.split("@", 1)[1] if "@" in sender_address else ""
    providers_by_sender = sorted({
        name for email, name in provider_emails.items()
        if sender_address and (
            sender_address == email
            or ("@" not in email and (sender_domain == email or sender_domain.endswith("." + email)))
        )
    })
    for name in providers_by_sender:
        if name not in matched_providers:
            matched_providers.append(name)

    has_fiscal = bool(matched_fiscal)
    has_internet = bool(matched_internet)
    has_provider = bool(matched_providers)
    if providers_by_sender and has_fiscal:
        # Remetente cadastrado no provedor + termo fiscal: evidência forte, mesmo sem a palavra "internet".
        category = "NOTA_SERVICO_INTERNET" if any(
            term in {"nota fiscal", "nfs-e", "nfse", "documento fiscal"}
            for term in matched_fiscal
        ) else "FATURA_INTERNET"
        confidence = 0.95
    elif has_fiscal and has_internet:
        category = "NOTA_SERVICO_INTERNET" if any(
            term in {"nota fiscal", "nfs-e", "nfse", "documento fiscal"}
            for term in matched_fiscal
        ) else "FATURA_INTERNET"
        confidence = 0.95 if has_provider else 0.82
    elif has_fiscal:
        category = "DOCUMENTO_FISCAL_REVISAO"
        confidence = 0.58 if has_provider else 0.52
    elif has_internet or has_provider:
        category = "POSSIVEL_SERVICO_INTERNET_REVISAO"
        confidence = 0.48 if has_internet and has_provider else 0.38
    else:
        category = "REVISAO"
        confidence = 0.15

    return jsonify({
        "ok": True,
        "classificacao": {
            "categoria": category,
            "confianca": confidence,
            "revisaoManual": confidence < 0.75,
            "provedoresEncontrados": matched_providers,
            "provedoresPorRemetente": providers_by_sender,
            "palavrasFiscais": matched_fiscal,
            "palavrasInternet": matched_internet,
            "metodo": "regras_com_provedores_cadastrados_v1",
            # Histórico do remetente (3 confirmações de "não é cobrança" = descarte automático no WF-08).
            "remetente": historico_remetente(sender_address),
            # Situação 1: que tipo de e-mail é (fatura nova, 2ª via, lembrete, atraso, pagamento confirmado).
            "evento": avisos_provedor.detectar_evento(
                str(payload.get("assunto") or ""), str(payload.get("corpo") or ""), str(payload.get("texto") or ""),
            ),
        },
    })


def _provedores_do_remetente(remetente: str) -> tuple[list[str], list[str]]:
    """Provedores (nomes) e locais cujo cadastro tem o e-mail ou domínio deste remetente."""
    achado = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", str(remetente or ""))
    email = achado.group(0).lower() if achado else ""
    if not email:
        return [], []
    dominio = email.split("@", 1)[1]
    nomes, locais = [], []
    for local in list_locais():
        for provedor in local.get("provedores") or []:
            if not isinstance(provedor, dict):
                continue
            cadastrados = [e.strip().lstrip("@").lower() for e in re.split(r"[,;\s]+", str(provedor.get("email") or "")) if e.strip()]
            if any(email == e or ("@" not in e and (dominio == e or dominio.endswith("." + e))) for e in cadastrados):
                if provedor.get("nome") and provedor["nome"] not in nomes:
                    nomes.append(provedor["nome"])
                locais.append(str(local["id"]))
    return nomes, locais


def _saldo_nota(nota: Dict[str, Any]) -> float:
    return float(nota.get("valor_total") or 0) - _total_paid(nota)


def _processar_aviso(item: Dict[str, Any], corpo: str = "") -> Dict[str, Any]:
    """Situação 1: lembrete, aviso de atraso ou pagamento confirmado procura a cobrança já lançada do mesmo provedor.
    Uma candidata: vincula (status AVISO); no pagamento, registra o pagamento, concilia e marca o provedor como pago.
    Nenhuma ou várias: fica na caixa como Inconclusivo, com as candidatas. Nunca derruba a gravação principal."""
    dados = dict(item.get("dados") or {})
    evento = (dados.get("evento") or {}).get("tipo")
    if evento not in avisos_provedor.EVENTOS_AVISO or dados.get("aviso", {}).get("acao") in (
            "vinculado", "pagamento_registrado", "vinculado_disponivel", "pagamento_confirmado_provedor"):
        return item
    if item.get("status") not in ("AGUARDANDO_ASSOCIACAO", "REVISAO", "IGNORADA_IA"):
        return item
    try:
        nomes, locais = _provedores_do_remetente(str(item.get("remetente") or ""))
        codigos_aviso = set(identificadores.codigos(dados.get("identificadoresCliente")))
        if codigos_aviso:
            por_codigo = [str(l["id"]) for l in list_locais() for p in (l.get("provedores") or [])
                          if isinstance(p, dict) and codigos_aviso & set(identificadores.codigos_do_provedor(p))]
            if por_codigo:
                locais = por_codigo
        aviso = {**dados, "evento": evento, "recebidaEm": item.get("recebida_em") or item.get("created_at")}
        if not aviso.get("emissorNome") and nomes:
            aviso["emissorNome"] = nomes[0]
        cands = avisos_provedor.candidatas(aviso, list_nota_lancadas(), _saldo_nota, mesma_empresa, locais,
                                           nome_util=lambda nome: bool(marca_provedor(nome)))
        if not cands:
            # Sem nota lançada do financeiro: procura a NOTA DISPONÍVEL (documento do e-mail já associado ao local).
            # Pagamento confirmado aí só marca o provedor como pago (alertas); a nota paga continua sendo do financeiro.
            disp = [d for d in notas_disponiveis.listar() if not d.get("nota_lancada_id")]
            cands_d = avisos_provedor.candidatas(aviso, disp, lambda n: float(n.get("valor_total") or 0), mesma_empresa, locais,
                                                 nome_util=lambda nome: bool(marca_provedor(nome)))
            if len(cands_d) == 1:
                disponivel = cands_d[0]
                vencimento = str(disponivel.get("data_vencimento") or "")[:10]
                registro = {"evento": evento, "em": avisos_provedor.agora_iso(), "candidatas": [avisos_provedor.resumo_candidata(disponivel)],
                            "acao": "vinculado_disponivel", "notaDisponivelId": disponivel["id"]}
                if evento == "pagamento_confirmado":
                    pago_em = avisos_provedor.data_pagamento_no_texto(f"{corpo} {item.get('assunto') or ''}") \
                        or str(item.get("recebida_em") or "")[:10] or datetime.now(timezone.utc).date().isoformat()
                    marcar_provedor_pago(str(disponivel.get("entidade_id") or ""), str(disponivel.get("provedor_nome") or ""), vencimento or pago_em[:10])
                    registro.update({"acao": "pagamento_confirmado_provedor", "dataPagamento": pago_em[:10]})
                    log_event("pagamento_confirmado_provedor", {"notaRecebidaId": item["id"], "notaDisponivelId": disponivel["id"]})
                dados["aviso"] = registro
                triagem = dict(dados.get("triagem") or {})
                triagem["probabilidade"] = "alta"
                triagem["motivoProbabilidade"] = f"{avisos_provedor.ROTULOS[evento]} da nota disponível {disponivel.get('numero') or disponivel['id']}"
                dados["triagem"] = triagem
                return vincular_aviso_nota_recebida(
                    item["id"], dados, status="AVISO", entidade_tipo=str(disponivel.get("entidade_tipo") or ""),
                    entidade_id=str(disponivel.get("entidade_id") or ""), nota_lancada_id="",
                ) or item
            cands = cands_d
        registro = {"evento": evento, "em": avisos_provedor.agora_iso(), "candidatas": [avisos_provedor.resumo_candidata(c) for c in cands[:5]]}
        if len(cands) != 1:
            registro["acao"] = "sem_vinculo" if not cands else "varias_candidatas"
            dados["aviso"] = registro
            triagem = dict(dados.get("triagem") or {})
            triagem["probabilidade"] = "inconclusivo"
            triagem["motivoProbabilidade"] = (
                f"{avisos_provedor.ROTULOS[evento]}: não achei a cobrança deste provedor (nota lançada ou disponível)"
                if not cands else f"{avisos_provedor.ROTULOS[evento]}: {len(cands)} cobranças possíveis; escolha a certa"
            )
            dados["triagem"] = triagem
            return vincular_aviso_nota_recebida(item["id"], dados) or item
        nota = cands[0]
        registro.update({"acao": "vinculado", "notaLancadaId": nota["id"]})
        if evento == "pagamento_confirmado":
            saldo = round(_saldo_nota(nota), 2)
            vencimento = str(nota.get("data_vencimento") or "")[:10]
            pago_em = avisos_provedor.data_pagamento_no_texto(f"{corpo} {item.get('assunto') or ''}") \
                or str(item.get("recebida_em") or "")[:10] or datetime.now(timezone.utc).date().isoformat()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pago_em):
                pago_em = datetime.now(timezone.utc).date().isoformat()
            try:
                pagamento = save_nota_paga({
                    "id": f"paga-aviso-{item['id']}", "entidadeTipo": nota.get("entidade_tipo"), "entidadeId": nota.get("entidade_id"),
                    "chave": nota.get("chave"), "numero": nota.get("numero"), "serie": nota.get("serie"),
                    "provedorNome": nota.get("provedor_nome"), "localNome": nota.get("local_nome"), "localCidade": nota.get("local_cidade"),
                    "valorTotal": nota.get("valor_total"), "valorPago": saldo, "dataEmissao": nota.get("data_emissao"),
                    "dataPagamento": pago_em, "status": "PAGO_COM_ATRASO" if vencimento and pago_em > vencimento else "PAGA",
                    "origem": "aviso_provedor",
                    "observacao": f"Pagamento confirmado pelo provedor por e-mail: {str(item.get('assunto') or '')[:200]}",
                })
            except DuplicateDocumentError:
                registro["acao"] = "ja_pago"
            else:
                run_conciliation(nota, pagamento)
                marcar_provedor_pago(str(nota.get("entidade_id") or ""), str(nota.get("provedor_nome") or ""), vencimento or pago_em)
                registro.update({"acao": "pagamento_registrado", "pagamentoId": pagamento["id"], "valorPago": saldo, "dataPagamento": pago_em})
                log_event("pagamento_por_aviso", {"notaRecebidaId": item["id"], "notaLancadaId": nota["id"], "valor": saldo})
        dados["aviso"] = registro
        triagem = dict(dados.get("triagem") or {})
        triagem["probabilidade"] = "alta"
        triagem["motivoProbabilidade"] = f"{avisos_provedor.ROTULOS[evento]} da cobrança {nota.get('numero') or nota['id']}"
        dados["triagem"] = triagem
        return vincular_aviso_nota_recebida(
            item["id"], dados, status="AVISO", entidade_tipo=str(nota.get("entidade_tipo") or ""),
            entidade_id=str(nota.get("entidade_id") or ""), nota_lancada_id=str(nota["id"]),
        ) or item
    except (sqlite3.Error, ValueError, TypeError):
        app.logger.exception("Não foi possível vincular o aviso %s.", item.get("id"))
        return item


@app.post("/api/notas-recebidas/<item_id>/vincular-aviso")
def revincular_aviso_route(item_id: str):
    """Tenta de novo ligar um aviso (lembrete, atraso, pagamento) à cobrança, depois que ela foi lançada."""
    item = get_nota_recebida(item_id)
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    dados = dict(item.get("dados") or {})
    if (dados.get("evento") or {}).get("tipo") not in avisos_provedor.EVENTOS_AVISO:
        return jsonify({"ok": False, "error": "Este documento não é um aviso do provedor."}), 400
    dados.pop("aviso", None)
    item = vincular_aviso_nota_recebida(item_id, dados) or item
    item = _processar_aviso(item, corpo=str(dados.get("descricaoServico") or ""))
    return jsonify({"ok": True, "acao": ((item.get("dados") or {}).get("aviso") or {}).get("acao", ""),
                    "item": _serialize_nota_recebida_api(item)})


_VALOR_EMAIL = re.compile(r"R\$\s*([\d.]+,\d{2})")
_VENC_EMAIL = re.compile(r"venc\w*\s*(?:em|dia|:)?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)


@app.post("/api/notas-recebidas/aviso")
def registrar_aviso_sem_anexo():
    """E-mail do provedor sem PDF (situação 1): pagamento confirmado, atraso ou lembrete. Fatura nova sem anexo
    (link ou aplicativo) não entra: continua só com a etiqueta SIGp/Sem-anexo, para tratamento manual."""
    payload = request.get_json(silent=True) or {}
    message_id = str(payload.get("gmailMessageId") or "").strip()
    if not message_id or len(message_id) > 512:
        return jsonify({"ok": False, "error": "Informe o ID da mensagem do Gmail."}), 400
    assunto = str(payload.get("assunto") or "")[:500]
    corpo = str(payload.get("corpo") or "")[:5000]
    remetente = re.sub(r"\[object Object\]", "", str(payload.get("remetente") or "")).strip(" ,")[:500]
    evento = avisos_provedor.detectar_evento(assunto, corpo)
    if evento["tipo"] not in avisos_provedor.EVENTOS_AVISO:
        return jsonify({"ok": True, "acao": "nenhum", "evento": evento})
    nomes, _locais = _provedores_do_remetente(remetente)
    nome_remetente = re.sub(r"<[^>]*>|\"", "", remetente).strip()
    valor = _VALOR_EMAIL.search(corpo)
    venc = _VENC_EMAIL.search(corpo)
    dados = {
        "emissorNome": nomes[0] if nomes else nome_remetente[:300],
        "valorTotal": float(valor.group(1).replace(".", "").replace(",", ".")) if valor else None,
        "dataVencimento": avisos_provedor._data(venc.group(1)).isoformat() if venc and avisos_provedor._data(venc.group(1)) else "",
        "semArquivo": True, "evento": evento, "tipoDocumento": "lembrete",
        "descricaoServico": " ".join(corpo.split())[:300],
        "classificacao": {"categoria": "AVISO_PROVEDOR", "confianca": 0.9 if nomes else 0.6,
                          "provedoresPorRemetente": nomes, "metodo": "aviso_sem_anexo"},
        "triagem": {"decisao": "importar", "probabilidade": "inconclusivo", "motivoProbabilidade": avisos_provedor.ROTULOS[evento["tipo"]]},
        "revisaoManual": True,
    }
    item, created = save_nota_recebida(
        message_id=message_id, attachment_id="aviso", thread_id=str(payload.get("gmailThreadId") or "")[:512],
        assunto=assunto, remetente=remetente, recebida_em=str(payload.get("recebidaEm") or "")[:64],
        nome_arquivo="", arquivo_storage="", dados=dados,
    )
    item = _processar_aviso(item, corpo=corpo)
    acao = ((item.get("dados") or {}).get("aviso") or {}).get("acao", "")
    return jsonify({"ok": True, "acao": acao, "evento": evento, "item": _serialize_nota_recebida_api(item)}), 201 if created else 200


@app.post("/api/notas-recebidas")
def importar_nota_recebida():
    message_id = str(request.form.get("gmailMessageId") or "").strip()
    if not message_id or len(message_id) > 512:
        return jsonify({"ok": False, "error": "Informe o ID da mensagem do Gmail (máximo 512 caracteres)."}), 400
    attachment_id = str(request.form.get("gmailAttachmentId") or "").strip() or "default"
    if len(attachment_id) > 512:
        return jsonify({"ok": False, "error": "O ID do anexo Gmail excede 512 caracteres."}), 400
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify({"ok": False, "error": "A mensagem precisa conter um PDF."}), 400
    safe_name = secure_filename(Path(arquivo.filename).name)
    # Normal: a fatura PDF (+ o XML da nota em "xmlConteudo"). Mensagem só com XML: o XML vem em "arquivo",
    # entra em Revisão e só associa quando a fatura PDF chegar (os dois documentos são obrigatórios).
    so_xml = safe_name.lower().endswith(".xml")
    if not safe_name.lower().endswith(".pdf") and not so_xml:
        return jsonify({"ok": False, "error": "O anexo precisa ser PDF (ou o XML da nota fiscal)."}), 400
    arquivo.stream.seek(0, 2)
    file_size = arquivo.stream.tell()
    arquivo.stream.seek(0)
    if file_size > MAX_FATURA_SIZE:
        return jsonify({"ok": False, "error": "O PDF excede o limite de 15 MiB."}), 413
    if so_xml:
        xml_texto = arquivo.stream.read().decode("utf-8", errors="replace")
        xml_nome = safe_name
    else:
        if arquivo.stream.read(5) != b"%PDF-":
            return jsonify({"ok": False, "error": "O anexo não é um PDF válido."}), 400
        # XML da nota: como arquivo ("xml", chega byte a byte) ou como texto ("xmlConteudo", usado pelo WF-08).
        # Navegadores trocam LF por CRLF em campos de texto multipart; o arquivo preserva a assinatura do XML.
        xml_parte = request.files.get("xml")
        if xml_parte and xml_parte.filename:
            xml_texto = xml_parte.stream.read(2 * 1024 * 1024 + 1).decode("utf-8", errors="replace")
            xml_nome = secure_filename(Path(xml_parte.filename).name) or "nota-fiscal.xml"
        else:
            xml_texto = str(request.form.get("xmlConteudo") or "")
            xml_nome = secure_filename(str(request.form.get("xmlNomeArquivo") or "")) or "nota-fiscal.xml"
    arquivo.stream.seek(0)
    erro_xml = _validar_xml_nota(xml_texto) if xml_texto.strip() else ""
    if erro_xml:
        return jsonify({"ok": False, "error": erro_xml}), 400
    try:
        extracted = json.loads(request.form.get("dadosExtracao") or "{}")
    except json.JSONDecodeError:
        return jsonify({"ok": False, "error": "Dados extraídos inválidos."}), 400
    if not isinstance(extracted, dict):
        return jsonify({"ok": False, "error": "Dados extraídos devem ser um objeto JSON."}), 400
    if len(str(extracted.get("descricaoServico") or "")) > 1000:
        return jsonify({"ok": False, "error": "A descrição extraída excede 1000 caracteres."}), 400
    # Regras do usuário: chave/número vazios ou inválidos recebem o valor padrão; sem data de emissão
    # no documento, vale a data de recebimento (com a origem registrada).
    if extracted:
        aplicar_padrao_identificacao(extracted)
        aplicar_data_emissao(extracted, request.form.get("recebidaEm"))

    anterior = get_nota_recebida_por_gmail(message_id, attachment_id)
    xml_anterior = Path(str(((anterior or {}).get("dados") or {}).get("xmlArquivo", {}).get("storage") or "")).name
    storage_name = f"{uuid4().hex}.{'xml' if so_xml else 'pdf'}"
    storage_path = NOTAS_RECEBIDAS_DIR / storage_name
    arquivo.save(storage_path)
    xml_storage = ""
    if xml_texto.strip():
        if so_xml:
            xml_storage = storage_name
        else:
            xml_storage = f"{uuid4().hex}.xml"
            (NOTAS_RECEBIDAS_DIR / xml_storage).write_bytes(xml_texto.encode("utf-8"))  # sem converter quebras de linha
        extracted["xmlArquivo"] = {"storage": xml_storage, "nome": xml_nome[:255], "tamanho": len(xml_texto.encode("utf-8"))}
    if so_xml:
        extracted["semPdf"] = True
        extracted["revisaoManual"] = True
        revisar = list(extracted.get("camposParaRevisar") or [])
        if "faturaPdf" not in revisar:
            revisar.append("faturaPdf")
        extracted["camposParaRevisar"] = revisar
    try:
        item, created = save_nota_recebida(
            message_id=message_id,
            attachment_id=attachment_id,
            thread_id=str(request.form.get("gmailThreadId") or "")[:512],
            assunto=str(request.form.get("assunto") or "")[:500],
            # "[object Object]" = objeto do Gmail convertido em texto no n8n; melhor vazio que um valor falso.
            remetente=re.sub(r"\[object Object\]", "", str(request.form.get("remetente") or "")).strip(" ,")[:500],
            recebida_em=str(request.form.get("recebidaEm") or "")[:64],
            nome_arquivo=safe_name,
            arquivo_storage=storage_name,
            dados=extracted,
        )
    except sqlite3.Error:
        storage_path.unlink(missing_ok=True)
        if xml_storage and xml_storage != storage_name:
            (NOTAS_RECEBIDAS_DIR / xml_storage).unlink(missing_ok=True)
        raise
    if not created:
        # O PDF original é mantido; só a extração muda, e apenas enquanto não houver associação.
        storage_path.unlink(missing_ok=True)
        guardado = ((item.get("dados") or {}).get("xmlArquivo") or {}).get("storage")
        if xml_storage and xml_storage != storage_name and guardado != xml_storage:
            (NOTAS_RECEBIDAS_DIR / xml_storage).unlink(missing_ok=True)
        # Reprocessamento trocou o XML guardado: o anterior não é mais referenciado.
        if xml_anterior.endswith(".xml") and guardado != xml_anterior and xml_anterior != str(item.get("arquivo_storage") or ""):
            (NOTAS_RECEBIDAS_DIR / xml_anterior).unlink(missing_ok=True)
    else:
        log_event("nota_recebida_importada", {"notaRecebidaId": item["id"], "origem": "gmail"})
    atualizada = not created and item.get("dados") == extracted
    item = _processar_aviso(item, corpo=str(request.form.get("corpo") or ""))
    return jsonify({
        "ok": True,
        "duplicada": not created,
        "atualizada": atualizada,
        "item": _serialize_nota_recebida_api(item),
    }), 201 if created else 200


def _parse_ocr_date(value: str) -> str:
    """Converte string de data em qualquer formato brasileiro para ISO (AAAA-MM-DD)."""
    value = value.strip()
    # Aceita também datas com horário (ex.: "05/11/2026 16:14:47") — extrai só a data.
    value = re.split(r"\s+", value)[0]
    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def _coluna_de(text: str, label_pattern: str) -> str:
    """Layout de colunas de boleto: rótulo em uma linha, valor na próxima.
    Localiza o rótulo (label_pattern) e extrai o token alinhado na linha seguinte.
    Quando o rótulo é o último campo da linha, pega o último token (não o primeiro)
    para evitar capturar o token de uma coluna anterior."""
    lines = text.split("\n")
    for i in range(len(lines) - 1):
        m = re.search(label_pattern, lines[i], re.IGNORECASE)
        if not m:
            continue
        next_line = lines[i + 1]
        if not next_line.strip():
            continue
        col_start = m.start()
        col_end = m.end()
        rest_of_line = lines[i][col_end:].strip()
        # Rótulo é o último campo da linha: pega o último token da linha seguinte
        if len(rest_of_line) < 5:
            tokens = [t.strip() for t in re.split(r"\s{2,}", next_line.strip()) if t.strip()]
            if tokens:
                return tokens[-1]
        # Rótulo no meio da linha: janela alinhada à coluna
        window = next_line[max(0, col_start - 5): col_end + 50]
        tokens = [t.strip() for t in re.split(r"\s{2,}", window.lstrip()) if t.strip()]
        if tokens:
            return tokens[0]
    return ""


def _coluna_data(text: str, label_pattern: str) -> str:
    """Como _coluna_de, mas extrai somente a parte de data (dd/mm/aaaa) do valor,
    ignorando horário e outros textos que possam estar na mesma célula."""
    value = _coluna_de(text, label_pattern)
    m = re.search(r"\d{2}[/.\-]\d{2}[/.\-]\d{4}", value)
    return m.group(0) if m else value


def _ler_linha_digitavel(text: str):
    """Extrai valor e vencimento da linha digitável de boleto bancário (47 dígitos).
    Fator de vencimento >= 1000 usa a base Febraban: 22/02/2025 = fator 1000."""
    m = re.search(
        r"(\d{5}[.\s]?\d{5}\s+\d{5}[.\s]?\d{6}\s+\d{5}[.\s]?\d{6}\s+\d\s+\d{14})",
        text,
    )
    if not m:
        return None, None, ""
    digits = re.sub(r"\D", "", m.group(1))
    if len(digits) != 47:
        return None, None, ""
    fator = int(digits[33:37])
    valor = int(digits[37:]) / 100
    if fator >= 1000:
        from datetime import timedelta
        base = datetime(2025, 2, 22).date()
        venc = (base + timedelta(days=fator - 1000)).isoformat()
    else:
        venc = ""
    return digits, (round(valor, 2) if valor > 0 else None), venc


_EMPRESAS_DO_GRUPO = ("ROTA TRANSPORTE", "VIACAO JEQUIE", "EXPRESSO BRASILEIRO")  # pagadoras; nunca emissoras
_ROTULO_RE = re.compile(
    r"^(ag[eê]ncia|c[oó]digo|prestador|fornecedor|benefici[aá]rio|cedente|emitente|danfe\w*|nfs-?e|raz[aã]o social|"
    r"nome(\s*/\s*nome empresarial)?|cnpj|cpf|endere[cç]o|documento|n[º°o]\.?|s[eé]rie|data|vencimento|valor|tomador|"
    r"destinat[aá]rio|pagador|sacado|cliente|referente|fatura|nota fiscal|\(\+\)|\(=\)|\(-\))\b",
    re.I,
)
_EMPRESA_RE = re.compile(r"\b(ltda|ltd|s\s*/\s*a|s\.a\.?|eireli|me|epp|mei)\b\.?", re.I)


def _limpar_prefixo_emissor(valor: str) -> str:
    """Remove rótulos colados ao nome: "Razão Social: X", "PROVEDOR / PRESTADOR: X", "Emitente - X"."""
    texto = re.sub(r"^.*?\braz[aã]o\s+social\s*[:\-]\s*", "", str(valor or ""), flags=re.I).strip()
    return re.sub(
        r"^(?:(?:provedor|prestador(?:\s+de\s+servi[cç]os)?|emitente|benefici[aá]rio|cedente|fornecedor)\s*[/|]?\s*)+[:\-]\s*",
        "", texto, flags=re.I,
    ).strip()


def _parece_rotulo(valor: str) -> bool:
    texto = str(valor or "").strip()
    if not texto:
        return False
    if _ROTULO_RE.match(texto) and not _EMPRESA_RE.search(texto):
        return True
    return bool(re.fullmatch(r"[\d\s/.,:R$-]+", texto))  # só números/datas/valores


def _sem_acento_maiusculo(valor: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def _empresa_emissora_por_linha(text: str) -> str:
    """Nome da empresa emissora numa linha solta (DANFECom, NFS-e nacional, boleto com rótulos empilhados).

    Procura primeiro até 4 linhas depois de um rótulo de emissor; depois, a primeira linha com cara de
    razão social. Ignora tomador/destinatário/pagador e as empresas do grupo (sempre pagadoras).
    """
    linhas = [ln.strip() for ln in text.splitlines()]

    def candidato(linha: str) -> str:
        primeiro = re.split(r"\s{2,}|\s\|\s|\s/\s(?=CNPJ|CPF|RUA|AV)", linha, maxsplit=1)[0].strip(" -:|")
        primeiro = re.sub(r"\s+-\s+.*$", "", _limpar_prefixo_emissor(primeiro))  # "X LTDA - NOME FANTASIA"
        if not _EMPRESA_RE.search(primeiro) or len(primeiro) > 120 or _parece_rotulo(primeiro):
            return ""
        if any(empresa in _sem_acento_maiusculo(primeiro) for empresa in _EMPRESAS_DO_GRUPO):
            return ""
        return primeiro

    pagador = re.compile(r"tomador|destinat[aá]rio|pagador|sacado|cliente|contratante", re.I)
    emissor = re.compile(r"emitente|benefici[aá]rio|cedente|prestador|nome\s*/\s*nome empresarial", re.I)
    for i, linha in enumerate(linhas):
        if emissor.search(linha) and not pagador.search(linha):
            for proxima in linhas[i:i + 5]:
                if pagador.search(proxima):
                    break
                nome = candidato(proxima)
                if nome:
                    return nome
    bloqueio = 0
    for linha in linhas:
        if pagador.search(linha):
            bloqueio = 3  # a linha do pagador e as seguintes pertencem ao cliente
            continue
        if bloqueio:
            bloqueio -= 1
            continue
        nome = candidato(linha)
        if nome:
            return nome
    return ""


_ROTULO_ENCARGO_RE = re.compile(
    r"^(?:mora|multa|juros|outros\s+acr[eé]scimos|outras\s+dedu|desconto|abatimento|valor\s+(?:cobrado|documento))", re.I,
)
def _descricao_valida(valor: str) -> bool:
    """Descrição precisa ter uma palavra (4+ letras) e não ser um campo de data ("Ref. 10/10 até 09/11")."""
    return bool(re.search(r"[^\W\d_]{4,}", valor)) and not re.search(r":\s*\d{2}[/.]\d{2}[/.]\d{4}\s*$", valor) \
        and not _ROTULO_ENCARGO_RE.match(valor)


_CABECALHO_TABELA_RE = re.compile(r"descri[cç][aã]o|valor|qtde|quant|contrato|unit[aá]rio|\bitem\b", re.I)


def _descricao_abaixo_do_rotulo(text: str) -> str:
    """"Discriminação do serviço:" sozinho na linha: a descrição é a 1ª célula da linha de baixo (pula o cabeçalho)."""
    linhas = [ln.strip() for ln in text.splitlines()]
    for i, linha in enumerate(linhas):
        if not re.match(r"^(?:discrimina[cç][aã]o|descri[cç][aã]o)\s+(?:do|dos|de)\s+servi[cç]os?\s*:?$", linha, re.I):
            continue
        seguintes = [ln for ln in linhas[i + 1:i + 6] if ln]
        if seguintes and len(_CABECALHO_TABELA_RE.findall(seguintes[0])) >= 2:
            seguintes = seguintes[1:]
        if not seguintes:
            return ""
        celula = re.split(r"\s{2,}", seguintes[0])[0].strip()
        return celula[:1000] if _descricao_valida(celula) else ""
    return ""


def _descricao_por_marcador(text: str) -> str:
    """Boleto: "(+) Prestação de serviço..." (ignora encargos: mora, multa, juros...) ou "Referente ao ..."."""
    for linha in text.splitlines():
        for m in re.finditer(r"\(\+\)\s*(.+?)(?=\s{3,}|\s*\([+=\-]\)|$)", linha):
            trecho = re.sub(r"\s*R\$.*$", "", m.group(1)).strip().strip(" -:")
            if len(trecho) >= 3 and _descricao_valida(trecho):
                return trecho[:1000]
    for linha in text.splitlines():
        m = re.match(r"^\s*(?:referente\b(?:\s+(?:ao|aos|à|às|a))?|ref\.)\s*(.+?)(?=\s{3,}|$)", linha, re.I)
        if m and len(m.group(1).strip()) >= 5 and _descricao_valida(m.group(1).strip().strip(" -:.")):
            return m.group(1).strip().strip(" -:.")[:1000]
    return ""


# Versão das regras de extração (mesma de n8n/lib/extrator.js, VERSAO_REGRAS). Suba as duas juntas quando as
# regras mudarem: leituras com versão menor aparecem como desatualizadas e podem ser relidas sob demanda.
REGRAS_EXTRACAO_VERSAO = 2


def _dv_chave_ok(digitos: str) -> bool:
    """Dígito verificador da chave de 44 dígitos (NF-e, NFCom): módulo 11, pesos 2 a 9 da direita."""
    if len(digitos) != 44 or not digitos.isdigit():
        return False
    soma = sum(int(d) * (2 + i % 8) for i, d in enumerate(reversed(digitos[:43])))
    dv = 11 - soma % 11
    return (0 if dv >= 10 else dv) == int(digitos[43])


_ROTULOS_VALOR_COLUNA = (
    r"valor\s+total\s+da\s+nfs-?e", r"valor\s+l[ií]quido\s+da\s+nfs-?e", r"valor\s+total\s+da\s+nota",
    r"total\s+a\s+pagar", r"valor\s+a\s+pagar",
)


def _extract_invoice_fields(text: str) -> Dict[str, Any]:
    """Extrai campos de fatura/boleto a partir do texto OCR.

    Estratégia em camadas para lidar com dois layouts principais:
    - Inline (NFS-e, NFCom): rótulo e valor na mesma linha, separados por ':'
    - Coluna (boleto bancário): rótulo em uma linha, valor alinhado na linha seguinte
    """
    # Normalizar para busca linha-a-linha (preserva o original para busca de coluna)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    def labeled_value(pattern: str) -> str:
        """Busca inline: rótulo e valor na mesma linha."""
        match = re.search(pattern, joined, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip(" \t:;.-") if match else ""

    # --- Emissor ---
    # Inline: "Prestador:", "Razão social:", "Beneficiário:", "Cedente:", "Emitente:"
    issuer = labeled_value(
        r"^(?:prestador(?:\s+de\s+servi[cç]os)?|fornecedor|raz[aã]o social(?: do prestador)?|"
        r"nome do prestador|benefici[aá]rio|cedente|emitente)"
        r"\s*[:\-]\s*(.+)$"
    )
    # Fallback coluna: "Beneficiário" como cabeçalho
    if not issuer:
        issuer = _coluna_de(text, r"benefici[aá]rio|cedente|emitente")
    # "Razão Social: X" junto do nome; e rótulos capturados no lugar do nome ("Prestador", "DANFECom",
    # "Agência/Código beneficiário") são descartados e vão para a busca por linha de empresa.
    issuer = _limpar_prefixo_emissor(issuer)
    if _parece_rotulo(issuer):
        issuer = ""
    if not issuer:
        issuer = _empresa_emissora_por_linha(text)

    # --- Número do documento ---
    # Inline NFS-e / NFCom com separador ':'
    number = labeled_value(
        r"^(?:n[uú]mero\s+(?:da\s+)?(?:nota(?:\s+fiscal)?|nfs[\s-]?e)|"
        r"nota(?:\s+fiscal)?(?:\s+de\s+servi[cç]o)?|nfs[\s-]?e|"
        r"n[º°o]\.?\s*(?:do\s+)?documento|n[uú]mero\s+(?:da\s+)?(?:fatura|conta))"
        r"\s*(?:n[º°o.]*)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./-]{0,79})$"
    )
    # Inline curto: "Nº.: 16713" (DANFECom)
    if not number:
        m_curto = re.search(r"\bn[º°o][.:]+\s*(\d{3,20})\b", text, re.IGNORECASE)
        if m_curto:
            number = m_curto.group(1)
    # Fallback coluna: "Nº Documento" como cabeçalho. Também quando a leitura inline pegou o rótulo da
    # coluna vizinha ("Nº documento    Vencimento" → "Vencimento"); aí só troca por um número válido.
    if not number or motivo_numero_invalido(number):
        candidate = _coluna_de(text, r"n[º°o]\.?\s*documento")
        cnpj_re = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")
        if candidate and not cnpj_re.match(candidate) and (not number or not motivo_numero_invalido(candidate)):
            number = candidate
    # Herdado do WF-08: "Nº Documento: 77001    Vencimento: ..." no meio da linha (exige ":", "#" ou "-").
    if not number or motivo_numero_invalido(number):
        m_meio = re.search(
            r"(?:n[º°o]\.?\s*(?:do\s+)?documento|n[uú]mero\s+(?:da\s+)?(?:nota(?:\s+fiscal)?|nfs-?e))"
            r"\s*[:#\-]\s*([A-Z0-9][A-Z0-9./-]{2,40})",
            text, re.IGNORECASE,
        )
        if m_meio and not motivo_numero_invalido(m_meio.group(1)):
            number = m_meio.group(1)
    # "NOTA FISCAL Nº 16210 - SÉRIE: 1" no meio da linha (DANFE-COM).
    if not number or motivo_numero_invalido(number):
        m_nf = re.search(r"nota\s+fiscal\s+n[º°o]\.?\s*[:#\-]?\s*(\d{1,20})(?!\d)", text, re.IGNORECASE)
        if m_nf and not motivo_numero_invalido(m_nf.group(1)):
            number = m_nf.group(1)
    # Herdado do WF-03: "Número da fatura/conta X" ou "Fatura nº X" em qualquer posição da linha.
    if not number or motivo_numero_invalido(number):
        m_qualquer = re.search(
            r"(?:n[uú]mero|n[uú]m\.?|n[º°o]\.?)\s*(?:da\s+)?(?:fatura|conta)\s*[:#º°\-]?\s*([A-Z0-9][A-Z0-9./-]{0,29})"
            r"|(?:fatura|conta)\s*(?:n[uú]mero|n[uú]m\.?|n[º°o]\.?)\s*[:#º°\-]?\s*([A-Z0-9][A-Z0-9./-]{0,29})",
            text, re.IGNORECASE,
        )
        achado = (m_qualquer.group(1) or m_qualquer.group(2)) if m_qualquer else ""
        if achado and not motivo_numero_invalido(achado):
            number = achado

    # --- Chave de acesso ---
    access_key = labeled_value(
        r"^(?:chave\s+de\s+acesso|chave\s+da\s+nota)\s*[:#\-]\s*([A-Z0-9 .-]{20,160})$"
    )
    access_key = re.sub(r"\s+", "", access_key)
    # Chave na linha de baixo ("CHAVE DE ACESSO DA NFS-e" + 50 dígitos). Só aceita 44 ou 50 dígitos exatos.
    if motivo_chave_invalida(access_key):
        m_chave = re.search(
            r"chave\s+de\s+acesso(?:\s+d[ao]\s+(?:nfs-?e|nf-?e|nfcom|nota(?:\s+fiscal)?))?[^\d\n]{0,40}\n?[ \t]*(\d[\d .]{42,68}\d)",
            text, re.IGNORECASE,
        )
        digitos = re.sub(r"\D", "", m_chave.group(1)) if m_chave else ""
        if len(digitos) in (44, 50):
            access_key = digitos
    # Chave de 44 dígitos em grupos de 4 ("2926 1000 ... 5990"), em qualquer coluna, só se o texto fala em
    # chave de acesso e o dígito verificador (módulo 11, NF-e/NFCom) confere.
    if motivo_chave_invalida(access_key) and re.search(r"chave\s+de\s+acesso", text, re.IGNORECASE):
        for m_grupos in re.finditer(r"(?<!\d)\d{4}(?: \d{4}){10}(?!\d)", text):
            digitos = m_grupos.group(0).replace(" ", "")
            if _dv_chave_ok(digitos):
                access_key = digitos
                break

    # --- Série ---
    series = labeled_value(r"^(?:s[eé]rie)\s*[:#\-]\s*([A-Z0-9./-]{1,80})$")

    # --- Descrição do serviço ---
    # Só a mesma linha do rótulo ([ \t], não \s): antes o \s atravessava a quebra e pegava a linha seguinte.
    description = labeled_value(
        r"^(?:discrimina[cç][aã]o|descri[cç][aã]o)[ \t]+(?:do|dos)?[ \t]*servi[cç]os?[ \t]*[:\-][ \t]*(.+)$"
    )[:1000]
    if not description:
        description = _descricao_abaixo_do_rotulo(text)
    if not description:
        description = _descricao_por_marcador(text)

    # --- Data de emissão ---
    # Inline: "Data de emissão:", "Emissão:", "Emitida em:"
    # Rótulos aceitos para a emissão: emissão, emitido/emitida em, data da fatura/nota/conta,
    # data do documento, data de processamento.
    issue_date_raw = labeled_value(
        r"^(?:data\s+de\s+emiss[aã]o(?:\s+d[aeo]\s+(?:fatura|nota|conta|documento))?|emiss[aã]o|emitid[ao]\s+em|"
        r"data\s+d[aeo]\s+(?:fatura|nota(?:\s+fiscal)?|conta|documento)|data\s+d[eo]\s+processamento)"
        r"\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/.]\d{2}[/.]\d{4})(?:\s.*)?$"
    )
    # Fallback coluna: "Data do documento", "Data da fatura" ou "DATA EMISSÃO" (NFCom/boleto)
    if not issue_date_raw:
        issue_date_raw = _coluna_data(
            text,
            r"data\s+d[aeo]\s+(?:documento|fatura|nota|conta)|data\s+d[eo]\s+processamento|(?:data\s+de\s+)?emiss[aã]o",
        )
    # Em qualquer posição da linha, com ":" ou espaço de coluna na MESMA linha ("Emissão: 07/10/2026",
    # "Data e Hora da Emissão    01/10/2026"); nunca a data da linha de baixo.
    if not _parse_ocr_date(issue_date_raw):
        m_emissao = re.search(
            r"(?:data\s+(?:e\s+hora\s+)?d[ae]\s+)?emiss[aã]o\s*(?::|[ \t]{2,})[ \t]*(\d{2}[/.]\d{2}[/.]\d{4})",
            text, re.IGNORECASE,
        )
        if m_emissao:
            issue_date_raw = m_emissao.group(1)

    # --- Data de vencimento ---
    # Inline: "Vencimento:", "Pagar até:"
    due_date_raw = labeled_value(
        r"^(?:data\s+de\s+)?(?:vencimento|pagar\s+at[eé])\s*[:\-]?\s*"
        r"(\d{4}-\d{2}-\d{2}|\d{2}[/.]\d{2}[/.]\d{4})$"
    )
    # Fallback coluna: "Vencimento" como cabeçalho de boleto
    if not due_date_raw:
        due_date_raw = _coluna_de(text, r"\bvencimento\b")
    # "... - DATA DE VENCIMENTO: 18/10/2026 - ..." no meio da linha (exige ":" na mesma linha).
    if not _parse_ocr_date(due_date_raw):
        m_venc = re.search(r"vencimento\s*:[ \t]*(\d{2}[/.]\d{2}[/.]\d{4})", text, re.IGNORECASE)
        if m_venc:
            due_date_raw = m_venc.group(1)

    # --- Valor total ---
    # Prioridade 1: linha digitável do boleto (mais confiável)
    _, boleto_amount, boleto_due = _ler_linha_digitavel(text)

    # Prioridade 2: rótulos de texto
    amount = None
    for label in (
        "valor total da nota", r"valor l[ií]quido da nota",
        # herdados do WF-03 (aba Faturas): "valor total da fatura/conta", "total da fatura/conta"
        r"valor\s+total\s+(?:da\s+)?(?:fatura|conta)", r"total\s+(?:da\s+)?(?:fatura|conta)",
        "total a pagar",
        r"valor\s+a\s+pagar", "valor total", "valor do documento", "valor cobrado",
        r"\(=\)\s*valor\s+cobrado",
    ):
        amount_value = labeled_value(
            rf"^(?:{label})\s*[:\-]?\s*(?:R\$\s*)?([\d.]+,\d{{2}}|\d+\.\d{{2}})$"
        )
        if amount_value:
            normalized = amount_value.replace(".", "").replace(",", ".") if "," in amount_value else amount_value
            try:
                amount = float(normalized)
            except ValueError:
                amount = None
            break
    # Rótulo e valor em colunas, em linhas diferentes (NFS-e Nacional: "VALOR TOTAL DA NFS-E" e, na linha de baixo,
    # "R$ 15,00"). Só rótulos específicos: "Valor Total Apurado - IBS" (imposto) não pode virar o valor da conta.
    if amount is None:
        for label in _ROTULOS_VALOR_COLUNA:
            m_coluna = re.match(r"^(?:R\$\s*)?([\d.]+,\d{2})$", _coluna_de(text, label))
            if m_coluna:
                amount = float(m_coluna.group(1).replace(".", "").replace(",", "."))
                break

    # Linha digitável prevalece para valor e vencimento (mais precisa)
    final_amount = boleto_amount if boleto_amount is not None else amount
    final_due_raw = due_date_raw
    if boleto_due:
        final_due_raw = boleto_due  # já é ISO

    # --- CNPJs ---
    def cnpj_on_line(line: str) -> str:
        match = re.search(r"(?<!\d)(?:\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)", line)
        return re.sub(r"\D", "", match.group(0)) if match else ""

    recipient_cnpj_line = next(
        (line for line in lines if re.search(r"(?:tomador|destinat[aá]rio|cliente|contratante|pagador)", line, re.I)
         and re.search(r"\b(?:cnpj|cpf)\b", line, re.I)),
        "",
    )
    issuer_cnpj_line = next(
        (line for line in lines if re.search(r"(?:prestador|fornecedor|emitente|benefici[aá]rio|cedente)", line, re.I)
         and re.search(r"\bcnpj\b", line, re.I)),
        "",
    )

    # Fallback CNPJ emissor: único CNPJ diferente do destinatário
    cnpj_all = re.findall(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", text)
    cnpj_digits_all = list(dict.fromkeys(re.sub(r"\D", "", c) for c in cnpj_all))
    cnpj_dest = cnpj_on_line(recipient_cnpj_line)
    cnpj_emis = cnpj_on_line(issuer_cnpj_line)
    if not cnpj_emis:
        outros = [c for c in cnpj_digits_all if c != cnpj_dest]
        if len(outros) == 1:
            cnpj_emis = outros[0]
    if not cnpj_emis and issuer:
        # CNPJ na linha do nome do emissor ou nas 3 seguintes (DANFECom, NFS-e nacional, boleto).
        nome_emissor = normalize_company_name(issuer)
        for i, linha in enumerate(lines):
            if nome_emissor and nome_emissor in normalize_company_name(linha):
                for vizinha in lines[i:i + 4]:
                    achado = cnpj_on_line(vizinha)
                    if achado and achado != cnpj_dest:
                        cnpj_emis = achado
                        break
                if cnpj_emis:
                    break

    # --- Montar resultado ---
    fields: Dict[str, Any] = {
        "emissorNome": issuer[:300],
        "numero": number[:80],
        "chave": access_key[:160],
        "serie": series[:80],
        "valorTotal": final_amount,
        "dataEmissao": _parse_ocr_date(issue_date_raw),
        "dataVencimento": _parse_ocr_date(final_due_raw) if not boleto_due else boleto_due,
        "descricaoServico": description,
        "cnpjDestinatario": cnpj_dest,
        "cnpjEmissor": cnpj_emis,
        "versaoRegras": REGRAS_EXTRACAO_VERSAO,
    }
    # Emissão não é obrigatória na leitura (cai para a data de recebimento adiante). Obrigatórios: nome, valor, vencimento.
    fields["camposParaRevisar"] = [
        key for key in ("emissorNome", "valorTotal", "dataVencimento")
        if not fields[key]
    ]
    return aplicar_padrao_identificacao(fields)

@app.post("/api/extracao/texto")
def extrair_campos_do_texto():
    """Extrator unificado (P4): campos de fatura/boleto a partir do texto do OCR. Não grava nada.

    Usado pelo WF-03 (aba Faturas e modal do provedor), no lugar do código próprio do workflow.
    Devolve o formato que a tela já usa (``numeroFatura``, ``cnpjCandidatos``, ``comparacao``...).
    """
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("texto") or "")
    if len(text) > 200_000:
        return jsonify({"ok": False, "error": "O texto excede 200000 caracteres."}), 413
    expected_provider = str(payload.get("provedorEsperado") or "").strip()
    fields = _extract_invoice_fields(text) if text.strip() else aplicar_padrao_identificacao({
        "emissorNome": "", "numero": "", "chave": "", "valorTotal": None, "dataEmissao": "", "dataVencimento": "",
        "descricaoServico": "", "cnpjEmissor": "", "cnpjDestinatario": "",
        "camposParaRevisar": ["emissorNome", "valorTotal", "dataVencimento"],
    })
    normalized_text = normalize_company_name(text)
    expected_found = bool(expected_provider and normalize_company_name(expected_provider) in normalized_text)
    if not fields.get("emissorNome"):
        # Último recurso (herdado do WF-03): o provedor esperado aparece no texto, ou uma linha com "telecom/internet".
        if expected_found:
            fields["emissorNome"] = expected_provider
        else:
            line = next((ln.strip() for ln in text.splitlines()
                         if re.search(r"telecom|telecomunic|provedor|internet|comunica[cç][oõ]es", ln, re.I)
                         and len(ln.strip()) <= 120), "")
            fields["emissorNome"] = re.sub(r"\s{2,}.*$", "", line)[:300]
    cnpjs = list(dict.fromkeys(
        re.sub(r"\D", "", value) for value in re.findall(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}", text)
    ))
    try:
        expected_amount = float(payload.get("valorEsperado") or 0)
    except (TypeError, ValueError):
        expected_amount = 0.0
    expected_due = str(payload.get("vencimentoEsperado") or "").strip()
    amount = fields.get("valorTotal")
    revisar = list(fields.get("camposParaRevisar") or [])
    if fields.get("emissorNome") and "emissorNome" in revisar:
        revisar.remove("emissorNome")
    return jsonify({
        "ok": True,
        "extrator": "sigp_backend_unificado_v1",
        "textEncontrado": bool(text.strip()),
        "ocrUsado": bool(payload.get("ocrUsado")),
        "emissorNome": fields.get("emissorNome") or "",
        "emissorEsperadoEncontrado": expected_found,
        "cnpjEmissor": fields.get("cnpjEmissor") or (cnpjs[0] if len(cnpjs) == 1 else ""),
        "cnpjCandidatos": cnpjs,
        "numeroFatura": fields.get("numero") or "",
        "numero": fields.get("numero") or "",
        "numeroPadrao": bool(fields.get("numeroPadrao")),
        "numeroOriginal": fields.get("numeroOriginal", ""),
        "chave": fields.get("chave") or "",
        "dataEmissao": fields.get("dataEmissao") or "",
        "dataVencimento": fields.get("dataVencimento") or "",
        "valorTotal": amount,
        "descricaoServico": fields.get("descricaoServico") or "",
        "linhaDigitavelUsada": bool(_ler_linha_digitavel(text)[0]),
        "versaoRegras": REGRAS_EXTRACAO_VERSAO,
        "comparacao": {
            "emissorConfere": expected_found,
            "valorConfere": expected_amount > 0 and amount is not None and abs(expected_amount - float(amount)) < 0.01,
            "vencimentoConfere": not expected_due or expected_due == fields.get("dataVencimento"),
        },
        "camposParaRevisar": revisar,
        "aviso": "" if text.strip() else "Nenhum texto foi reconhecido no PDF, mesmo após o OCR local; confira os campos manualmente.",
    })


@app.post("/api/notas-recebidas/<item_id>/extrair")
def extrair_nota_recebida(item_id: str):
    item = get_nota_recebida(item_id)
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    pdf_path = NOTAS_RECEBIDAS_DIR / str(item["arquivo_storage"])
    stored = item.get("dados") if isinstance(item.get("dados"), dict) else {}
    if pdf_path.suffix.lower() == ".xml":
        return jsonify({"ok": False, "error": "Chegou só o XML da nota; falta a fatura PDF. Os campos já vieram do XML."}), 422
    if not pdf_path.is_file():
        return jsonify({"ok": False, "error": "O PDF desta nota não foi encontrado no armazenamento."}), 404

    try:
        pdf_data = pdf_path.read_bytes()
        ocr_request = Request(
            OCR_URL,
            data=pdf_data,
            headers={"Content-Type": "application/pdf"},
            method="POST",
        )
        with urlopen(ocr_request, timeout=OCR_TIMEOUT_SECONDS) as response:
            ocr_result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        app.logger.warning("Serviço OCR respondeu HTTP %s ao extrair nota recebida %s.", exc.code, item_id)
        return jsonify({"ok": False, "error": f"Serviço OCR respondeu HTTP {exc.code}: {detail or exc.reason}"}), 502
    except (TimeoutError, URLError) as exc:
        app.logger.warning("Serviço OCR indisponível ao extrair nota recebida %s: %s", item_id, exc)
        return jsonify({"ok": False, "error": "Não foi possível acessar o serviço OCR. Verifique se o container ocr está ativo."}), 503
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        app.logger.exception("Falha ao ler PDF ou resposta OCR da nota recebida %s.", item_id)
        return jsonify({"ok": False, "error": f"Falha ao processar o PDF no serviço OCR: {exc}"}), 502

    if not isinstance(ocr_result, dict) or ocr_result.get("ok") is False:
        return jsonify({"ok": False, "error": "O serviço OCR devolveu uma resposta inválida."}), 502
    text = str(ocr_result.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": str(
            ocr_result.get("aviso") or "Nenhum texto foi reconhecido no PDF."
        )}), 422
    fields = _extract_invoice_fields(text)
    fields["identificadoresCliente"] = identificadores.ler(text)
    stored_data = item.get("dados") if isinstance(item.get("dados"), dict) else {}
    # Campos lidos agora prevalecem; o que não foi lido aproveita o que já estava salvo.
    for key in (
        "emissorNome", "serie", "valorTotal",
        "dataVencimento", "descricaoServico", "cnpjDestinatario", "cnpjEmissor",
    ):
        if fields.get(key) in (None, "") and stored_data.get(key) not in (None, ""):
            fields[key] = stored_data[key]
    # Número e chave: dado real vence o padrão; o padrão nunca substitui dado real.
    mesclar_identificacao(fields, stored_data)
    # Emissão: documento (rótulos ampliados) -> emissão já salva do documento -> data de recebimento,
    # sempre com a origem registrada. Uma emissão salva como "recebimento" não conta como dado do documento.
    if fields.get("dataEmissao"):
        fields["dataEmissaoOrigem"] = "documento"
    elif stored_data.get("dataEmissao") and stored_data.get("dataEmissaoOrigem") != "recebimento":
        fields["dataEmissao"] = stored_data["dataEmissao"]
        fields["dataEmissaoOrigem"] = "documento"
    else:
        aplicar_data_emissao(fields, item.get("recebida_em"), item.get("created_at"))
    revisar = [
        key for key in ("emissorNome", "valorTotal", "dataVencimento")
        if fields.get(key) in (None, "")
    ]
    for key in ("numero", "chave", "dataEmissao"):
        if key in (fields.get("camposParaRevisar") or []) and key not in revisar:
            revisar.append(key)
    fields["camposParaRevisar"] = revisar
    if isinstance(stored.get("xmlFiscal"), dict):
        # Prioridade do XML (decisão do usuário): a releitura do PDF não substitui os campos fiscais do XML.
        fields = aplicar_prioridade_xml(fields, stored["xmlFiscal"])
        fields["xmlFiscal"] = stored["xmlFiscal"]
        fields["xmlArquivo"] = stored.get("xmlArquivo")
        aplicar_padrao_identificacao(fields)
    fields["versaoRegras"] = REGRAS_EXTRACAO_VERSAO
    # Releitura sob demanda: grava a leitura nova enquanto a nota não foi associada nem descartada,
    # preservando o que não é leitura do PDF (XML, classificação da IA, análise, descarte).
    gravada = atualizar_extracao_nota_recebida(item_id, fields)
    return jsonify({
        "ok": True,
        "dados": fields,
        "ocrUsado": bool(ocr_result.get("ocrUsado")),
        "textEncontrado": True,
        "gravada": gravada,
    })


def _validar_xml_nota(texto: str) -> str:
    """O SIGp só guarda o XML (quem lê é o n8n). Recusa o que não é XML, DOCTYPE/ENTITY e tamanho excessivo."""
    if len(texto.encode("utf-8")) > 2 * 1024 * 1024:
        return "O XML da nota excede 2 MiB."
    if not re.match(r"^\ufeff?\s*<", texto):
        return "O conteúdo enviado como XML da nota não é XML."
    if re.search(r"<!DOCTYPE|<!ENTITY", texto, re.IGNORECASE):
        return "XML com DOCTYPE/ENTITY não é aceito."
    return ""


def _enviar_xml(pasta: Path, info: Any, rotulo: str):
    info = info if isinstance(info, dict) else {}
    nome = Path(str(info.get("storage") or "")).name  # só o nome: nada de caminhos vindos do JSON
    path = pasta / nome if nome.endswith(".xml") else None
    if not path or not path.is_file():
        return jsonify({"ok": False, "error": f"{rotulo} não tem XML da nota fiscal."}), 404
    return send_file(path, mimetype="application/xml", as_attachment=True, download_name=str(info.get("nome") or nome))


@app.get("/api/notas-disponiveis")
def notas_disponiveis_route():
    """Notas disponíveis (documentos do e-mail associados ao local), com os documentos de cada uma."""
    tipo = str(request.args.get("entidadeTipo") or "").strip().lower()
    if tipo and tipo not in LOCAL_TIPOS:
        return jsonify({"ok": False, "error": "Tipo de local inválido."}), 400
    return jsonify({"ok": True, "items": notas_disponiveis.listar(tipo, str(request.args.get("entidadeId") or "").strip())})


@app.get("/api/faturas/<fatura_id>/xml")
def download_xml_fatura(fatura_id: str):
    fatura = get_fatura_local(fatura_id)
    if not fatura:
        return jsonify({"ok": False, "error": "Documento não encontrado."}), 404
    return _enviar_xml(FATURAS_DIR, (fatura.get("dados") or {}).get("xmlNotaFiscal"), "Este documento")


@app.get("/api/notas-recebidas/<item_id>/xml")
def download_xml_nota_recebida(item_id: str):
    item = get_nota_recebida(item_id)
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    return _enviar_xml(NOTAS_RECEBIDAS_DIR, (item.get("dados") or {}).get("xmlArquivo"), "Esta nota recebida")


@app.get("/api/notas/lancadas/<nota_id>/xml")
def download_xml_nota_lancada(nota_id: str):
    nota = get_nota_lancada(nota_id)
    if not nota:
        return jsonify({"ok": False, "error": "Nota lançada não encontrada."}), 404
    # notas_lancadas tem colunas fixas: o XML fica registrado na nota recebida associada (a mais recente vale,
    # inclusive na recorrência mensal, quando a nota do mês é atualizada pelo XML novo).
    recebidas = sorted(
        (item for item in list_notas_recebidas("ASSOCIADA") if item.get("nota_lancada_id") == nota_id
         and (item.get("dados") or {}).get("xmlNotaFiscal")),
        key=lambda item: str(item.get("updated_at") or ""), reverse=True,
    )
    info = (recebidas[0]["dados"]["xmlNotaFiscal"]) if recebidas else None
    return _enviar_xml(FATURAS_DIR, info, "Esta nota lançada")


@app.get("/api/notas-recebidas/<item_id>/arquivo")
def download_nota_recebida(item_id: str):
    item = get_nota_recebida(item_id)
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    path = NOTAS_RECEBIDAS_DIR / item["arquivo_storage"]
    if not path.is_file():
        return jsonify({"ok": False, "error": "O PDF da nota recebida não foi encontrado no armazenamento."}), 404
    tipo = "application/xml" if path.suffix.lower() == ".xml" else "application/pdf"
    return send_file(path, mimetype=tipo, as_attachment=False, download_name=item["nome_arquivo"])


@app.patch("/api/notas-recebidas/<item_id>/associar")
def associar_nota_recebida_route(item_id: str):
    payload = request.get_json(silent=True) or {}
    entidade_tipo = str(payload.get("entidadeTipo") or "").strip().lower()
    entidade_id = str(payload.get("entidadeId") or "").strip()
    operador = _autor(payload.get("operador"))
    if entidade_tipo not in LOCAL_TIPOS or not entidade_id:
        return jsonify({"ok": False, "error": "Selecione uma agência, rodoviária ou garagem."}), 400
    local = get_local(entidade_id)
    if not local or local.get("tipo") != entidade_tipo or not local.get("ativo"):
        return jsonify({"ok": False, "error": "O local selecionado não existe, está inativo ou pertence a outro tipo."}), 404
    item = get_nota_recebida(item_id)
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    if item.get("status") == "IGNORADA_IA":
        return jsonify({"ok": False, "error": "Documento ignorado pela IA: resgate-o para a caixa antes de associar."}), 409
    if (item.get("dados") or {}).get("semArquivo"):
        return jsonify({"ok": False, "error": "Aviso sem anexo não vira nota lançada: lance a fatura do mês e use \"Tentar vincular de novo\"."}), 409
    data = dict(item.get("dados") or {})
    correction_fields = {
        "emissorNome", "dataEmissao", "dataVencimento", "valorTotal", "chave",
        "numero", "serie", "descricaoServico",
    }
    corrections = payload.get("dados") if isinstance(payload.get("dados"), dict) else {}
    corrections = {key: value for key, value in corrections.items() if key in correction_fields}
    extraidos = json.loads(json.dumps(item.get("dados") or {}))  # retrato do que a extração entregou (para o feedback)
    try:
        sugestoes_antes = _serialize_nota_recebida_api(item).get("sugestoesLocal") or []
    except Exception:  # noqa: BLE001 (métrica: nunca impede a associação)
        sugestoes_antes = []
    # Número/chave que o usuário digitou de fato (diferente do extraído) valem como digitados.
    digitados = {
        key: str(corrections[key]).strip()
        for key in ("numero", "chave")
        if str(corrections.get(key) or "").strip()
        and str(corrections[key]).strip() != str(extraidos.get(key) or "").strip()
    }
    data.update(corrections)
    # Vazios ou inválidos viram o valor padrão (999999999); nunca bloqueiam a associação.
    aplicar_padrao_identificacao(data)
    data.update(digitados)
    provider_name = str(data.get("emissorNome") or "").strip()[:300]
    due_date = str(data.get("dataVencimento") or "").strip()
    issue_date = str(data.get("dataEmissao") or "").strip()
    # Obrigatórios, sem valor padrão: se o OCR não achou, o usuário informa à mão.
    try:
        amount = float(data.get("valorTotal"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Informe o valor da nota (obrigatório; o OCR não o identificou)."}), 400
    if not provider_name:
        return jsonify({"ok": False, "error": "Informe o emissor/provedor da nota (obrigatório; o OCR não o identificou)."}), 400
    if not isfinite(amount) or amount <= 0:
        return jsonify({"ok": False, "error": "O valor da nota precisa ser maior que zero."}), 400
    try:
        datetime.strptime(due_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"ok": False, "error": "Informe a data de vencimento (obrigatória; formato AAAA-MM-DD)."}), 400
    if issue_date:
        try:
            datetime.strptime(issue_date, "%Y-%m-%d")
            data.setdefault("dataEmissaoOrigem", "documento")
        except ValueError:
            return jsonify({"ok": False, "error": "A data de emissão informada é inválida (AAAA-MM-DD)."}), 400
    else:
        # Sem emissão no documento: vale a data de recebimento, com a origem registrada.
        aplicar_data_emissao(data, item.get("recebida_em"), item.get("created_at"))
        issue_date = data["dataEmissao"]
    data.update({
        "emissorNome": provider_name,
        "valorTotal": amount,
        "dataEmissao": issue_date,
        "dataVencimento": due_date,
        "chave": str(data.get("chave") or "").strip()[:160],
        "numero": str(data.get("numero") or "").strip()[:80],
        "serie": str(data.get("serie") or "").strip()[:80],
        "descricaoServico": str(data.get("descricaoServico") or "").strip()[:1000],
    })
    comparison = _compare_received_invoice(data, entidade_tipo, entidade_id)
    candidates = comparison["candidatas"]
    selected_note_id = str(payload.get("notaDisponivelId") or payload.get("notaLancadaId") or "").strip()
    if len(candidates) > 1 and not selected_note_id:
        return jsonify({
            "ok": False,
            "error": "Escolha qual nota existente será comparada antes de associar.",
            "requiresComparison": True,
            "comparacao": comparison,
        }), 409
    selected_candidate = next(
        (candidate for candidate in candidates if candidate["notaDisponivelId"] == selected_note_id),
        candidates[0] if len(candidates) == 1 else None,
    )
    if selected_note_id and not selected_candidate:
        return jsonify({
            "ok": False,
            "error": "A nota selecionada não é uma correspondência válida neste local. Compare novamente.",
            "requiresComparison": True,
            "comparacao": comparison,
        }), 409
    if selected_candidate and selected_candidate["diferencas"] and (
        not payload.get("confirmarAtualizacao") or selected_note_id != selected_candidate["notaDisponivelId"]
    ):
        return jsonify({
            "ok": False,
            "error": "Há divergências na nota existente. Confira os campos e confirme a atualização, ou mantenha a nota recebida sem associar.",
            "requiresConfirmation": True,
            "comparacao": comparison,
        }), 409
    if not candidates and selected_note_id:
        return jsonify({"ok": False, "error": "Não há nota existente selecionada para atualizar."}), 409

    label_groups = {"agencia": "Agências", "rodoviaria": "Rodoviárias", "garagem": "Garagens"}
    label_name = re.sub(r"[\x00-\x1f/\\]+", " - ", str(local.get("nome") or "")).strip(" .-") or local["id"]
    label = f"SIGp/{label_groups[entidade_tipo]}/{label_name}"

    source_path = NOTAS_RECEBIDAS_DIR / str(item["arquivo_storage"])
    if source_path.suffix.lower() == ".xml":
        return jsonify({"ok": False, "error": "Chegou só o XML da nota fiscal. A fatura PDF também é obrigatória; associe quando ela chegar."}), 409
    if not source_path.is_file():
        return jsonify({"ok": False, "error": "O PDF desta nota não foi encontrado no armazenamento."}), 404
    xml_origem = Path(str(((item.get("dados") or {}).get("xmlArquivo") or {}).get("storage") or "")).name
    if xml_origem.endswith(".xml") and (NOTAS_RECEBIDAS_DIR / xml_origem).is_file():
        xml_storage_name = f"gmail-{uuid4().hex}.xml"
        shutil.copyfile(NOTAS_RECEBIDAS_DIR / xml_origem, FATURAS_DIR / xml_storage_name)
        data["xmlNotaFiscal"] = {"storage": xml_storage_name, "nome": item["dados"]["xmlArquivo"].get("nome") or xml_origem}
    storage_name = f"gmail-{uuid4().hex}.pdf"
    storage_path = FATURAS_DIR / storage_name
    shutil.copyfile(source_path, storage_path)
    try:
        integration = integrar_nota_recebida(
            item_id, entidade_tipo, entidade_id, label, operador, local, data, storage_name,
            selected_note_id=selected_candidate["notaDisponivelId"] if selected_candidate else "",
            # Divergência confirmada (número/valor diferentes) = correção: o documento novo substitui a fatura.
            # Sem divergência = outro documento da mesma cobrança: entra como adicional, sem substituir.
            substituir=bool(selected_candidate and selected_candidate["diferencas"]),
        )
    except ValueError as exc:
        storage_path.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except sqlite3.Error:
        storage_path.unlink(missing_ok=True)
        raise
    if not integration:
        storage_path.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    previous_storage = integration["arquivoAnterior"]
    if previous_storage and previous_storage != storage_name and not any(
        invoice.get("arquivo_storage") == previous_storage for invoice in list_faturas_locais()
    ):
        (FATURAS_DIR / previous_storage).unlink(missing_ok=True)
    disponivel = integration["notaDisponivel"]
    launched_note = integration["notaLancada"]  # só quando o financeiro já lançou a nota correspondente
    log_event("nota_disponivel_associada", {"notaDisponivelId": disponivel["id"], "notaLancadaId": (launched_note or {}).get("id", ""),
                                            "entidadeTipo": entidade_tipo, "entidadeId": entidade_id})
    reconciliations = reconcile_note(launched_note["id"]) if launched_note else []
    log_event("nota_recebida_associada", {
        "notaRecebidaId": item_id,
        "entidadeTipo": entidade_tipo,
        "entidadeId": entidade_id,
        "operador": operador,
        "notaDisponivelId": disponivel["id"],
        "notaLancadaId": (launched_note or {}).get("id", ""),
        "reconciliacoes": reconciliations,
    })
    # P2-04: o provedor de internet do local recebe nome, valor e vencimento da fatura (base dos alertas).
    provider_update = _atualizar_provedor_do_local(
        entidade_id, provider_name, amount, due_date, str(integration.get("faturaId") or ""),
    )
    aprendidos: Dict[str, Any] = {"adicionados": [], "emOutroLocal": []}
    try:
        aprendidos = aprender_codigos_cliente(entidade_id, provider_name, data.get("identificadoresCliente") or [])
        if aprendidos.get("provedor") and (aprendidos["adicionados"] or provider_update.get("provedor")):
            # O navegador regrava o local inteiro: devolve o provedor já com os códigos para ele não apagar.
            provider_update = {**provider_update, "provedor": aprendidos["provedor"],
                               "acao": provider_update.get("acao") if provider_update.get("acao") in ("criado", "atualizado") else "atualizado"}
    except sqlite3.Error:
        app.logger.exception("Não foi possível guardar o código do cliente da nota %s.", item_id)
    try:
        # Exemplo rotulado: extração original x dados confirmados pelo usuário (base para medir/melhorar a LLM).
        registrar_feedback_extracao(
            item_id, "associada", provedor=provider_name, entidade_tipo=entidade_tipo, entidade_id=entidade_id,
            operador=operador, extraidos=extraidos,
            finais={**data, "sugestaoLocalId": str((sugestoes_antes[0] if sugestoes_antes else {}).get("id") or "")},
        )
    except sqlite3.Error:
        app.logger.exception("Não foi possível registrar o feedback da associação %s.", item_id)
    return jsonify({
        "ok": True,
        "item": _serialize_nota_recebida_api(integration["item"]),
        "gmailLabel": label,
        "notaDisponivel": disponivel,
        "notaDisponivelCriada": integration["createdNote"],
        "notaLancada": launched_note,
        "documentoAdicional": bool(integration.get("documentoAdicional")),
        "provedor": provider_update.get("provedor"),
        "provedorAcao": provider_update.get("acao"),
        "provedorAviso": provider_update.get("aviso", ""),
        "codigosAprendidos": aprendidos.get("adicionados", []),
        "codigosEmOutroLocal": aprendidos.get("emOutroLocal", []),
        "conciliacoes": reconciliations,
    })


MOTIVOS_DESCARTE = {
    "nao_cobranca": "Não é cobrança de internet/telecom",
    "duplicada": "Duplicada",
    "ilegivel": "Ilegível ou sem texto",
    "fora_escopo": "Fora do escopo (outro serviço ou empresa)",
    "outro": "Outro motivo",
}


@app.patch("/api/notas-recebidas/<item_id>/descartar")
def descartar_nota_recebida_route(item_id: str):
    payload = request.get_json(silent=True) or {}
    motivo = str(payload.get("motivo") or "").strip()
    if motivo not in MOTIVOS_DESCARTE:
        return jsonify({"ok": False, "error": "Informe o motivo do descarte.", "motivos": MOTIVOS_DESCARTE}), 400
    detalhe = str(payload.get("detalhe") or "").strip()
    operador = _autor(payload.get("operador"))
    atual = get_nota_recebida(item_id)
    if not atual:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    try:
        item = descartar_nota_recebida(item_id, motivo, detalhe, operador)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    if atual.get("status") != "DESCARTADA":
        registrar_feedback_extracao(
            item_id, "descartada", motivo=motivo, provedor=str((atual.get("dados") or {}).get("emissorNome") or ""),
            operador=operador, extraidos=atual.get("dados") or {}, finais={"motivo": motivo, "detalhe": detalhe[:500]},
        )
        log_event("nota_recebida_descartada", {"notaRecebidaId": item_id, "motivo": motivo, "operador": operador})
    return jsonify({"ok": True, "item": _serialize_nota_recebida_api(item)})


@app.patch("/api/notas-recebidas/<item_id>/restaurar")
def restaurar_nota_recebida_route(item_id: str):
    operador = _autor((request.get_json(silent=True) or {}).get("operador"))
    try:
        item = restaurar_nota_recebida(item_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    log_event("nota_recebida_restaurada", {"notaRecebidaId": item_id, "operador": operador})
    return jsonify({"ok": True, "item": _serialize_nota_recebida_api(item)})


_TIPO_LOCAL_ROTULO = {"agencia": "Agência", "rodoviaria": "Rodoviária", "garagem": "Garagem"}


def _endereco_email(remetente: str) -> str:
    texto = str(remetente or "")
    if "object Object" in texto:
        return ""
    achado = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texto)
    return achado.group(0).lower() if achado else ""


def _palavras_assunto(assunto: str) -> set:
    texto = normalize_company_name_words(assunto)
    return {p for p in texto.split() if len(p) >= 4 and p not in {"fatura", "boleto", "nota", "fiscal", "internet", "segunda", "via"}}


def normalize_company_name_words(valor: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(valor or "").casefold())
    sem = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sem).strip()


def _limpo(valor: Any, tamanho: int = 120) -> str:
    """Texto curto e numa linha só: os exemplos vão para o prompt e não podem carregar instruções longas."""
    return re.sub(r"\s+", " ", str(valor or "")).strip()[:tamanho]


def _rotulo_local(tipo: Any, nome: Any) -> str:
    rotulo, nome = _TIPO_LOCAL_ROTULO.get(str(tipo or ""), ""), str(nome or "").strip()
    return nome if not rotulo or normalize_company_name(nome).startswith(normalize_company_name(rotulo)) else f"{rotulo} {nome}"


def _exemplo_de(caso: Dict[str, Any]) -> Dict[str, Any]:
    dados, extraidos = caso.get("dados") or {}, caso.get("extraidos") or {}
    triagem = dados.get("triagem") or {}
    exemplo = {
        "id": caso["id"],
        "remetente": _endereco_email(caso.get("remetente")),
        "assunto": _limpo(caso.get("assunto"), 90),
        "arquivo": _limpo(caso.get("nome_arquivo"), 60),
        "decididoEm": str(caso.get("updated_at") or "")[:10],
    }
    if caso["status"] == "ASSOCIADA":
        exemplo.update({
            "rotulo": "cobranca_provedor",
            "provedor": _limpo(dados.get("emissorNome"), 80),
            "tipoDocumento": _limpo(dados.get("tipoDocumento") or extraidos.get("tipoDocumento") or "", 20),
            "local": _limpo(_rotulo_local(caso.get("entidade_tipo"), caso.get("local_nome")), 80),
            "valor": dados.get("valorTotal"),
        })
        lido = _limpo(extraidos.get("emissorNome"), 80)
        if lido and normalize_company_name(lido) != normalize_company_name(exemplo["provedor"]):
            exemplo["correcao"] = f"a leitura trouxe \"{lido}\"; o correto é \"{exemplo['provedor']}\""
        if triagem.get("resgatadoEm"):
            exemplo["correcao"] = "a IA tinha ignorado; o operador confirmou que é cobrança"
    else:
        descarte = dados.get("descarte") or {}
        exemplo.update({
            "rotulo": "nao_cobranca",
            "motivo": _limpo(MOTIVOS_DESCARTE.get(descarte.get("motivo"), descarte.get("motivo") or ""), 60),
            "detalhe": _limpo(descarte.get("detalhe"), 80),
        })
    return exemplo


def _pastas_arquivos() -> Dict[str, Path]:
    return {"notas_recebidas": NOTAS_RECEBIDAS_DIR, "faturas": FATURAS_DIR}


def _backup_dir() -> Path:
    return Path(_database.DB_PATH).parent / "backups"


@app.get("/api/llm/metricas")
def metricas_llm_route():
    """Painel da IA: acerto da triagem, dos campos e do local por mês, tempo por documento e memória do modelo."""
    try:
        meses = min(max(int(request.args.get("meses") or 6), 1), 24)
    except ValueError:
        meses = 6
    resultado = metricas_llm.calcular(list_notas_recebidas(), listar_feedback(), meses=meses)
    resultado["modelo"] = metricas_llm.estado_modelo(
        os.environ.get("SIGP_OLLAMA_URL", "http://ollama:11434"), os.environ.get("SIGP_OLLAMA_MODEL", "qwen2.5:3b"),
    )
    resultado["resumo"] = metricas_llm.resumo_textual(resultado)
    return jsonify({"ok": True, **resultado})


# Variáveis de integração do servidor: só o estado. Segredos aparecem como "definida/não definida", nunca o valor.
_INTEGRACAO_SEGREDOS = ("SIGP_API_KEY", "SIGP_N8N_TOKEN", "SIGP_COFRE_CHAVE")
_INTEGRACAO_VALORES = ("SIGP_CORS_ORIGINS", "SIGP_N8N_EVENTOS_URL", "SIGP_EXIGIR_FATURA", "SIGP_PUBLIC_API_URL", "SIGP_PUBLIC_N8N_URL")


# ---------------------------------------------------------------- assistente da IA local
_REL_ID = re.compile(r"^rel-\d{8}-\d{6}-[0-9a-f]{6}$")


def _quem_pergunta() -> Dict[str, Any]:
    quem = getattr(g, "acesso", None)
    if quem:
        return quem
    return {"perfil": acesso.ADMIN, "nome": "Administrador", "usuario": "", "permissoes": acesso.TODAS}  # sem SIGP_API_KEY (desenvolvimento)


def _pasta_relatorios() -> Path:
    return Path(_database.DB_PATH).resolve().parent / "relatorios_assistente"


def _contexto_assistente() -> "assistente.Contexto":
    quem = _quem_pergunta()
    permissoes = acesso.TODAS if quem.get("perfil") == acesso.ADMIN else quem.get("permissoes", [])
    hoje = date.today()
    return assistente.Contexto(quem.get("usuario") or quem.get("nome") or "", permissoes, hoje, _pasta_relatorios(),
                               alertas=lambda: _lista_alertas(hoje, 5), locais=list_locais, notas_recebidas=list_notas_recebidas)


@app.post("/api/assistente/perguntar")
def assistente_perguntar_route():
    payload = request.get_json(silent=True) or {}
    try:
        resposta = assistente.responder(payload.get("pergunta"), _contexto_assistente(), conversa_id=str(payload.get("conversaId") or "") or None)
    except ValueError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 400
    except LookupError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 404
    return jsonify({"ok": True, **resposta})


def _usuario_assistente() -> str:
    quem = _quem_pergunta()
    return quem.get("usuario") or quem.get("nome") or ""


@app.get("/api/assistente/conversas")
def assistente_conversas_route():
    return jsonify({"ok": True, "items": assistente.listar_conversas(_usuario_assistente())})


@app.get("/api/assistente/conversas/<conversa_id>")
def assistente_conversa_route(conversa_id: str):
    try:
        return jsonify({"ok": True, **assistente.mensagens(conversa_id, _usuario_assistente())})
    except LookupError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 404


@app.patch("/api/assistente/conversas/<conversa_id>")
def assistente_renomear_route(conversa_id: str):
    try:
        assistente.renomear_conversa(conversa_id, _usuario_assistente(), (request.get_json(silent=True) or {}).get("titulo"))
    except ValueError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 400
    except LookupError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 404
    return jsonify({"ok": True})


@app.delete("/api/assistente/conversas/<conversa_id>")
def assistente_apagar_route(conversa_id: str):
    try:
        assistente.apagar_conversa(conversa_id, _usuario_assistente())
    except LookupError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 404
    return jsonify({"ok": True})


@app.get("/api/assistente/treinamento")
def assistente_treinamento_route():
    return jsonify({"ok": True, **assistente.treinamento()})


@app.get("/api/assistente/dataset.jsonl")
def assistente_dataset_route():
    from flask import Response
    return Response(assistente.dataset_jsonl(), mimetype="application/jsonl; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=sigp-assistente-dataset.jsonl"})


@app.post("/api/assistente/avaliar")
def assistente_avaliar_route():
    payload = request.get_json(silent=True) or {}
    quem = _quem_pergunta()
    try:
        r = assistente.avaliar(str(payload.get("id") or ""), bool(payload.get("util")), str(payload.get("comentario") or ""),
                               quem.get("usuario") or quem.get("nome") or "")
    except LookupError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 404
    return jsonify({"ok": True, **r})


@app.get("/api/assistente/historico")
def assistente_historico_route():
    quem = _quem_pergunta()
    return jsonify({"ok": True, "items": assistente.historico(quem.get("usuario") or quem.get("nome") or "")})


@app.get("/api/assistente/conhecimento")
def assistente_conhecimento_route():
    return jsonify({"ok": True, **assistente.conhecimento()})


@app.post("/api/assistente/termos")
def assistente_termos_route():
    payload = request.get_json(silent=True) or {}
    quem = _quem_pergunta()
    try:
        item = assistente.aprender_termo(payload.get("termo"), payload.get("significa"), quem.get("usuario") or quem.get("nome") or "")
    except ValueError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 400
    return jsonify({"ok": True, "item": item}), 201


@app.get("/api/assistente/relatorios/<rel_id>/<formato>")
def assistente_relatorio_route(rel_id: str, formato: str):
    if not _REL_ID.match(rel_id) or formato not in ("pdf", "csv"):
        return jsonify({"ok": False, "error": "Relatório inválido."}), 404
    pasta = _pasta_relatorios()
    meta_arquivo, arquivo = pasta / f"{rel_id}.json", pasta / f"{rel_id}.{formato}"
    if not meta_arquivo.exists() or not arquivo.exists():
        return jsonify({"ok": False, "error": "Relatório não encontrado (os relatórios ficam guardados por 7 dias)."}), 404
    quem = _quem_pergunta()
    dono = json.loads(meta_arquivo.read_text(encoding="utf-8")).get("usuario", "")
    if quem.get("perfil") != acesso.ADMIN and dono != (quem.get("usuario") or quem.get("nome") or ""):
        return jsonify({"ok": False, "error": "Este relatório é de outro usuário."}), 403
    return send_file(arquivo, mimetype="application/pdf" if formato == "pdf" else "text/csv; charset=utf-8",
                     as_attachment=formato == "csv", download_name=f"{rel_id}.{formato}")


@app.get("/api/configuracoes/alertas")
def config_alertas_route():
    """E-mails que recebem o resumo diário de alertas (lido pelo WF-06 antes de enviar)."""
    return jsonify({"ok": True, **config_alertas.ler(), "maximo": config_alertas.MAX_EMAILS})


@app.put("/api/configuracoes/alertas")
def config_alertas_salvar_route():
    payload = request.get_json(silent=True) or {}
    quem = (getattr(g, "acesso", None) or {}).get("nome") or "Administrador"
    try:
        dados = config_alertas.salvar(payload.get("emails"), quem, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **dados, "maximo": config_alertas.MAX_EMAILS})


@app.get("/api/configuracoes/email-faturas")
def config_email_faturas_route():
    """Remetentes da busca de faturas e a busca pronta do Gmail (lida pelo WF-08 antes de cada leitura)."""
    return jsonify({"ok": True, **config_email_faturas.ler()})


@app.put("/api/configuracoes/email-faturas")
def config_email_faturas_salvar_route():
    payload = request.get_json(silent=True) or {}
    quem = (getattr(g, "acesso", None) or {}).get("nome") or "Administrador"
    try:
        dados = config_email_faturas.salvar(payload.get("remetentes"), quem, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **dados})


# Cofre de chaves (backend/cofre.py): grava e apaga; nunca devolve o valor.
@app.get("/api/cofre")
def cofre_estado_route():
    return jsonify({"ok": True, **cofre.estado()})


@app.put("/api/cofre/<nome>")
def cofre_salvar_route(nome: str):
    payload = request.get_json(silent=True) or {}
    quem = (getattr(g, "acesso", None) or {}).get("nome") or "Administrador"
    try:
        return jsonify({"ok": True, **cofre.salvar(nome, payload.get("valor"), quem)})
    except cofre.CofreErro as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404 if str(exc) == "Segredo desconhecido." else 400


@app.delete("/api/cofre/<nome>")
def cofre_apagar_route(nome: str):
    try:
        return jsonify({"ok": True, **cofre.apagar(nome)})
    except cofre.CofreErro as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.get("/api/integracao/estado")
def integracao_estado_route():
    variaveis: Dict[str, Any] = {}
    for nome in _INTEGRACAO_SEGREDOS:
        variaveis[nome] = {"segredo": True, "definida": bool(os.environ.get(nome, "").strip())}
    for nome in _INTEGRACAO_VALORES:
        valor = os.environ.get(nome, "").strip()
        variaveis[nome] = {"segredo": False, "definida": bool(valor), "valor": valor[:200]}
    ocr: Dict[str, Any] = {"ok": False}
    try:
        with urllib.request.urlopen(os.environ.get("SIGP_OCR_URL", "http://ocr:5002") + "/health", timeout=3) as resposta:  # noqa: S310
            ocr = {"ok": True, **json.loads(resposta.read().decode("utf-8"))}
    except (OSError, ValueError):
        pass
    if "regrasSenha" in ocr:
        variaveis["SIGP_PDF_SENHA_CNPJS"] = {"segredo": False, "definida": ocr["regrasSenha"] > 0, "valor": f"{ocr['regrasSenha']} empresa(s)"}
    eventos = list_eventos(limite=1)
    ultimo = eventos[0] if eventos else None
    eventos_texto = "nenhum evento enviado ainda" if not ultimo else (
        f"último {ultimo.get('evento')} {str(ultimo.get('status') or '').lower()} em {str(ultimo.get('created_at') or '')[:16].replace('T', ' ')}")
    return jsonify({
        "ok": True, "variaveis": variaveis, "ocr": ocr,
        "ollama": metricas_llm.estado_modelo(os.environ.get("SIGP_OLLAMA_URL", "http://ollama:11434"), os.environ.get("SIGP_OLLAMA_MODEL", "qwen2.5:3b")),
        "eventos": {"configurado": bool(events.webhook_url()), "texto": eventos_texto if events.webhook_url() else "SIGP_N8N_EVENTOS_URL não definida"},
    })


@app.get("/api/saude/banco")
def saude_banco_route():
    completo = str(request.args.get("completo") or "") in ("1", "true", "sim")
    return jsonify({"ok": True, **saude_banco.verificar(Path(_database.DB_PATH), _backup_dir(), _pastas_arquivos(), completo)})


@app.post("/api/saude/banco/backup")
def saude_banco_backup_route():
    """Backup consistente + teste de restauração + rodízio (7 diários e 4 semanais). Chamado pelo n8n todo dia."""
    try:
        resultado = saude_banco.fazer_backup(Path(_database.DB_PATH), _backup_dir())
    except (RuntimeError, sqlite3.Error, OSError) as erro:
        log_event("backup_banco_falhou", {"erro": str(erro)[:300]})
        return jsonify({"ok": False, "error": str(erro)[:300]}), 500
    log_event("backup_banco", {"arquivo": resultado["arquivo"], "bytes": resultado["bytes"], "removidos": len(resultado["removidos"])})
    return jsonify({"ok": True, **resultado})


@app.post("/api/saude/banco/manutencao")
def saude_banco_manutencao_route():
    try:
        resultado = saude_banco.manutencao(Path(_database.DB_PATH))
    except sqlite3.Error as erro:
        return jsonify({"ok": False, "error": str(erro)[:300]}), 500
    log_event("manutencao_banco", resultado)
    return jsonify({"ok": True, **resultado, "saude": saude_banco.verificar(Path(_database.DB_PATH), _backup_dir(), _pastas_arquivos())})


@app.get("/api/llm/exemplos")
def exemplos_llm_route():
    """Memória de exemplos (etapa 4): decisões do operador em documentos parecidos, para o prompt da LLM.

    Semelhança: mesmo remetente (+5), mesmo domínio (+3), mesma empresa no nome lido/remetente (+3),
    palavras do assunto em comum (+1 cada, até 2). Só entra quem pontua; um exemplo por combinação
    rótulo + provedor + remetente; os mais recentes primeiro no empate. Não envia valores fiscais (chave, número).
    """
    remetente = _endereco_email(request.args.get("remetente") or "")
    dominio = remetente.split("@", 1)[1] if "@" in remetente else ""
    assunto = _palavras_assunto(request.args.get("assunto") or "")
    nome_remetente = re.sub(r"<[^>]*>|\"", "", str(request.args.get("remetente") or "")).strip()
    empresa = str(request.args.get("emissor") or "").strip() or nome_remetente
    try:
        limite = min(max(int(request.args.get("limite") or 4), 1), 8)
    except ValueError:
        limite = 4
    pontuados = []
    for caso in casos_decididos():
        exemplo = _exemplo_de(caso)
        pontos = 0
        if remetente and exemplo["remetente"] == remetente:
            pontos += 5
        elif dominio and exemplo["remetente"].endswith("@" + dominio):
            pontos += 3
        alvo = exemplo.get("provedor") or _limpo(caso.get("remetente"), 80)
        # Nome genérico do remetente ("Faturamento", "Financeiro") não identifica empresa.
        if empresa and alvo and marca_provedor(empresa) and mesma_empresa(alvo, empresa):
            pontos += 3
        pontos += min(2, len(assunto & _palavras_assunto(caso.get("assunto") or "")))
        # Só assunto parecido não basta ("fatura" está em quase todo e-mail): precisa remetente, domínio ou empresa.
        if pontos >= 3:
            pontuados.append((pontos, exemplo["decididoEm"], exemplo))
    pontuados.sort(key=lambda x: (x[0], x[1]), reverse=True)
    vistos, exemplos = set(), []
    for pontos, _data, exemplo in pontuados:
        chave = (exemplo["rotulo"], normalize_company_name(exemplo.get("provedor") or ""), exemplo["remetente"])
        if chave in vistos:
            continue
        vistos.add(chave)
        exemplos.append({**exemplo, "semelhanca": pontos})
        if len(exemplos) >= limite:
            break
    return jsonify({"ok": True, "exemplos": exemplos, "total": len(exemplos)})


@app.get("/api/notas-recebidas/triagem")
def resumo_triagem_route():
    """Últimas leituras do Gmail (por execução do n8n): documentos para a caixa e ignorados pela IA."""
    try:
        limite = min(max(int(request.args.get("limite") or 5), 1), 30)
    except ValueError:
        limite = 5
    return jsonify({"ok": True, **resumo_triagem(limite)})


@app.post("/api/notas-recebidas/ignorados/confirmar")
def confirmar_ignorados_route():
    """Operador concorda com a IA: os documentos ignorados viram descartados ("não é cobrança"). Aceita lote."""
    payload = request.get_json(silent=True) or {}
    ids = [str(i) for i in (payload.get("ids") or []) if str(i).strip()][:200]
    operador = _autor(payload.get("operador"))
    if not ids:
        return jsonify({"ok": False, "error": "Informe os documentos em 'ids'."}), 400
    confirmados, ignorados_fora = [], []
    for item_id in ids:
        atual = get_nota_recebida(item_id)
        if not atual or atual.get("status") != "IGNORADA_IA":
            ignorados_fora.append(item_id)
            continue
        descartar_nota_recebida(item_id, "nao_cobranca", "Confirmado: ignorado pela IA.", operador)
        try:
            registrar_feedback_extracao(
                item_id, "ignorado_confirmado", motivo="nao_cobranca",
                provedor=str((atual.get("dados") or {}).get("emissorNome") or ""), operador=operador,
                extraidos=atual.get("dados") or {}, finais={"decisao": "ignorar", "confirmadoPor": operador},
            )
        except sqlite3.Error:
            app.logger.exception("Não foi possível registrar o feedback do ignorado %s.", item_id)
        confirmados.append(item_id)
    log_event("ignorados_confirmados", {"ids": confirmados, "operador": operador})
    return jsonify({"ok": True, "confirmados": confirmados, "naoEncontrados": ignorados_fora})


@app.patch("/api/notas-recebidas/<item_id>/resgatar")
def resgatar_ignorado_route(item_id: str):
    """A IA errou: o documento volta para a caixa. Vira exemplo rotulado (a IA ignorou uma cobrança)."""
    operador = _autor((request.get_json(silent=True) or {}).get("operador"))
    atual = get_nota_recebida(item_id)
    try:
        item = resgatar_ignorado(item_id, operador)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    try:
        registrar_feedback_extracao(
            item_id, "ignorado_resgatado", motivo="ia_ignorou_cobranca",
            provedor=str((atual.get("dados") or {}).get("emissorNome") or ""), operador=operador,
            extraidos=atual.get("dados") or {}, finais={"decisao": "importar", "resgatadoPor": operador},
        )
    except sqlite3.Error:
        app.logger.exception("Não foi possível registrar o feedback do resgate %s.", item_id)
    log_event("ignorado_resgatado", {"notaRecebidaId": item_id, "operador": operador})
    return jsonify({"ok": True, "item": _serialize_nota_recebida_api(item)})


@app.patch("/api/notas-recebidas/<item_id>/analise")
def colocar_em_analise_route(item_id: str):
    """Nota em dúvida: fica em EM_ANALISE (fora da fila de associação) até o operador decidir."""
    payload = request.get_json(silent=True) or {}
    observacao = str(payload.get("observacao") or "").strip()
    operador = _autor(payload.get("operador"))
    try:
        item = colocar_em_analise(item_id, observacao, operador)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    log_event("nota_recebida_em_analise", {"notaRecebidaId": item_id, "operador": operador, "observacao": observacao[:200]})
    return jsonify({"ok": True, "item": _serialize_nota_recebida_api(item)})


@app.patch("/api/notas-recebidas/<item_id>/liberar")
def retirar_de_analise_route(item_id: str):
    operador = _autor((request.get_json(silent=True) or {}).get("operador"))
    try:
        item = retirar_de_analise(item_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    if not item:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    log_event("nota_recebida_liberada", {"notaRecebidaId": item_id, "operador": operador})
    return jsonify({"ok": True, "item": _serialize_nota_recebida_api(item)})


@app.post("/api/notas-recebidas/<item_id>/confirmar-etiqueta")
def confirmar_etiqueta_nota_recebida_route(item_id: str):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("ok"), bool):
        return jsonify({"ok": False, "error": "Informe o resultado da operação Gmail em 'ok'."}), 400
    current = get_nota_recebida(item_id)
    if not current:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    if current.get("status") != "ASSOCIADA" or not current.get("etiqueta_gmail"):
        return jsonify({"ok": False, "error": "A nota precisa estar associada antes de confirmar a etiqueta Gmail."}), 409
    result = confirmar_etiqueta_nota_recebida(
        item_id, payload["ok"], str(payload.get("erro") or "")[:500],
    )
    if not result:
        return jsonify({"ok": False, "error": "Nota recebida não encontrada."}), 404
    return jsonify({"ok": True, "item": _serialize_nota_recebida_api(result)})


def _pode(permissao: str) -> bool:
    """Permissão de quem chama (sem SIGP_API_KEY, em desenvolvimento, tudo é liberado)."""
    if not API_KEY:
        return True
    quem = getattr(g, "acesso", None) or {}
    return quem.get("perfil") == acesso.ADMIN or permissao in (quem.get("permissoes") or [])


# Campos com rede e IPs (o atual "redes" e os antigos, que podem existir no registro bruto "dados").
_CAMPOS_REDE = ("redes", "ipWireguard", "ipWinbox", "ip", "gateway")


def _ocultar_rede(local: Dict[str, Any]) -> Dict[str, Any]:
    """Rede e IPs só para quem tem "rede.ver"; para os demais a lista vem vazia e marcada como restrita
    (também no registro bruto "dados")."""
    if _pode("rede.ver"):
        return local
    limpo = {k: v for k, v in local.items() if k not in _CAMPOS_REDE}
    if isinstance(local.get("dados"), dict):
        limpo["dados"] = {k: v for k, v in local["dados"].items() if k not in _CAMPOS_REDE}
    return {**limpo, "redes": [], "redesOcultas": True}


@app.get("/api/locais")
def get_locais():
    tipo = str(request.args.get("tipo") or "").strip().lower()
    if tipo and tipo not in LOCAL_TIPOS:
        return jsonify({"ok": False, "error": "Tipo de local inválido."}), 400
    return jsonify({"items": [_ocultar_rede(l) for l in list_locais(tipo, request.args.get("inativos") == "1")]})


@app.get("/api/base-conhecimento")
def base_conhecimento_route():
    """Base de conhecimento das unidades (formato RAG-ready), gerada do banco na hora. Rede e IPs só com "rede.ver"."""
    from flask import Response
    base = base_conhecimento.gerar(list_locais(), _pode("rede.ver"))
    corpo = json.dumps(base, ensure_ascii=False, indent=2)
    if request.args.get("baixar") == "1":
        return Response(corpo, mimetype="application/json; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename=base_conhecimento_unidades_{base['data_geracao']}.json"})
    return Response(corpo, mimetype="application/json; charset=utf-8")


@app.get("/api/cadastro/correcoes")
def cadastro_correcoes_route():
    """Prévia das correções: unificar nomes de provedor, dia de vencimento (com sugestão) e unidades inválidas."""
    return jsonify({"ok": True, **correcoes_cadastro.propostas(list_locais(), list_notas_recebidas(), list_nota_lancadas(), list_faturas_locais())})


def _corrigir(tipo: str, executar):
    """Backup do banco antes, executa, registra o que mudou (evento) e devolve o resumo."""
    try:
        backup = saude_banco.fazer_backup(Path(_database.DB_PATH), _backup_dir())
    except (RuntimeError, sqlite3.Error, OSError) as erro:
        return jsonify({"ok": False, "error": f"Backup antes da correção falhou; nada foi alterado. {str(erro)[:200]}"}), 500
    feitos = executar(request.get_json(silent=True) or {})
    quem = (getattr(g, "acesso", None) or {})
    log_event("correcao_cadastro", {"tipo": tipo, "quem": quem.get("usuario") or quem.get("nome") or "", "itens": feitos[:200] if isinstance(feitos, list) else feitos})
    return jsonify({"ok": True, "aplicados": len(feitos) if isinstance(feitos, list) else int(bool(feitos)), "itens": feitos, "backup": backup["arquivo"]})


@app.post("/api/cadastro/correcoes/unificar")
def cadastro_unificar_route():
    return _corrigir("unificar", lambda d: correcoes_cadastro.unificar(d.get("itens") or []))


@app.post("/api/cadastro/correcoes/vencimento")
def cadastro_vencimento_route():
    return _corrigir("vencimento", lambda d: correcoes_cadastro.preencher_vencimento(d.get("itens") or []))


@app.post("/api/cadastro/correcoes/desativar")
def cadastro_desativar_route():
    local = get_local(str((request.get_json(silent=True) or {}).get("localId") or ""))
    if not local or base_conhecimento.unidade_valida(local):
        return jsonify({"ok": False, "error": "Só unidades inválidas (nome de cabeçalho de planilha) podem ser desativadas aqui."}), 400
    return _corrigir("desativar", lambda d: [x for x in [correcoes_cadastro.desativar_unidade(str(d.get("localId")))] if x])


@app.get("/api/base-conhecimento/qualidade")
def base_conhecimento_qualidade_route():
    return jsonify({"ok": True, **base_conhecimento.qualidade(list_locais())})


@app.get("/api/marcadores")
def marcadores_route():
    """Catálogo de marcadores e grupos, com quantos e quais locais (ativos e válidos) estão em cada um."""
    return jsonify({"ok": True, "items": marcadores.com_contagem(list_locais()), "camposRegra": sorted(marcadores.CAMPOS_REGRA)})


def _salvar_marcador(marcador_id: str = ""):
    try:
        item = marcadores.salvar(request.get_json(silent=True) or {}, marcador_id or None)
    except LookupError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 404
    except ValueError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 400
    log_event("marcador_salvo", {"id": item["id"], "nome": item["nome"], "tipo": item["tipo"], "quem": _autor("")})
    return jsonify({"ok": True, "item": item}), (200 if marcador_id else 201)


@app.post("/api/marcadores")
def criar_marcador_route():
    return _salvar_marcador()


@app.put("/api/marcadores/<marcador_id>")
def editar_marcador_route(marcador_id: str):
    return _salvar_marcador(marcador_id)


@app.delete("/api/marcadores/<marcador_id>")
def excluir_marcador_route(marcador_id: str):
    try:
        feito = marcadores.excluir(marcador_id)
    except LookupError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 404
    log_event("marcador_excluido", {"id": marcador_id, **feito, "quem": _autor("")})
    return jsonify({"ok": True, **feito})


@app.post("/api/marcadores/previa")
def previa_grupo_route():
    """Quais locais entrariam num grupo com esta regra (antes de salvar)."""
    try:
        return jsonify({"ok": True, **marcadores.previa(list_locais(), (request.get_json(silent=True) or {}).get("regra"))})
    except ValueError as erro:
        return jsonify({"ok": False, "error": str(erro)}), 400


@app.get("/api/locais/item/<local_id>")
def get_local_route(local_id: str):
    local = get_local(local_id)
    if not local:
        return jsonify({"ok": False, "error": "Local não encontrado."}), 404
    return jsonify({"ok": True, "item": _ocultar_rede(local)})


@app.put("/api/locais/<tipo>")
def put_locais(tipo: str):
    """Sincroniza o retrato completo de um tipo de local (enviado pela interface ou por integração)."""
    tipo = tipo.strip().lower()
    if tipo not in LOCAL_TIPOS:
        return jsonify({"ok": False, "error": "Tipo de local inválido."}), 400
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "Envie {'items': [...]}."}), 400
    # Nome antigo de provedor já unificado (Qualidade do cadastro) vira o nome novo: cópia antiga da tela não desfaz.
    items = correcoes_cadastro.aplicar_mapa_nomes(items)
    # Marcadores com a grafia do catálogo (aceita apelido); renomeado/excluído não volta; novo entra no catálogo.
    items = marcadores.normalizar_itens(items)
    # Linha "Nota lançada" que a associação do Gmail punha no local (id "gmail-...") é nota disponível: não volta.
    items = [notas_disponiveis.limpar_notas_fiscais_do_local(i) if isinstance(i, dict) else i for i in items]
    # Unidade inválida já desativada (cabeçalho de planilha) não volta por uma cópia antiga da tela.
    inativas = {str(l["id"]) for l in list_locais(tipo, True) if not l.get("ativo")}
    items = [i for i in items if not (isinstance(i, dict) and str(i.get("id")) in inativas and not base_conhecimento.unidade_valida(i))]
    if not _pode("rede.ver"):
        # Quem não vê rede e IPs não pode apagá-los nem alterá-los: mantém o que está gravado.
        atuais = {str(l["id"]): {k: l[k] for k in _CAMPOS_REDE if k in l} for l in list_locais(tipo, True)}
        items = [{**{k: v for k, v in i.items() if k not in _CAMPOS_REDE}, "redes": [], **atuais.get(str(i.get("id")), {})}
                 if isinstance(i, dict) else i for i in items]
        for i in items:
            if isinstance(i, dict):
                i.pop("redesOcultas", None)
    return jsonify({"ok": True, **sync_locais(tipo, [item for item in items if isinstance(item, dict)])})


@app.post("/api/locais/<tipo>/item")
def criar_local_route(tipo: str):
    tipo = tipo.strip().lower()
    if tipo not in LOCAL_TIPOS:
        return jsonify({"ok": False, "error": "Tipo de local inválido."}), 400
    payload = request.get_json(silent=True) or {}
    nome = str(payload.get("nome") or "").strip()
    cidade = str(payload.get("cidade") or "").strip()
    if not nome or not cidade or len(nome) > 160 or len(cidade) > 120:
        return jsonify({"ok": False, "error": "Informe o nome do local (até 160 caracteres) e uma cidade válida (até 120 caracteres)."}), 400
    try:
        item = create_local(tipo, nome, cidade)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 409
    return jsonify({"ok": True, "item": item}), 201


@app.get("/api/app-state")
def get_app_state_route():
    requested = [key for key in request.args.get("keys", "").split(",") if key]
    if any(key not in APP_STATE_KEYS for key in requested):
        return jsonify({"ok": False, "error": "Uma ou mais chaves de dados são inválidas."}), 400
    keys = requested or sorted(APP_STATE_KEYS)
    return jsonify({"items": get_app_state(keys)})


@app.put("/api/app-state/<state_key>")
def put_app_state_route(state_key: str):
    if state_key not in APP_STATE_KEYS:
        return jsonify({"ok": False, "error": "Chave de dados inválida."}), 400
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "value" not in payload:
        return jsonify({"ok": False, "error": "Envie o campo 'value' em JSON."}), 400
    try:
        save_app_state(state_key, payload["value"])
    except (TypeError, ValueError) as error:
        return jsonify({"ok": False, "error": f"Os dados não podem ser serializados: {error}"}), 400
    return jsonify({"ok": True})


@app.delete("/api/app-state/<state_key>")
def delete_app_state_route(state_key: str):
    if state_key not in APP_STATE_KEYS:
        return jsonify({"ok": False, "error": "Chave de dados inválida."}), 400
    delete_app_state(state_key)
    return jsonify({"ok": True})


def _parse_iso_date(value: str, default: date) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date() if value else default


def _lista_alertas(today: date, window: int, tipos=None) -> List[Dict[str, Any]]:
    # Local excluído na tela fica inativo (o histórico é preservado): suas notas não geram alerta.
    excluidos = {str(item["id"]) for item in list_locais(incluir_inativos=True) if not item.get("ativo")}
    notas = [note for note in list_nota_lancadas() if str(note.get("entidade_id") or "") not in excluidos]
    recebidas = list_notas_recebidas()
    locais = list_locais()
    itens = build_alerts(locais, notas, list_nota_pagas(), list_conciliacoes(), today, window, tipos,
                         received_notes=recebidas, ultima_leitura=fatura_esperada.ultima_leitura_gmail(recebidas))
    # Regional do local (marcador "Regional ..."): o resumo diário agrupa por ela; só leitura, nada é gravado.
    regional = {str(l["id"]): marcadores.regional(l.get("marcadores") or []) for l in locais}
    for item in itens:
        if item.get("entidadeId"):
            item["regional"] = regional.get(str(item["entidadeId"]), "")
    return itens


@app.get("/api/alertas")
def get_alertas():
    try:
        today = _parse_iso_date(str(request.args.get("hoje") or "").strip(), date.today())
        window = max(0, min(90, int(request.args.get("dias") or 7)))
    except ValueError:
        return jsonify({"ok": False, "error": "Parâmetros inválidos (hoje=AAAA-MM-DD, dias=0..90)."}), 400
    tipos = {item.strip() for item in str(request.args.get("tipo") or "").split(",") if item.strip()} or None
    items = _lista_alertas(today, window, tipos)
    resumo: Dict[str, int] = {}
    for item in items:
        resumo[item["status"]] = resumo.get(item["status"], 0) + 1
    return jsonify({"ok": True, "hoje": today.isoformat(), "dias": window, "total": len(items), "resumo": resumo, "items": items})


@app.get("/api/analises")
def get_analises():
    escopo = str(request.args.get("escopo") or "").strip().upper()
    status_validacao = str(request.args.get("status") or "").strip().upper()
    try:
        limite = max(1, min(100, int(request.args.get("limite") or 20)))
    except ValueError:
        limite = 20
    return jsonify({"items": list_analises(escopo, limite, status_validacao)})


@app.post("/api/analises")
def post_analise():
    """Resultado de análise gravado pelo n8n. SIG com ``dados.requerValidacao`` fica PENDENTE para o gerente."""
    payload = request.get_json(silent=True) or {}
    escopo = str(payload.get("escopo") or "").strip().upper()
    conteudo = str(payload.get("conteudo") or "").strip()
    if escopo not in {"SIG", "SIE"} or not conteudo:
        return jsonify({"ok": False, "error": "Informe escopo (SIG ou SIE) e conteudo."}), 400
    dados = payload.get("dados") if isinstance(payload.get("dados"), dict) else {}
    status_validacao = "PENDENTE" if escopo == "SIG" and dados.get("requerValidacao") else ""
    item = save_analise(
        escopo, conteudo, str(payload.get("titulo") or ""), str(payload.get("referencia") or ""),
        dados, str(payload.get("modelo") or ""), str(payload.get("origem") or "n8n"), status_validacao,
    )
    return jsonify({"ok": True, "item": item})


@app.post("/api/sig/decisoes")
def post_decisao_gerente():
    """Decisão do gerente na aba SIG (C-02). validar e corrigir seguem para a etapa executiva (SIE) no n8n;
    devolver encerra o ciclo de análise com a justificativa. O status da conciliação não muda (regra do SIGp, D13)."""
    payload = request.get_json(silent=True) or {}
    analise_id = str(payload.get("analiseId") or "").strip()
    acao = str(payload.get("acao") or "").strip().lower()
    justificativa = str(payload.get("justificativa") or "").strip()
    usuario = _autor(payload.get("usuario"))
    conteudo_corrigido = str(payload.get("conteudoCorrigido") or "").strip()
    if not analise_id or acao not in {"validar", "corrigir", "devolver"}:
        return jsonify({"ok": False, "error": "Informe a análise e a ação (validar, corrigir ou devolver)."}), 400
    if not usuario:
        return jsonify({"ok": False, "error": "Informe o usuário que decidiu (auditoria)."}), 400
    if acao in {"corrigir", "devolver"} and len(justificativa) < 5:
        return jsonify({"ok": False, "error": "Explique o motivo para corrigir ou devolver (mínimo 5 caracteres)."}), 400
    if acao == "corrigir" and len(conteudo_corrigido) < 5:
        return jsonify({"ok": False, "error": "Informe a análise corrigida."}), 400
    try:
        resultado = registrar_decisao_gerente(analise_id, acao, justificativa, usuario, conteudo_corrigido)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    if not resultado:
        return jsonify({"ok": False, "error": "Análise não encontrada."}), 404
    analise, decisao = resultado["analise"], resultado["decisao"]
    log_event("decisao_gerente", {"analiseId": analise_id, "acao": acao, "usuario": usuario})
    # O n8n recebe a decisão pela mesma fila de eventos (reenvio automático se estiver fora do ar).
    events.emit("decisao_gerente", {
        "decisao": {k: decisao[k] for k in ("id", "acao", "status", "justificativa", "conteudo_corrigido", "usuario", "created_at")},
        "analise": {k: analise.get(k) for k in ("id", "titulo", "referencia", "conteudo", "modelo", "created_at")},
        "resumo": (analise.get("dados") or {}),
    })
    return jsonify({"ok": True, "analise": analise, "decisao": decisao})


@app.get("/api/sig/decisoes")
def get_decisoes_gerente():
    return jsonify({"items": list_decisoes_gerente(str(request.args.get("analiseId") or "").strip())})


@app.get("/api/sie/resumo")
def get_sie_summary():
    default_start, default_end = default_period()
    try:
        start = _parse_iso_date(str(request.args.get("inicio") or "").strip(), date.fromisoformat(default_start))
        end = _parse_iso_date(str(request.args.get("fim") or "").strip(), date.fromisoformat(default_end))
    except ValueError:
        return jsonify({"ok": False, "error": "Informe datas válidas no formato AAAA-MM-DD."}), 400
    if end < start or (end - start).days > 1100:
        return jsonify({"ok": False, "error": "Período inválido (máximo de 36 meses)."}), 400
    # C-04: a SIE conta só ciclos fechados que o gerente validou na aba SIG.
    validacoes = validacao_por_nota(list_analises("SIG", 100000))
    result = build_sie_summary(list_nota_lancadas(), list_conciliacoes(), start.isoformat(), end.isoformat(), validacoes)
    received_documents = []
    seen_received_notes = set()
    for item in list_notas_recebidas():
        if item.get("status") != "ASSOCIADA" or not item.get("nota_lancada_id"):
            continue
        note = get_nota_lancada(str(item["nota_lancada_id"]))
        if not note:
            continue
        reference = str(note.get("data_emissao") or item.get("recebida_em") or "")[:10]
        try:
            reference_date = date.fromisoformat(reference)
        except ValueError:
            continue
        if not start <= reference_date <= end:
            continue
        if note["id"] in seen_received_notes:
            continue
        seen_received_notes.add(note["id"])
        related = list_conciliacoes_da_nota(note["id"])
        latest = max(related, key=lambda row: str(row.get("updated_at") or ""), default=None)
        local = get_local(str(note.get("entidade_id") or ""))
        received_documents.append({
            "id": item["id"],
            "nomeArquivo": item["nome_arquivo"],
            "notaLancadaId": note["id"],
            "local": local,
            "provedor": note.get("provedor_nome") or "",
            "numero": note.get("numero") or "",
            "valor": note.get("valor_total") or 0,
            "dataEmissao": note.get("data_emissao") or "",
            "dataVencimento": note.get("data_vencimento") or "",
            "statusFluxo": (latest or {}).get("status") or "AGUARDANDO_PAGAMENTO",
            "etiquetaStatus": item.get("etiqueta_status") or "",
        })
    return jsonify({
        "ok": True,
        **result,
        "notasRecebidas": received_documents,
        "analises": list_analises("SIE", 5),
    })


@app.get("/api/eventos")
def get_eventos():
    return jsonify({"items": list_eventos(str(request.args.get("status") or "").strip().upper())})


@app.post("/api/eventos/reenviar")
def post_eventos_reenviar():
    if not events.webhook_url():
        return jsonify({"ok": False, "error": "SIGP_N8N_EVENTOS_URL não configurada."}), 400
    return jsonify({"ok": True, **events.retry_pending()})


def main() -> None:
    init_db()
    host = os.environ.get("SIGP_HOST", "127.0.0.1")
    port = int(os.environ.get("SIGP_PORT", "5001"))
    if os.environ.get("SIGP_DEBUG", "0") == "1":
        app.run(host=host, port=port, debug=True)
        return
    from waitress import serve
    print(f"SIGp API em http://{host}:{port} (waitress)", flush=True)
    serve(app, host=host, port=port, threads=8)


if __name__ == "__main__":
    main()
