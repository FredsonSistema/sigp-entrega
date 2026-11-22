from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.campos import VALOR_PADRAO, eh_padrao, motivo_chave_invalida, motivo_numero_invalido
from backend.provedores import competencia, mesma_empresa

DB_DIR = Path(__file__).resolve().parent / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "sigp.db"


class DuplicateDocumentError(ValueError):
    def __init__(self, existing_id: str):
        super().__init__(f"Documento duplicado; já existe o registro {existing_id}.")
        self.existing_id = existing_id


def _normalize_provider_name(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in decomposed if char.isalnum() and not unicodedata.combining(char))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.execute("PRAGMA synchronous = FULL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS notas_lancadas (
            id TEXT PRIMARY KEY,
            entidade_tipo TEXT DEFAULT 'agencia',
            entidade_id TEXT,
            chave TEXT,
            numero TEXT,
            serie TEXT,
            provedor_nome TEXT,
            local_nome TEXT,
            local_cidade TEXT,
            municipio_codigo TEXT DEFAULT '',
            valor_total REAL,
            data_emissao TEXT,
            data_vencimento TEXT,
            status TEXT DEFAULT 'PENDENTE',
            observacao TEXT,
            servicos_json TEXT NOT NULL DEFAULT '[]',
            origem TEXT DEFAULT 'manual',
            arquivo_origem TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS notas_pagas (
            id TEXT PRIMARY KEY,
            entidade_tipo TEXT DEFAULT 'agencia',
            entidade_id TEXT,
            chave TEXT,
            numero TEXT,
            serie TEXT,
            provedor_nome TEXT,
            local_nome TEXT,
            local_cidade TEXT,
            municipio_codigo TEXT DEFAULT '',
            valor_total REAL,
            valor_pago REAL,
            data_emissao TEXT,
            data_pagamento TEXT,
            status TEXT DEFAULT 'PENDENTE',
            observacao TEXT,
            servicos_json TEXT NOT NULL DEFAULT '[]',
            origem TEXT DEFAULT 'manual',
            arquivo_origem TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS conciliacoes (
            id TEXT PRIMARY KEY,
            nota_lancada_id TEXT,
            nota_paga_id TEXT,
            chave_match INTEGER DEFAULT 0,
            valor_match INTEGER DEFAULT 0,
            local_match INTEGER DEFAULT 0,
            servicos_match INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDENTE',
            observacao TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS faturas_provedores (
            id TEXT PRIMARY KEY,
            nota_lancada_id TEXT NOT NULL UNIQUE,
            nome_arquivo TEXT NOT NULL,
            arquivo_storage TEXT NOT NULL,
            dados_extracao_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(nota_lancada_id) REFERENCES notas_lancadas(id)
        );

        CREATE TABLE IF NOT EXISTS faturas_locais (
            id TEXT PRIMARY KEY,
            entidade_tipo TEXT NOT NULL,
            entidade_id TEXT NOT NULL,
            provedor_id TEXT NOT NULL DEFAULT '',
            provedor_nome TEXT NOT NULL DEFAULT '',
            nota_lancada_id TEXT NOT NULL DEFAULT '',
            nome_arquivo TEXT NOT NULL,
            arquivo_storage TEXT NOT NULL,
            dados_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notas_recebidas (
            id TEXT PRIMARY KEY,
            gmail_message_id TEXT NOT NULL,
            gmail_attachment_id TEXT NOT NULL DEFAULT 'default',
            nota_lancada_id TEXT NOT NULL DEFAULT '',
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
            etiqueta_erro TEXT NOT NULL DEFAULT '',
            operador TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(gmail_message_id, gmail_attachment_id)
        );
        CREATE INDEX IF NOT EXISTS idx_notas_recebidas_status
            ON notas_recebidas(status, recebida_em DESC, created_at DESC);
        -- Exemplos rotulados pelo uso (associação e descarte). Base para medir e melhorar a extração/LLM.
        -- Fica só neste banco local; não é enviado a serviço externo.
        CREATE TABLE IF NOT EXISTS extracao_feedback (
            id TEXT PRIMARY KEY,
            nota_recebida_id TEXT NOT NULL,
            tipo TEXT NOT NULL,                       -- 'associada' | 'descartada'
            motivo TEXT NOT NULL DEFAULT '',
            provedor TEXT NOT NULL DEFAULT '',
            entidade_tipo TEXT NOT NULL DEFAULT '',
            entidade_id TEXT NOT NULL DEFAULT '',
            operador TEXT NOT NULL DEFAULT '',
            dados_extraidos_json TEXT NOT NULL DEFAULT '{}',   -- o que a extração entregou
            dados_finais_json TEXT NOT NULL DEFAULT '{}',      -- o que o usuário confirmou
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_extracao_feedback_nota
            ON extracao_feedback(nota_recebida_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_faturas_locais_entidade
            ON faturas_locais(entidade_tipo, entidade_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notas_lancadas_chave
            ON notas_lancadas(chave);
        CREATE INDEX IF NOT EXISTS idx_notas_pagas_chave
            ON notas_pagas(chave);
        CREATE INDEX IF NOT EXISTS idx_conciliacoes_par
            ON conciliacoes(nota_lancada_id, nota_paga_id);

        CREATE TABLE IF NOT EXISTS api_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT,
            payload TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS locais (
            id TEXT PRIMARY KEY,
            tipo TEXT NOT NULL,
            nome TEXT NOT NULL DEFAULT '',
            cidade TEXT NOT NULL DEFAULT '',
            endereco TEXT NOT NULL DEFAULT '',
            vencimento_fatura TEXT NOT NULL DEFAULT '',
            provedores_json TEXT NOT NULL DEFAULT '[]',
            dados_json TEXT NOT NULL DEFAULT '{}',
            ativo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_locais_tipo ON locais(tipo, ativo);

        CREATE TABLE IF NOT EXISTS app_state (
            state_key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS correcoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_tipo TEXT NOT NULL,
            documento_id TEXT NOT NULL,
            campo TEXT NOT NULL,
            valor_anterior TEXT,
            valor_novo TEXT,
            usuario TEXT NOT NULL DEFAULT '',
            motivo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_correcoes_documento ON correcoes(documento_tipo, documento_id);

        CREATE TABLE IF NOT EXISTS analises (
            id TEXT PRIMARY KEY,
            escopo TEXT NOT NULL,
            referencia TEXT NOT NULL DEFAULT '',
            titulo TEXT NOT NULL DEFAULT '',
            conteudo TEXT NOT NULL,
            dados_json TEXT NOT NULL DEFAULT '{}',
            modelo TEXT NOT NULL DEFAULT '',
            origem TEXT NOT NULL DEFAULT 'n8n',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_analises_escopo ON analises(escopo, created_at DESC);

        CREATE TABLE IF NOT EXISTS eventos_saida (
            id TEXT PRIMARY KEY,
            evento TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDENTE',
            tentativas INTEGER NOT NULL DEFAULT 0,
            ultimo_erro TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            enviado_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_eventos_saida_status ON eventos_saida(status, created_at);
        """
    )
    for table in ("notas_lancadas", "notas_pagas"):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "servicos_json" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN servicos_json TEXT NOT NULL DEFAULT '[]'")
        if "municipio_codigo" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN municipio_codigo TEXT NOT NULL DEFAULT ''")
        if "sistema_origem" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN sistema_origem TEXT NOT NULL DEFAULT ''")
        if "id_externo" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN id_externo TEXT NOT NULL DEFAULT ''")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_externo ON {table}(sistema_origem, id_externo)")
    reconciliation_columns = {row["name"] for row in conn.execute("PRAGMA table_info(conciliacoes)").fetchall()}
    if "servicos_match" not in reconciliation_columns:
        conn.execute("ALTER TABLE conciliacoes ADD COLUMN servicos_match INTEGER NOT NULL DEFAULT 0")
    if "fatura_id" not in reconciliation_columns:
        conn.execute("ALTER TABLE conciliacoes ADD COLUMN fatura_id TEXT NOT NULL DEFAULT ''")
    if "fatura_match" not in reconciliation_columns:
        conn.execute("ALTER TABLE conciliacoes ADD COLUMN fatura_match INTEGER")
    # Fase C: análise SIG aguarda o gerente (validar / corrigir / devolver) antes de ir para a SIE.
    analysis_columns = {row["name"] for row in conn.execute("PRAGMA table_info(analises)").fetchall()}
    for column in ("status_validacao", "validado_em", "validado_por"):
        if column not in analysis_columns:
            conn.execute(f"ALTER TABLE analises ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS decisoes_gerente (
            id TEXT PRIMARY KEY,
            analise_id TEXT NOT NULL,
            referencia TEXT NOT NULL DEFAULT '',
            acao TEXT NOT NULL,                  -- validar | corrigir | devolver
            status TEXT NOT NULL,                -- VALIDADA | CORRIGIDA | DEVOLVIDA
            justificativa TEXT NOT NULL DEFAULT '',
            conteudo_corrigido TEXT NOT NULL DEFAULT '',
            usuario TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decisoes_gerente_analise ON decisoes_gerente(analise_id, created_at DESC)")
    invoice_columns = {row["name"] for row in conn.execute("PRAGMA table_info(faturas_locais)").fetchall()}
    if "provedor_id" not in invoice_columns:
        conn.execute("ALTER TABLE faturas_locais ADD COLUMN provedor_id TEXT NOT NULL DEFAULT ''")
    if "provedor_nome" not in invoice_columns:
        conn.execute("ALTER TABLE faturas_locais ADD COLUMN provedor_nome TEXT NOT NULL DEFAULT ''")
    # Nota disponível: documento que chegou do provedor (Gmail) e foi associado ao local. Não é nota lançada:
    # nota lançada é só a do financeiro (Importar NF, WF-01). Quando o financeiro lança, as duas se ligam.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notas_disponiveis (
            id TEXT PRIMARY KEY, entidade_tipo TEXT NOT NULL, entidade_id TEXT NOT NULL,
            chave TEXT NOT NULL DEFAULT '', numero TEXT NOT NULL DEFAULT '', serie TEXT NOT NULL DEFAULT '',
            provedor_nome TEXT NOT NULL DEFAULT '', local_nome TEXT NOT NULL DEFAULT '', local_cidade TEXT NOT NULL DEFAULT '',
            valor_total REAL NOT NULL DEFAULT 0, data_emissao TEXT NOT NULL DEFAULT '', data_vencimento TEXT NOT NULL DEFAULT '',
            observacao TEXT NOT NULL DEFAULT '', servicos_json TEXT NOT NULL DEFAULT '[]',
            nota_lancada_id TEXT NOT NULL DEFAULT '', origem TEXT NOT NULL DEFAULT 'gmail', id_externo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notas_disponiveis_local ON notas_disponiveis(entidade_tipo, entidade_id, data_vencimento)")
    if "nota_disponivel_id" not in invoice_columns:
        conn.execute("ALTER TABLE faturas_locais ADD COLUMN nota_disponivel_id TEXT NOT NULL DEFAULT ''")
    received_invoice_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(notas_recebidas)").fetchall()
    }
    if "etiqueta_erro" not in received_invoice_columns:
        conn.execute("ALTER TABLE notas_recebidas ADD COLUMN etiqueta_erro TEXT NOT NULL DEFAULT ''")
        received_invoice_columns.add("etiqueta_erro")
    if "nota_lancada_id" not in received_invoice_columns:
        conn.execute("ALTER TABLE notas_recebidas ADD COLUMN nota_lancada_id TEXT NOT NULL DEFAULT ''")
    if "gmail_attachment_id" not in received_invoice_columns:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE notas_recebidas_migrated (
                id TEXT PRIMARY KEY,
                gmail_message_id TEXT NOT NULL,
                gmail_attachment_id TEXT NOT NULL DEFAULT 'default',
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
                etiqueta_erro TEXT NOT NULL DEFAULT '',
                operador TEXT NOT NULL DEFAULT '',
                nota_lancada_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(gmail_message_id, gmail_attachment_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO notas_recebidas_migrated (
                id, gmail_message_id, gmail_attachment_id, gmail_thread_id, assunto, remetente, recebida_em,
                nome_arquivo, arquivo_storage, dados_json, status, entidade_tipo, entidade_id, etiqueta_gmail,
                etiqueta_status, etiqueta_erro, operador, created_at, updated_at, nota_lancada_id
            )
            SELECT
                id, gmail_message_id, 'default', gmail_thread_id, assunto, remetente, recebida_em,
                nome_arquivo, arquivo_storage, dados_json, status, entidade_tipo, entidade_id, etiqueta_gmail,
                etiqueta_status, etiqueta_erro, operador, created_at, updated_at, nota_lancada_id
            FROM notas_recebidas
            """
        )
        conn.execute("DROP TABLE notas_recebidas")
        conn.execute("ALTER TABLE notas_recebidas_migrated RENAME TO notas_recebidas")
        conn.execute(
            "CREATE INDEX idx_notas_recebidas_status "
            "ON notas_recebidas(status, recebida_em DESC, created_at DESC)"
        )
    if "nota_disponivel_id" not in {row["name"] for row in conn.execute("PRAGMA table_info(notas_recebidas)").fetchall()}:
        conn.execute("ALTER TABLE notas_recebidas ADD COLUMN nota_disponivel_id TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_faturas_locais_provedor "
        "ON faturas_locais(entidade_tipo, entidade_id, provedor_id, created_at DESC)"
    )
    conn.commit()
    conn.close()
    # Perfis e permissões (backend/acesso.py): tabelas e grupos padrão.
    from backend import acesso
    acesso.garantir_tabelas()
    # Assistente da IA local (backend/assistente.py): perguntas, avaliações e o que ele aprendeu.
    from backend import assistente
    assistente.garantir_tabelas()
    # Marcadores e grupos de localidades (backend/marcadores.py): catálogo e migração dos marcadores antigos.
    from backend import marcadores
    marcadores.garantir_tabelas()
    # Cofre de chaves (backend/cofre.py): segredos de integração criptografados.
    from backend import cofre
    cofre.garantir_tabelas()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_row(row: sqlite3.Row) -> Dict[str, Any]:
    result = {key: row[key] for key in row.keys()}
    if "servicos_json" in result:
        try:
            result["servicos"] = json.loads(result.pop("servicos_json") or "[]")
        except json.JSONDecodeError:
            result["servicos"] = []
            result.pop("servicos_json", None)
    return result


def _so_data(valor: Any) -> str:
    """"2026-10-05T09:30:00-03:00" -> "2026-10-05" (datas ISO com horário vindas de XML/navegador)."""
    texto = str(valor or "").strip()
    return texto[:10] if re.match(r"^\d{4}-\d{2}-\d{2}T", texto) else texto


def _identificador_util(valor: Any) -> str:
    """Chave/número que identificam a nota; vazio quando é o padrão 999999999 (nunca é identidade fiscal)."""
    texto = str(valor or "").strip()
    return "" if eh_padrao(texto) else texto


def _identificador_invalido(campo: str, valor: Any) -> bool:
    texto = str(valor or "").strip()
    return bool(texto) and not eh_padrao(texto) and bool(
        motivo_chave_invalida(texto) if campo == "chave" else motivo_numero_invalido(texto)
    )


def _preservar_identificacao(conn: sqlite3.Connection, table: str, payload: Dict[str, Any]) -> None:
    """Atualização do mesmo registro (mesmo id): dado real vence o padrão.

    Se o que chegou para chave/número é vazio, padrão ou inválido (ex.: cópia do navegador com a chave de 41
    dígitos do XML, que o SIGp gravou como 999999999), mantém o que já está gravado.
    """
    existente = conn.execute(
        f"SELECT chave, numero, serie, provedor_nome, data_emissao FROM {table} WHERE id = ?", (str(payload["id"]),),
    ).fetchone()
    if not existente:
        return
    # Série, emitente e emissão vazios (cópia antiga do navegador) não apagam nem contradizem o gravado.
    for campo in ("serie", "provedor_nome", "data_emissao"):
        if not str(payload.get(campo) or "").strip() and str(existente[campo] or "").strip():
            payload[campo] = existente[campo]
    for campo in ("chave", "numero"):
        novo = payload.get(campo)
        antigo = str(existente[campo] or "").strip()
        if not antigo:
            continue
        if not _identificador_util(novo):
            payload[campo] = antigo  # vazio ou padrão não apaga o que está gravado
        elif campo == "numero" and eh_padrao(antigo) and _identificador_invalido(campo, novo):
            payload[campo] = antigo  # "número" que é valor/data/rótulo não substitui o padrão gravado


def _find_duplicate_document(
    conn: sqlite3.Connection,
    table: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    existing_id = str(payload["id"])
    existing = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (existing_id,)).fetchone()
    if existing:
        # Mesmo id = o mesmo registro sendo atualizado (o usuário corrigindo a própria nota). Só é "outro
        # documento" se um identificador real (chave/número, nunca o padrão 999999999) conflita ou se o local muda.
        # Emitente, série e emissão podem ser corrigidos no mesmo registro (ex.: nome fantasia -> razão social).
        for campo in ("chave", "numero"):
            antigo = _identificador_util(existing[campo]).casefold()
            novo = _identificador_util(payload[campo]).casefold()
            if antigo and novo and antigo != novo:
                raise DuplicateDocumentError(existing_id)
        old_local = (str(existing["entidade_tipo"] or "").strip().casefold(), str(existing["entidade_id"] or "").strip())
        new_local = (str(payload["entidade_tipo"] or "").strip().casefold(), str(payload["entidade_id"] or "").strip())
        if all(old_local) and all(new_local) and old_local != new_local:
            raise DuplicateDocumentError(existing_id)
        return None

    key = str(payload["chave"] or "").strip()
    if eh_padrao(key):
        key = ""  # valor padrão não identifica a nota: não pode gerar duplicidade
    if key:
        columns = "id, numero, serie, provedor_nome, data_emissao, entidade_tipo, entidade_id"
        if table == "notas_pagas":
            columns += ", data_pagamento, valor_pago"
        candidates = conn.execute(
            f"SELECT {columns} FROM {table} WHERE lower(trim(chave)) = lower(?) ORDER BY created_at",
            (key,),
        ).fetchall()
    else:
        number = str(payload["numero"] or "").strip()
        issuer = str(payload["provedor_nome"] or "").strip()
        if not number or not issuer or eh_padrao(number):
            return None
        columns = "id, numero, serie, provedor_nome, data_emissao, entidade_tipo, entidade_id"
        if table == "notas_pagas":
            columns += ", data_pagamento, valor_pago"
        date_column = "data_emissao"
        date_value = str(payload["data_emissao"] or "").strip()
        params = [
            number,
            str(payload["serie"] or "").strip(),
            issuer,
            str(payload["entidade_tipo"] or "").strip(),
            str(payload["entidade_id"] or "").strip(),
        ]
        if table == "notas_pagas":
            date_column = "data_pagamento"
            date_value = str(payload["data_pagamento"] or "").strip()
        candidates = conn.execute(
            f"""SELECT {columns}
                FROM {table}
                WHERE lower(trim(numero)) = lower(?)
                  AND lower(trim(serie)) = lower(?)
                  AND lower(trim(provedor_nome)) = lower(?)
                  AND lower(trim(entidade_tipo)) = lower(?)
                  AND trim(entidade_id) = ?
                  AND trim({date_column}) = ?""",
            (*params, date_value),
        ).fetchall()

    for candidate in candidates:
        if table == "notas_pagas":
            if (
                str(candidate["data_pagamento"] or "").strip()
                == str(payload["data_pagamento"] or "").strip()
                and abs(float(candidate["valor_pago"] or 0) - float(payload["valor_pago"] or 0)) < 0.01
            ):
                return str(candidate["id"])
            continue
        return str(candidate["id"])
    return None


def get_nota_lancada(nota_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM notas_lancadas WHERE id = ?", (nota_id,)).fetchone()
    conn.close()
    return serialize_row(row) if row else None


def get_nota_paga(nota_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM notas_pagas WHERE id = ?", (nota_id,)).fetchone()
    conn.close()
    return serialize_row(row) if row else None


def save_nota_lancada(dados: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    payload = {
        "id": dados.get("id") or dados.get("chave") or f"nf-lancada-{dados.get('numero') or 'manual'}",
        "entidade_tipo": dados.get("entidadeTipo") or dados.get("entidade_tipo") or "agencia",
        "entidade_id": dados.get("entidadeId") or dados.get("entidade_id") or "",
        "chave": dados.get("chave") or "",
        "numero": dados.get("numero") or "",
        "serie": dados.get("serie") or "",
        "provedor_nome": dados.get("provedorNome") or dados.get("provedor_nome") or "",
        "local_nome": dados.get("localNome") or dados.get("local_nome") or "",
        "local_cidade": dados.get("localCidade") or dados.get("local_cidade") or "",
        "municipio_codigo": dados.get("municipioCodigo") or dados.get("municipio_codigo") or "",
        "valor_total": float(dados.get("valorTotal") or dados.get("valor") or 0),
        "data_emissao": dados.get("dataEmissao") or dados.get("data_emissao") or "",
        "data_vencimento": dados.get("dataVencimento") or dados.get("data_vencimento") or "",
        "status": (dados.get("status") or "PENDENTE").upper(),
        "observacao": dados.get("observacao") or "",
        "servicos_json": json.dumps(dados.get("servicos") or [], ensure_ascii=False),
        "origem": dados.get("origem") or "manual",
        "arquivo_origem": dados.get("arquivoOrigem") or dados.get("arquivo_origem") or "",
        "sistema_origem": str(dados.get("sistemaOrigem") or dados.get("sistema_origem") or "").strip(),
        "id_externo": str(dados.get("idExterno") or dados.get("id_externo") or "").strip(),
        "created_at": dados.get("createdAt") or dados.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "updated_at": dados.get("updatedAt") or dados.get("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    payload["data_emissao"] = _so_data(payload["data_emissao"])
    payload["data_vencimento"] = _so_data(payload["data_vencimento"])
    # Serviço único sem valor (NFS-e nacional não traz valor por item): o valor do item é o total da nota.
    servicos = dados.get("servicos") if isinstance(dados.get("servicos"), list) else []
    if len(servicos) == 1 and isinstance(servicos[0], dict) and not servicos[0].get("valorTotal") and payload["valor_total"] > 0:
        servicos = [{**servicos[0], "valorTotal": payload["valor_total"]}]
        payload["servicos_json"] = json.dumps(servicos, ensure_ascii=False)
    conn.execute("BEGIN IMMEDIATE")
    _resolve_external_id(conn, "notas_lancadas", payload)
    _preservar_identificacao(conn, "notas_lancadas", payload)
    recorrencia = _aplicar_recorrencia(conn, payload)
    try:
        # Na recorrência a nota do mês é atualizada de propósito (datas e nome podem mudar): sem checagem de identidade.
        duplicate_id = None if recorrencia else _find_duplicate_document(conn, "notas_lancadas", payload)
    except DuplicateDocumentError:
        conn.rollback()
        conn.close()
        raise
    if duplicate_id:
        conn.rollback()
        conn.close()
        raise DuplicateDocumentError(duplicate_id)
    conn.execute(
        """
        INSERT INTO notas_lancadas (
            id, entidade_tipo, entidade_id, chave, numero, serie, provedor_nome,
            local_nome, local_cidade, municipio_codigo, valor_total, data_emissao, data_vencimento,
            status, observacao, servicos_json, origem, arquivo_origem, sistema_origem, id_externo, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            entidade_tipo = excluded.entidade_tipo,
            entidade_id = excluded.entidade_id,
            chave = excluded.chave,
            numero = excluded.numero,
            serie = excluded.serie,
            provedor_nome = excluded.provedor_nome,
            local_nome = excluded.local_nome,
            local_cidade = excluded.local_cidade,
            municipio_codigo = excluded.municipio_codigo,
            valor_total = excluded.valor_total,
            data_emissao = excluded.data_emissao,
            data_vencimento = excluded.data_vencimento,
            status = excluded.status,
            observacao = excluded.observacao,
            servicos_json = excluded.servicos_json,
            origem = excluded.origem,
            arquivo_origem = excluded.arquivo_origem,
            sistema_origem = excluded.sistema_origem,
            id_externo = excluded.id_externo,
            updated_at = excluded.updated_at
        """,
        (
            payload["id"], payload["entidade_tipo"], payload["entidade_id"], payload["chave"], payload["numero"],
            payload["serie"], payload["provedor_nome"], payload["local_nome"], payload["local_cidade"], payload["municipio_codigo"],
            payload["valor_total"], payload["data_emissao"], payload["data_vencimento"], payload["status"],
            payload["observacao"], payload["servicos_json"], payload["origem"], payload["arquivo_origem"],
            payload["sistema_origem"], payload["id_externo"], payload["created_at"], payload["updated_at"],
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM notas_lancadas WHERE id = ?", (payload["id"],)).fetchone()
    conn.close()
    result = serialize_row(row)
    if recorrencia:
        result["recorrencia"] = recorrencia
    return result


def _identificador_real(valor: Any) -> bool:
    texto = str(valor or "").strip()
    return bool(texto) and not eh_padrao(texto)


def _aplicar_recorrencia(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Regra das notas recorrentes na gravação direta (NFS-e no local, WF-01, Praxio/Globus).

    - Nota já existente regravada sem número/chave real: mantém os identificadores reais que ela tinha.
    - Nota NOVA sem número/chave real: se houver nota do mesmo local, empresa e mês, atualiza e substitui
      essa nota (mantendo seus identificadores reais e o nome do provedor) em vez de criar outra.
    Nota com número/chave real segue a identidade fiscal normal (pode ser outra cobrança no mesmo mês).
    Devolve a descrição da recorrência quando a nota do mês foi reaproveitada.
    """
    existente = conn.execute("SELECT * FROM notas_lancadas WHERE id = ?", (payload["id"],)).fetchone()
    if existente:
        for campo in ("numero", "chave"):
            if not _identificador_real(payload[campo]) and _identificador_real(existente[campo]):
                payload[campo] = existente[campo]
        return None
    if _identificador_real(payload["numero"]) or _identificador_real(payload["chave"]):
        return None
    alvo = encontrar_nota_da_competencia(
        conn, payload["entidade_tipo"], payload["entidade_id"], payload["provedor_nome"], payload["data_vencimento"],
    )
    if not alvo:
        return None
    id_original = payload["id"]
    payload["id"] = alvo["id"]
    payload["created_at"] = alvo["created_at"]
    for campo in ("numero", "chave", "serie"):
        if not _identificador_real(payload[campo]) and str(alvo[campo] or "").strip():
            payload[campo] = alvo[campo]
    payload["provedor_nome"] = alvo["provedor_nome"] or payload["provedor_nome"]
    return {"notaSubstituida": alvo["id"], "idRecebido": id_original, "competencia": competencia(payload["data_vencimento"])}


def save_nota_paga(dados: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    payload = {
        "id": dados.get("id") or dados.get("chave") or f"nf-paga-{dados.get('numero') or 'manual'}",
        "entidade_tipo": dados.get("entidadeTipo") or dados.get("entidade_tipo") or "agencia",
        "entidade_id": dados.get("entidadeId") or dados.get("entidade_id") or "",
        "chave": dados.get("chave") or "",
        "numero": dados.get("numero") or "",
        "serie": dados.get("serie") or "",
        "provedor_nome": dados.get("provedorNome") or dados.get("provedor_nome") or "",
        "local_nome": dados.get("localNome") or dados.get("local_nome") or "",
        "local_cidade": dados.get("localCidade") or dados.get("local_cidade") or "",
        "municipio_codigo": dados.get("municipioCodigo") or dados.get("municipio_codigo") or "",
        "valor_total": float(dados.get("valorTotal") or dados.get("valor") or 0),
        "valor_pago": float(dados.get("valorPago") or dados.get("valor_pago") or 0),
        "data_emissao": dados.get("dataEmissao") or dados.get("data_emissao") or "",
        "data_pagamento": dados.get("dataPagamento") or dados.get("data_pagamento") or "",
        "status": (dados.get("status") or "PENDENTE").upper(),
        "observacao": dados.get("observacao") or "",
        "servicos_json": json.dumps(dados.get("servicos") or [], ensure_ascii=False),
        "origem": dados.get("origem") or "manual",
        "arquivo_origem": dados.get("arquivoOrigem") or dados.get("arquivo_origem") or "",
        "sistema_origem": str(dados.get("sistemaOrigem") or dados.get("sistema_origem") or "").strip(),
        "id_externo": str(dados.get("idExterno") or dados.get("id_externo") or "").strip(),
        "created_at": dados.get("createdAt") or dados.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "updated_at": dados.get("updatedAt") or dados.get("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    payload["data_emissao"] = _so_data(payload["data_emissao"])
    payload["data_pagamento"] = _so_data(payload["data_pagamento"])
    conn.execute("BEGIN IMMEDIATE")
    _resolve_external_id(conn, "notas_pagas", payload)
    _preservar_identificacao(conn, "notas_pagas", payload)
    try:
        duplicate_id = _find_duplicate_document(conn, "notas_pagas", payload)
    except DuplicateDocumentError:
        conn.rollback()
        conn.close()
        raise
    if duplicate_id:
        conn.rollback()
        conn.close()
        raise DuplicateDocumentError(duplicate_id)
    conn.execute(
        """
        INSERT INTO notas_pagas (
            id, entidade_tipo, entidade_id, chave, numero, serie, provedor_nome,
            local_nome, local_cidade, municipio_codigo, valor_total, valor_pago, data_emissao, data_pagamento,
            status, observacao, servicos_json, origem, arquivo_origem, sistema_origem, id_externo, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            entidade_tipo = excluded.entidade_tipo,
            entidade_id = excluded.entidade_id,
            chave = excluded.chave,
            numero = excluded.numero,
            serie = excluded.serie,
            provedor_nome = excluded.provedor_nome,
            local_nome = excluded.local_nome,
            local_cidade = excluded.local_cidade,
            municipio_codigo = excluded.municipio_codigo,
            valor_total = excluded.valor_total,
            valor_pago = excluded.valor_pago,
            data_emissao = excluded.data_emissao,
            data_pagamento = excluded.data_pagamento,
            status = excluded.status,
            observacao = excluded.observacao,
            servicos_json = excluded.servicos_json,
            origem = excluded.origem,
            arquivo_origem = excluded.arquivo_origem,
            sistema_origem = excluded.sistema_origem,
            id_externo = excluded.id_externo,
            updated_at = excluded.updated_at
        """,
        (
            payload["id"], payload["entidade_tipo"], payload["entidade_id"], payload["chave"], payload["numero"],
            payload["serie"], payload["provedor_nome"], payload["local_nome"], payload["local_cidade"], payload["municipio_codigo"],
            payload["valor_total"], payload["valor_pago"], payload["data_emissao"], payload["data_pagamento"],
            payload["status"], payload["observacao"], payload["servicos_json"], payload["origem"], payload["arquivo_origem"],
            payload["sistema_origem"], payload["id_externo"], payload["created_at"], payload["updated_at"],
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM notas_pagas WHERE id = ?", (payload["id"],)).fetchone()
    conn.close()
    return serialize_row(row)


def list_nota_lancadas() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT n.*, (
            EXISTS(SELECT 1 FROM faturas_provedores f WHERE f.nota_lancada_id = n.id)
            OR EXISTS(SELECT 1 FROM faturas_locais fl WHERE fl.nota_lancada_id = n.id)
        ) AS fatura_anexada
        FROM notas_lancadas n
        ORDER BY n.updated_at DESC
        """
    ).fetchall()
    conn.close()
    return [serialize_row(row) for row in rows]


def get_fatura_provedor(nota_lancada_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM faturas_provedores WHERE nota_lancada_id = ?",
        (nota_lancada_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    result["dados_extracao"] = json.loads(result.pop("dados_extracao_json") or "{}")
    return result


def delete_fatura_provedor(nota_lancada_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, nota_lancada_id, nome_arquivo, arquivo_storage FROM faturas_provedores WHERE nota_lancada_id = ?",
        (nota_lancada_id,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM faturas_provedores WHERE nota_lancada_id = ?", (nota_lancada_id,))
        conn.commit()
    conn.close()
    return dict(row) if row else None


def save_fatura_provedor(
    nota_lancada_id: str,
    nome_arquivo: str,
    arquivo_storage: str,
    dados_extracao: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "id": f"fatura-{nota_lancada_id}",
        "nota_lancada_id": nota_lancada_id,
        "nome_arquivo": nome_arquivo,
        "arquivo_storage": arquivo_storage,
        "dados_extracao_json": json.dumps(dados_extracao, ensure_ascii=False),
        "created_at": now,
        "updated_at": now,
    }
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO faturas_provedores (
            id, nota_lancada_id, nome_arquivo, arquivo_storage,
            dados_extracao_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(nota_lancada_id) DO UPDATE SET
            nome_arquivo = excluded.nome_arquivo,
            arquivo_storage = excluded.arquivo_storage,
            dados_extracao_json = excluded.dados_extracao_json,
            updated_at = excluded.updated_at
        """,
        (
            payload["id"], payload["nota_lancada_id"], payload["nome_arquivo"],
            payload["arquivo_storage"], payload["dados_extracao_json"],
            payload["created_at"], payload["updated_at"],
        ),
    )
    conn.execute(
        """
        UPDATE notas_lancadas
        SET data_vencimento = ?, updated_at = ?
        WHERE id = ? AND (data_vencimento IS NULL OR data_vencimento = '')
        """,
        (str(dados_extracao.get("dataVencimento") or ""), now, nota_lancada_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM faturas_provedores WHERE nota_lancada_id = ?",
        (nota_lancada_id,),
    ).fetchone()
    conn.close()
    result = dict(row)
    result["dados_extracao"] = json.loads(result.pop("dados_extracao_json") or "{}")
    return result


def list_faturas_locais(entidade_tipo: str = "", entidade_id: str = "") -> List[Dict[str, Any]]:
    conn = get_connection()
    conditions = []
    params: list[str] = []
    if entidade_tipo:
        conditions.append("entidade_tipo = ?")
        params.append(entidade_tipo)
    if entidade_id:
        conditions.append("entidade_id = ?")
        params.append(entidade_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM faturas_locais {where} ORDER BY created_at DESC, rowid DESC",
        params,
    ).fetchall()
    conn.close()
    return [serialize_fatura_local(row) for row in rows]


def get_fatura_local(fatura_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM faturas_locais WHERE id = ?", (fatura_id,)).fetchone()
    conn.close()
    return serialize_fatura_local(row) if row else None


def link_fatura_local(fatura_id: str, nota_lancada_id: str, dados: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT nota_lancada_id FROM faturas_locais WHERE id = ?", (fatura_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        current_note_id = str(row["nota_lancada_id"] or "")
        if current_note_id and current_note_id != nota_lancada_id:
            conn.rollback()
            raise ValueError("A fatura já está vinculada a outra nota.")

        conn.execute(
            """
            UPDATE faturas_locais
            SET nota_lancada_id = ?, dados_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                nota_lancada_id,
                json.dumps(dados, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                fatura_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM faturas_locais WHERE id = ?", (fatura_id,)).fetchone()
        return serialize_fatura_local(updated)
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_fatura_local(fatura_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, nota_lancada_id, nome_arquivo, arquivo_storage FROM faturas_locais WHERE id = ?",
        (fatura_id,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM faturas_locais WHERE id = ?", (fatura_id,))
        conn.commit()
    conn.close()
    return dict(row) if row else None


def serialize_fatura_local(row: sqlite3.Row) -> Dict[str, Any]:
    result = dict(row)
    result["dados"] = json.loads(result.pop("dados_json") or "{}")
    return result


def _serialize_nota_recebida(row: sqlite3.Row) -> Dict[str, Any]:
    result = dict(row)
    result["dados"] = json.loads(result.pop("dados_json") or "{}")
    return result


OPERADOR_AUTOMATICO = "sigp-ia"
CONFIRMACOES_PARA_DESCARTE = 3


def _status_inicial(dados: Dict[str, Any]) -> str:
    """Triagem pela IA: ignorado vai para a fila própria; remetente já confirmado 3 vezes como "não é cobrança"
    é descartado direto (reversível, sem revisão); o resto vai para a caixa."""
    if str(dados.get("decisaoIA") or "") == "ignorar":
        if (dados.get("triagem") or {}).get("autoDescarte"):
            return "DESCARTADA"
        return "IGNORADA_IA"
    return "REVISAO" if dados.get("revisaoManual") else "AGUARDANDO_ASSOCIACAO"


def save_nota_recebida(
    message_id: str,
    attachment_id: str,
    thread_id: str,
    assunto: str,
    remetente: str,
    recebida_em: str,
    nome_arquivo: str,
    arquivo_storage: str,
    dados: Dict[str, Any],
) -> tuple[Dict[str, Any], bool]:
    now = _now()
    item_id = f"nrec-{uuid4().hex}"
    if _status_inicial(dados) == "DESCARTADA" and not dados.get("descarte"):
        dados = {**dados, "descarte": {
            "motivo": "nao_cobranca", "operador": OPERADOR_AUTOMATICO, "em": now, "statusAnterior": "IGNORADA_IA",
            "detalhe": f"Automático: remetente confirmado {CONFIRMACOES_PARA_DESCARTE} vezes como não cobrança.",
        }}
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO notas_recebidas (
                id, gmail_message_id, gmail_attachment_id, gmail_thread_id, assunto, remetente, recebida_em,
                nome_arquivo, arquivo_storage, dados_json, status, etiqueta_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(gmail_message_id, gmail_attachment_id) DO UPDATE SET
                -- Reprocessamento: só substitui a extração enquanto ninguém associou o documento.
                assunto = COALESCE(NULLIF(excluded.assunto, ''), notas_recebidas.assunto),
                remetente = COALESCE(NULLIF(excluded.remetente, ''), notas_recebidas.remetente),
                recebida_em = COALESCE(NULLIF(excluded.recebida_em, ''), notas_recebidas.recebida_em),
                dados_json = excluded.dados_json,
                status = excluded.status,
                updated_at = excluded.updated_at
            WHERE notas_recebidas.status IN ('REVISAO', 'AGUARDANDO_ASSOCIACAO', 'IGNORADA_IA')
              AND notas_recebidas.entidade_id = ''
              AND excluded.dados_json NOT IN ('', '{}')
            """,
            (
                item_id, message_id, attachment_id, thread_id, assunto, remetente, recebida_em,
                nome_arquivo, arquivo_storage, json.dumps(dados, ensure_ascii=False),
                _status_inicial(dados),
                "PENDENTE", now, now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM notas_recebidas WHERE gmail_message_id = ? AND gmail_attachment_id = ?",
            (message_id, attachment_id),
        ).fetchone()
        created = bool(row and row["id"] == item_id)
        return _serialize_nota_recebida(row), created
    finally:
        conn.close()


def listar_feedback() -> List[Dict[str, Any]]:
    """Exemplos rotulados (associações, descartes, confirmações) com o que foi lido e o que o operador confirmou."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM extracao_feedback ORDER BY created_at").fetchall()
    finally:
        conn.close()
    itens = []
    for row in rows:
        item = dict(row)
        item["extraidos"] = json.loads(item.pop("dados_extraidos_json") or "{}")
        item["finais"] = json.loads(item.pop("dados_finais_json") or "{}")
        itens.append(item)
    return itens


def historico_remetente(endereco: str) -> Dict[str, Any]:
    """Decisões do operador sobre documentos do mesmo endereço de e-mail: quantas vezes confirmou
    "não é cobrança" (descartes automáticos não contam) e quantas vezes associou como cobrança."""
    endereco = str(endereco or "").strip().lower()
    vazio = {"endereco": endereco, "confirmadosNaoCobranca": 0, "cobrancasConfirmadas": 0}
    if "@" not in endereco:
        return vazio
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT status, dados_json FROM notas_recebidas WHERE instr(lower(remetente), ?) > 0",
            (endereco,),
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        if row["status"] == "ASSOCIADA":
            vazio["cobrancasConfirmadas"] += 1
            continue
        descarte = (json.loads(row["dados_json"] or "{}").get("descarte") or {})
        if row["status"] == "DESCARTADA" and descarte.get("motivo") == "nao_cobranca" \
                and descarte.get("operador") != OPERADOR_AUTOMATICO:
            vazio["confirmadosNaoCobranca"] += 1
    return vazio


def list_notas_recebidas(
    status: str = "", etiqueta_pendente: bool = False, incluir_descartadas: bool = True,
) -> List[Dict[str, Any]]:
    conditions: list[str] = []
    params: list[str] = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    elif not etiqueta_pendente and not incluir_descartadas:
        # Descartadas e ignoradas pela IA saem da caixa; ficam nos filtros próprios.
        conditions.append("status NOT IN ('DESCARTADA', 'IGNORADA_IA')")
    if etiqueta_pendente:
        conditions.extend(("status = 'ASSOCIADA'", "etiqueta_status IN ('PENDENTE', 'ERRO')"))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM notas_recebidas {where} ORDER BY recebida_em DESC, created_at DESC",
        params,
    ).fetchall()
    conn.close()
    return [_serialize_nota_recebida(row) for row in rows]


def registrar_feedback_extracao(
    nota_recebida_id: str,
    tipo: str,
    *,
    motivo: str = "",
    provedor: str = "",
    entidade_tipo: str = "",
    entidade_id: str = "",
    operador: str = "",
    extraidos: Optional[Dict[str, Any]] = None,
    finais: Optional[Dict[str, Any]] = None,
) -> str:
    """Grava um exemplo rotulado (associação ou descarte) para medir/melhorar a extração."""
    feedback_id = f"fb-{uuid4().hex}"
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO extracao_feedback (
                id, nota_recebida_id, tipo, motivo, provedor, entidade_tipo, entidade_id, operador,
                dados_extraidos_json, dados_finais_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id, nota_recebida_id, tipo, motivo[:200], provedor[:300], entidade_tipo, entidade_id,
                operador[:120], json.dumps(extraidos or {}, ensure_ascii=False),
                json.dumps(finais or {}, ensure_ascii=False), _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return feedback_id


def descartar_nota_recebida(item_id: str, motivo: str, detalhe: str, operador: str) -> Optional[Dict[str, Any]]:
    """Marca como DESCARTADA (reversível). Não apaga o registro nem o PDF."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        if row["status"] == "ASSOCIADA":
            conn.rollback()
            raise ValueError("Uma nota já associada não pode ser descartada.")
        dados = json.loads(row["dados_json"] or "{}")
        if row["status"] != "DESCARTADA":
            dados["descarte"] = {
                "motivo": motivo, "detalhe": detalhe[:500], "operador": operador[:120],
                "em": _now(), "statusAnterior": row["status"],
            }
        conn.execute(
            "UPDATE notas_recebidas SET status = 'DESCARTADA', dados_json = ?, operador = ?, updated_at = ? WHERE id = ?",
            (json.dumps(dados, ensure_ascii=False), operador[:120], _now(), item_id),
        )
        updated = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        return _serialize_nota_recebida(updated)
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def restaurar_nota_recebida(item_id: str) -> Optional[Dict[str, Any]]:
    """Desfaz o descarte: volta ao status anterior (REVISAO ou AGUARDANDO_ASSOCIACAO)."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        if row["status"] != "DESCARTADA":
            conn.rollback()
            raise ValueError("Apenas notas descartadas podem ser restauradas.")
        dados = json.loads(row["dados_json"] or "{}")
        anterior = (dados.pop("descarte", {}) or {}).get("statusAnterior")
        novo = anterior if anterior in ("REVISAO", "AGUARDANDO_ASSOCIACAO", "EM_ANALISE") else "REVISAO"
        conn.execute(
            "UPDATE notas_recebidas SET status = ?, dados_json = ?, updated_at = ? WHERE id = ?",
            (novo, json.dumps(dados, ensure_ascii=False), _now(), item_id),
        )
        updated = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        return _serialize_nota_recebida(updated)
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def colocar_em_analise(item_id: str, observacao: str, operador: str) -> Optional[Dict[str, Any]]:
    """Nota em dúvida: sai da fila de associação e fica em EM_ANALISE até o operador decidir.

    Não associa, não descarta e não apaga nada. O reprocessamento do Gmail não sobrescreve este status
    (o upsert só atualiza REVISAO/AGUARDANDO_ASSOCIACAO). Chamar de novo atualiza a observação.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        if row["status"] in ("ASSOCIADA", "DESCARTADA"):
            conn.rollback()
            raise ValueError("Só notas ainda não associadas nem descartadas podem ficar em análise.")
        dados = json.loads(row["dados_json"] or "{}")
        anterior = (dados.get("analise") or {}).get("statusAnterior") if row["status"] == "EM_ANALISE" else row["status"]
        dados["analise"] = {
            "observacao": observacao[:500], "operador": operador[:120], "em": _now(),
            "statusAnterior": anterior if anterior in ("REVISAO", "AGUARDANDO_ASSOCIACAO") else "REVISAO",
        }
        conn.execute(
            "UPDATE notas_recebidas SET status = 'EM_ANALISE', dados_json = ?, operador = ?, updated_at = ? WHERE id = ?",
            (json.dumps(dados, ensure_ascii=False), operador[:120], _now(), item_id),
        )
        updated = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        return _serialize_nota_recebida(updated)
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def retirar_de_analise(item_id: str) -> Optional[Dict[str, Any]]:
    """Devolve a nota em análise à fila (status anterior). A observação fica no histórico (analiseAnterior)."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        if row["status"] != "EM_ANALISE":
            conn.rollback()
            raise ValueError("A nota não está em análise.")
        dados = json.loads(row["dados_json"] or "{}")
        analise = dados.pop("analise", {}) or {}
        dados["analiseAnterior"] = {**analise, "encerradaEm": _now()}
        novo = analise.get("statusAnterior") if analise.get("statusAnterior") in ("REVISAO", "AGUARDANDO_ASSOCIACAO") else "REVISAO"
        conn.execute(
            "UPDATE notas_recebidas SET status = ?, dados_json = ?, updated_at = ? WHERE id = ?",
            (novo, json.dumps(dados, ensure_ascii=False), _now(), item_id),
        )
        updated = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        return _serialize_nota_recebida(updated)
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


_CAMPOS_LEITURA_PDF = (
    "emissorNome", "numero", "chave", "serie", "valorTotal", "dataEmissao", "dataEmissaoOrigem", "dataVencimento",
    "descricaoServico", "cnpjEmissor", "cnpjDestinatario", "camposParaRevisar", "numeroPadrao", "numeroOriginal",
    "numeroMotivo", "chavePadrao", "chaveOriginal", "chaveMotivo", "divergenciasXml", "origemCampos", "versaoRegras",
    "identificadoresCliente",
)


def atualizar_extracao_nota_recebida(item_id: str, campos: Dict[str, Any]) -> bool:
    """Grava a releitura do PDF numa nota ainda não associada nem descartada. Devolve True se gravou.

    Só troca os campos de leitura; mantém XML, classificação da IA, análise, descarte e o que mais houver.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status, dados_json FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not row or row["status"] not in ("REVISAO", "AGUARDANDO_ASSOCIACAO", "EM_ANALISE"):
            conn.rollback()
            return False
        dados = json.loads(row["dados_json"] or "{}")
        for campo in _CAMPOS_LEITURA_PDF:
            if campo in campos:
                dados[campo] = campos[campo]
        dados["relidaEm"] = _now()
        conn.execute("UPDATE notas_recebidas SET dados_json = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(dados, ensure_ascii=False), _now(), item_id))
        conn.commit()
        return True
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def resgatar_ignorado(item_id: str, operador: str) -> Optional[Dict[str, Any]]:
    """A IA errou: o documento ignorado volta para a caixa (Revisão ou Aguardando associação)."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        if row["status"] != "IGNORADA_IA":
            conn.rollback()
            raise ValueError("Só documentos ignorados pela IA podem ser resgatados.")
        dados = json.loads(row["dados_json"] or "{}")
        triagem = dict(dados.get("triagem") or {})
        triagem.update({"resgatadoEm": _now(), "resgatadoPor": operador[:120]})
        dados["triagem"] = triagem
        novo = "REVISAO" if dados.get("revisaoManual") else "AGUARDANDO_ASSOCIACAO"
        conn.execute("UPDATE notas_recebidas SET status = ?, dados_json = ?, operador = ?, updated_at = ? WHERE id = ?",
                     (novo, json.dumps(dados, ensure_ascii=False), operador[:120], _now(), item_id))
        updated = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        return _serialize_nota_recebida(updated)
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def casos_decididos(limite: int = 2000) -> List[Dict[str, Any]]:
    """Notas recebidas já decididas pelo operador (associadas e descartadas), com o local e a última leitura
    corrigida (feedback). Base da memória de exemplos da LLM (etapa 4)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT n.id, n.status, n.remetente, n.assunto, n.nome_arquivo, n.entidade_tipo, n.entidade_id,
                   n.dados_json, n.updated_at, l.nome AS local_nome,
                   (SELECT f.dados_extraidos_json FROM extracao_feedback f
                     WHERE f.nota_recebida_id = n.id ORDER BY f.created_at DESC LIMIT 1) AS extraidos_json
            FROM notas_recebidas AS n
            LEFT JOIN locais AS l ON l.id = n.entidade_id
            WHERE n.status IN ('ASSOCIADA', 'DESCARTADA')
            ORDER BY n.updated_at DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["dados"] = json.loads(item.pop("dados_json") or "{}")
        item["extraidos"] = json.loads(item.pop("extraidos_json") or "{}")
        result.append(item)
    return result


def resumo_triagem(limite: int = 5) -> Dict[str, Any]:
    """Resumo das últimas leituras do Gmail: por execução do n8n, quantos foram para a caixa e quantos a IA ignorou."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT status, dados_json FROM notas_recebidas WHERE dados_json LIKE '%\"execucaoId\"%'"
        ).fetchall()
        pendentes = conn.execute("SELECT COUNT(*) FROM notas_recebidas WHERE status = 'IGNORADA_IA'").fetchone()[0]
    finally:
        conn.close()
    grupos: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        triagem = (json.loads(row["dados_json"] or "{}").get("triagem") or {})
        chave = str(triagem.get("execucaoId") or "")
        if not chave:
            continue
        g = grupos.setdefault(chave, {"execucaoId": chave, "em": "", "documentos": 0, "paraCaixa": 0,
                                      "ignorados": 0, "ignoradosPendentes": 0, "resgatados": 0, "origemBusca": ""})
        g["documentos"] += 1
        g["em"] = max(g["em"], str(triagem.get("em") or ""))
        g["origemBusca"] = triagem.get("origemBusca") or g["origemBusca"]
        if triagem.get("decisao") == "ignorar":
            g["ignorados"] += 1
            if row["status"] == "IGNORADA_IA":
                g["ignoradosPendentes"] += 1
            if triagem.get("resgatadoEm"):
                g["resgatados"] += 1
        else:
            g["paraCaixa"] += 1
    execucoes = sorted(grupos.values(), key=lambda g: g["em"], reverse=True)[:max(1, limite)]
    return {"execucoes": execucoes, "ignoradosPendentes": int(pendentes)}


def get_nota_recebida_por_gmail(message_id: str, attachment_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM notas_recebidas WHERE gmail_message_id = ? AND gmail_attachment_id = ?",
            (message_id, attachment_id),
        ).fetchone()
        return _serialize_nota_recebida(row) if row else None
    finally:
        conn.close()


def get_nota_recebida(item_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    return _serialize_nota_recebida(row) if row else None


def associar_nota_recebida(
    item_id: str,
    entidade_tipo: str,
    entidade_id: str,
    etiqueta_gmail: str,
    operador: str,
) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        exists = conn.execute("SELECT id FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not exists:
            conn.rollback()
            return None
        conn.execute(
            """
            UPDATE notas_recebidas
            SET status = 'ASSOCIADA', entidade_tipo = ?, entidade_id = ?, etiqueta_gmail = ?,
                etiqueta_status = 'PENDENTE', operador = ?, updated_at = ?
            WHERE id = ?
            """,
            (entidade_tipo, entidade_id, etiqueta_gmail, operador, _now(), item_id),
        )
        row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        return _serialize_nota_recebida(row)
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def encontrar_nota_da_competencia(
    conn: sqlite3.Connection, entidade_tipo: str, entidade_id: str, provedor: str, data_vencimento: str,
    excluir_id: str = "",
) -> Optional[sqlite3.Row]:
    """Nota lançada do mesmo local, da mesma empresa e do mesmo mês de vencimento (cobrança recorrente).

    Prefere o mesmo dia de vencimento; depois, a atualizada mais recentemente.
    """
    mes = competencia(data_vencimento)
    if not (entidade_id and provedor and mes):
        return None
    rows = conn.execute(
        """
        SELECT * FROM notas_lancadas
        WHERE entidade_tipo = ? AND entidade_id = ? AND substr(data_vencimento, 1, 7) = ? AND id <> ?
        ORDER BY (data_vencimento = ?) DESC, updated_at DESC
        """,
        (entidade_tipo, entidade_id, mes, excluir_id, data_vencimento),
    ).fetchall()
    return next((row for row in rows if mesma_empresa(row["provedor_nome"], provedor)), None)


def encontrar_disponivel_da_competencia(
    conn: sqlite3.Connection, entidade_tipo: str, entidade_id: str, provedor: str, data_vencimento: str,
) -> Optional[sqlite3.Row]:
    """Nota disponível do mesmo local, da mesma empresa e do mesmo mês de vencimento (a mesma cobrança)."""
    mes = competencia(data_vencimento)
    if not (entidade_id and provedor and mes):
        return None
    rows = conn.execute(
        """
        SELECT * FROM notas_disponiveis
        WHERE entidade_tipo = ? AND entidade_id = ? AND substr(data_vencimento, 1, 7) = ?
        ORDER BY (data_vencimento = ?) DESC, updated_at DESC
        """,
        (entidade_tipo, entidade_id, mes, data_vencimento),
    ).fetchall()
    return next((row for row in rows if mesma_empresa(row["provedor_nome"], provedor)), None)


def lancada_da_disponivel(conn: sqlite3.Connection, disponivel: Dict[str, Any]) -> Optional[sqlite3.Row]:
    """Nota lançada pelo financeiro que corresponde à nota disponível: mesma chave (real) no local, ou mesmo
    local + mesma empresa + mesmo mês de vencimento. Notas criadas pela associação do Gmail não contam."""
    chave = str(disponivel.get("chave") or "").strip()
    if chave and not eh_padrao(chave):
        row = conn.execute(
            "SELECT * FROM notas_lancadas WHERE entidade_tipo = ? AND entidade_id = ? AND chave = ? AND sistema_origem <> 'gmail'",
            (disponivel["entidade_tipo"], disponivel["entidade_id"], chave),
        ).fetchone()
        if row:
            return row
    nota = encontrar_nota_da_competencia(conn, disponivel["entidade_tipo"], disponivel["entidade_id"],
                                         str(disponivel.get("provedor_nome") or ""), str(disponivel.get("data_vencimento") or ""))
    return nota if nota and nota["sistema_origem"] != "gmail" else None


def integrar_nota_recebida(
    item_id: str,
    entidade_tipo: str,
    entidade_id: str,
    etiqueta_gmail: str,
    operador: str,
    local: Dict[str, Any],
    dados: Dict[str, Any],
    arquivo_storage: str,
    selected_note_id: str = "",
    substituir: bool = False,
) -> Optional[Dict[str, Any]]:
    """Associa o documento recebido ao local como NOTA DISPONÍVEL (não cria nota lançada: essa é só do financeiro).
    Documentos da mesma cobrança (local + provedor + mês) ficam na mesma nota disponível. Se o financeiro já lançou
    a nota correspondente, as duas se ligam (e a fatura entra na conciliação dela)."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        received = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not received:
            conn.rollback()
            return None

        provider_name = str(dados.get("emissorNome") or "").strip()
        due_date = str(dados.get("dataVencimento") or "").strip()
        existing = None
        if selected_note_id:
            existing = conn.execute("SELECT * FROM notas_disponiveis WHERE id = ?", (selected_note_id,)).fetchone()
            if not existing or existing["entidade_tipo"] != entidade_tipo or existing["entidade_id"] != entidade_id:
                raise ValueError("A nota escolhida para atualização não pertence ao local selecionado.")
        elif received["nota_disponivel_id"]:
            ligada = conn.execute("SELECT * FROM notas_disponiveis WHERE id = ?", (received["nota_disponivel_id"],)).fetchone()
            if ligada and ligada["entidade_tipo"] == entidade_tipo and ligada["entidade_id"] == entidade_id \
                    and competencia(ligada["data_vencimento"]) == competencia(due_date) and mesma_empresa(ligada["provedor_nome"], provider_name):
                existing = ligada
        if not existing:
            # Recorrência: mesmo local + mesma empresa + mesmo mês de vencimento = a mesma cobrança.
            existing = encontrar_disponivel_da_competencia(conn, entidade_tipo, entidade_id, provider_name, due_date)
        disponivel_id = str(existing["id"]) if existing else f"disp-{uuid4().hex}"

        def _identificador(campo: str) -> str:
            # Número/chave real vence o valor padrão: o padrão nunca apaga o que a nota já tinha.
            novo = str(dados.get(campo) or "").strip()
            antigo = str((existing[campo] or "") if existing else "").strip()
            if (not novo or eh_padrao(novo)) and antigo and not eh_padrao(antigo):
                return antigo
            return novo or antigo

        now = _now()
        servicos = [{"codigo": "", "classificacao": "PENDENTE", **s} for s in (dados.get("servicos") or []) if isinstance(s, dict)]
        payload = {
            "id": disponivel_id, "entidade_tipo": entidade_tipo, "entidade_id": entidade_id,
            "chave": _identificador("chave") or VALOR_PADRAO, "numero": _identificador("numero") or VALOR_PADRAO,
            "serie": str(dados.get("serie") or (existing["serie"] if existing else "") or "").strip(),
            "provedor_nome": provider_name, "local_nome": str(local.get("nome") or ""), "local_cidade": str(local.get("cidade") or ""),
            "valor_total": float(dados["valorTotal"]), "data_emissao": str(dados["dataEmissao"]), "data_vencimento": due_date,
            "observacao": str(dados.get("descricaoServico") or ""),
            "servicos_json": json.dumps(servicos, ensure_ascii=False) if servicos else (existing["servicos_json"] if existing else "[]"),
            "nota_lancada_id": str(existing["nota_lancada_id"] or "") if existing else "",
            "origem": "gmail", "id_externo": str(received["gmail_message_id"]),
            "created_at": existing["created_at"] if existing else now, "updated_at": now,
        }
        if not payload["nota_lancada_id"]:
            lancada = lancada_da_disponivel(conn, payload)
            payload["nota_lancada_id"] = str(lancada["id"]) if lancada else ""
        conn.execute(
            """
            INSERT INTO notas_disponiveis (id, entidade_tipo, entidade_id, chave, numero, serie, provedor_nome, local_nome, local_cidade,
                valor_total, data_emissao, data_vencimento, observacao, servicos_json, nota_lancada_id, origem, id_externo, created_at, updated_at)
            VALUES (:id, :entidade_tipo, :entidade_id, :chave, :numero, :serie, :provedor_nome, :local_nome, :local_cidade,
                :valor_total, :data_emissao, :data_vencimento, :observacao, :servicos_json, :nota_lancada_id, :origem, :id_externo, :created_at, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                chave = excluded.chave, numero = excluded.numero, serie = excluded.serie, provedor_nome = excluded.provedor_nome,
                local_nome = excluded.local_nome, local_cidade = excluded.local_cidade, valor_total = excluded.valor_total,
                data_emissao = excluded.data_emissao, data_vencimento = excluded.data_vencimento, observacao = excluded.observacao,
                servicos_json = excluded.servicos_json, nota_lancada_id = excluded.nota_lancada_id, id_externo = excluded.id_externo,
                updated_at = excluded.updated_at
            """,
            payload,
        )
        lancada_id = payload["nota_lancada_id"]

        # Documentos da mesma cobrança: o primeiro é a fatura principal; os seguintes (XML/NFS-e em PDF, boleto à parte,
        # outro e-mail) entram como documentos adicionais e não substituem nada. Associar de novo o MESMO documento
        # atualiza a linha dele. Divergência confirmada (correção) substitui a principal. (Regras por mês: a definir.)
        principal = conn.execute(
            """
            SELECT id, arquivo_storage, created_at FROM faturas_locais
            WHERE nota_disponivel_id = ? AND COALESCE(json_extract(dados_json, '$.documentoAdicional'), 0) = 0
            ORDER BY created_at, rowid LIMIT 1
            """,
            (disponivel_id,),
        ).fetchone()
        previous_invoice = conn.execute(
            """
            SELECT id, arquivo_storage, created_at FROM faturas_locais
            WHERE nota_disponivel_id = ? AND json_extract(dados_json, '$.notaRecebidaId') = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (disponivel_id, item_id),
        ).fetchone()
        if substituir and principal and not previous_invoice:
            previous_invoice = principal  # correção confirmada: o documento novo ocupa o lugar da fatura principal
        adicional = bool(principal) and not (previous_invoice and previous_invoice["id"] == principal["id"])
        if previous_invoice:
            invoice_id = str(previous_invoice["id"])
        elif principal:
            invoice_id = f"gmail-{disponivel_id}-{item_id}"
        else:
            invoice_id = f"gmail-{disponivel_id}"
        invoice_data = {
            **dados,
            "provedorEsperado": provider_name,
            "comparacao": {"emissorConfere": True, "valorConfere": True, "vencimentoConfere": True},
            "origem": "gmail",
            "notaRecebidaId": item_id,
            **({"documentoAdicional": True} if adicional else {}),
        }
        conn.execute(
            """
            INSERT INTO faturas_locais (
                id, entidade_tipo, entidade_id, provedor_id, provedor_nome, nota_lancada_id, nota_disponivel_id, nome_arquivo,
                arquivo_storage, dados_json, created_at, updated_at
            ) VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                entidade_tipo = excluded.entidade_tipo, entidade_id = excluded.entidade_id,
                provedor_nome = excluded.provedor_nome, nota_lancada_id = excluded.nota_lancada_id,
                nota_disponivel_id = excluded.nota_disponivel_id,
                nome_arquivo = excluded.nome_arquivo, arquivo_storage = excluded.arquivo_storage,
                dados_json = excluded.dados_json, updated_at = excluded.updated_at
            """,
            (
                invoice_id, entidade_tipo, entidade_id, provider_name, lancada_id, disponivel_id,
                str(received["nome_arquivo"]), arquivo_storage, json.dumps(invoice_data, ensure_ascii=False),
                previous_invoice["created_at"] if previous_invoice else now, now,
            ),
        )
        if lancada_id:
            conn.execute("UPDATE faturas_locais SET nota_lancada_id = ? WHERE nota_disponivel_id = ?", (lancada_id, disponivel_id))
        conn.execute(
            """
            UPDATE notas_recebidas
            SET nota_disponivel_id = ?, nota_lancada_id = ?, status = 'ASSOCIADA', entidade_tipo = ?, entidade_id = ?,
                dados_json = ?, etiqueta_gmail = ?, etiqueta_status = 'PENDENTE', etiqueta_erro = '',
                operador = ?, updated_at = ?
            WHERE id = ?
            """,
            (disponivel_id, lancada_id, entidade_tipo, entidade_id, json.dumps(dados, ensure_ascii=False),
             etiqueta_gmail, operador, now, item_id),
        )
        disp_row = conn.execute("SELECT * FROM notas_disponiveis WHERE id = ?", (disponivel_id,)).fetchone()
        lancada_row = conn.execute("SELECT * FROM notas_lancadas WHERE id = ?", (lancada_id,)).fetchone() if lancada_id else None
        received_row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        return {
            "item": _serialize_nota_recebida(received_row),
            "notaDisponivel": serialize_row(disp_row),
            "notaLancada": serialize_row(lancada_row) if lancada_row else None,
            # A fatura atual do provedor continua sendo a principal; o adicional só se soma aos documentos.
            "faturaId": str(principal["id"]) if adicional else invoice_id,
            "documentoAdicional": adicional,
            "arquivoAnterior": str(previous_invoice["arquivo_storage"]) if previous_invoice else "",
            "createdNote": existing is None,
        }
    except (sqlite3.Error, ValueError):
        conn.rollback()
        raise
    finally:
        conn.close()


def confirmar_etiqueta_nota_recebida(item_id: str, ok: bool, erro: str = "") -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        status = "APLICADA" if ok else "ERRO"
        row = conn.execute("SELECT id FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE notas_recebidas SET etiqueta_status = ?, etiqueta_erro = ?, updated_at = ? WHERE id = ?",
            (status, "" if ok else erro, _now(), item_id),
        )
        updated = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        conn.commit()
        result = _serialize_nota_recebida(updated)
        return result
    finally:
        conn.close()


def save_fatura_local(
    fatura_id: str,
    entidade_tipo: str,
    entidade_id: str,
    nota_lancada_id: str,
    nome_arquivo: str,
    arquivo_storage: str,
    dados: Dict[str, Any],
    provedor_id: str = "",
    provedor_nome: str = "",
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO faturas_locais (
            id, entidade_tipo, entidade_id, provedor_id, provedor_nome, nota_lancada_id, nome_arquivo,
            arquivo_storage, dados_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fatura_id, entidade_tipo, entidade_id, provedor_id, provedor_nome, nota_lancada_id, nome_arquivo,
            arquivo_storage, json.dumps(dados, ensure_ascii=False), now, now,
        ),
    )
    if nota_lancada_id and dados.get("dataVencimento"):
        conn.execute(
            """
            UPDATE notas_lancadas
            SET data_vencimento = ?, updated_at = ?
            WHERE id = ? AND (data_vencimento IS NULL OR data_vencimento = '')
            """,
            (str(dados["dataVencimento"]), now, nota_lancada_id),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM faturas_locais WHERE id = ?", (fatura_id,)).fetchone()
    conn.close()
    return serialize_fatura_local(row)


def list_nota_pagas() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM notas_pagas ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [serialize_row(row) for row in rows]


def save_conciliacao(
    nota_lancada: Dict[str, Any],
    nota_paga: Dict[str, Any],
    status: str,
    observacao: str,
    comparacao: Dict[str, bool] | None = None,
    fatura_id: str = "",
    fatura_match: bool | None = None,
) -> Dict[str, Any]:
    conn = get_connection()
    nota_lancada_id = nota_lancada.get("id") or ""
    nota_paga_id = nota_paga.get("id") or ""
    conn.execute("BEGIN IMMEDIATE")
    existing = conn.execute(
        "SELECT id, created_at FROM conciliacoes WHERE nota_lancada_id = ? AND nota_paga_id = ? ORDER BY updated_at DESC LIMIT 1",
        (nota_lancada_id, nota_paga_id),
    ).fetchone()
    chave_lancada = "" if eh_padrao(nota_lancada.get("chave")) else (nota_lancada.get("chave") or "")
    chave_paga = "" if eh_padrao(nota_paga.get("chave")) else (nota_paga.get("chave") or "")
    valor_lancado = nota_lancada.get("valor_total", nota_lancada.get("valorTotal", nota_lancada.get("valor", 0)))
    valor_pago_nota = nota_paga.get("valor_total", nota_paga.get("valorTotal", nota_paga.get("valor", 0)))
    cidade_lancada = nota_lancada.get("local_cidade") or nota_lancada.get("localCidade") or ""
    cidade_paga = nota_paga.get("local_cidade") or nota_paga.get("localCidade") or ""
    chave_match = int((comparacao or {}).get("chave", bool(chave_lancada and chave_paga and chave_lancada.strip().upper() == chave_paga.strip().upper())))
    valor_match = int((comparacao or {}).get("valor", float(valor_lancado or 0) > 0 and abs(float(valor_lancado or 0) - float(valor_pago_nota or 0)) < 0.01))
    local_match = int((comparacao or {}).get("cidade", bool(cidade_lancada and cidade_paga and cidade_lancada.strip().casefold() == cidade_paga.strip().casefold())))
    servicos_match = int((comparacao or {}).get("servicos", False))
    payload = {
        "id": str(existing["id"]) if existing else f"conc-{uuid4().hex}",
        "nota_lancada_id": nota_lancada_id,
        "nota_paga_id": nota_paga_id,
        "chave_match": chave_match,
        "valor_match": valor_match,
        "local_match": local_match,
        "servicos_match": servicos_match,
        "status": status,
        "observacao": observacao,
        "created_at": str(existing["created_at"]) if existing else _now(),
        "updated_at": _now(),
        "fatura_id": fatura_id,
        "fatura_match": None if fatura_match is None else int(fatura_match),
    }
    conn.execute(
        """
        INSERT INTO conciliacoes (id, nota_lancada_id, nota_paga_id, chave_match, valor_match, local_match, servicos_match, status, observacao, fatura_id, fatura_match, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            chave_match = excluded.chave_match,
            valor_match = excluded.valor_match,
            local_match = excluded.local_match,
            servicos_match = excluded.servicos_match,
            status = excluded.status,
            observacao = excluded.observacao,
            fatura_id = excluded.fatura_id,
            fatura_match = excluded.fatura_match,
            updated_at = excluded.updated_at
        """,
        (
            payload["id"], payload["nota_lancada_id"], payload["nota_paga_id"],
            payload["chave_match"], payload["valor_match"], payload["local_match"], payload["servicos_match"],
            payload["status"], payload["observacao"], payload["fatura_id"], payload["fatura_match"],
            payload["created_at"], payload["updated_at"],
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM conciliacoes WHERE id = ?", (payload["id"],)).fetchone()
    conn.close()
    return serialize_row(row)


def list_conciliacoes() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT rowid AS _ordem, * FROM conciliacoes ORDER BY updated_at DESC, rowid DESC").fetchall()
    conn.close()
    return [serialize_row(row) for row in rows]


def log_event(tipo: str, payload: Dict[str, Any]) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO api_events (tipo, payload, created_at) VALUES (?, ?, ?)",
        (tipo, json.dumps(payload, ensure_ascii=False), datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def _resolve_external_id(conn: sqlite3.Connection, table: str, payload: Dict[str, Any]) -> None:
    """Reenvio do mesmo documento externo (Praxio/Globus/n8n) atualiza o registro existente."""
    if not payload.get("sistema_origem") or not payload.get("id_externo"):
        return
    row = conn.execute(
        f"SELECT id FROM {table} WHERE sistema_origem = ? AND id_externo = ? LIMIT 1",
        (payload["sistema_origem"], payload["id_externo"]),
    ).fetchone()
    if row:
        payload["id"] = str(row["id"])


# --- Locais (agências, rodoviárias, garagens) -------------------------------------------

LOCAL_TIPOS = {"agencia", "rodoviaria", "garagem"}


def _serialize_local(row: sqlite3.Row) -> Dict[str, Any]:
    result = dict(row)
    result["vencimentoFatura"] = result.pop("vencimento_fatura")
    result["provedores"] = json.loads(result.pop("provedores_json") or "[]")
    extras = json.loads(result.pop("dados_json") or "{}")
    result.update(extras)
    result["dados"] = extras
    result["ativo"] = bool(result["ativo"])
    return result


_CAMPOS_FATURA_ATUAL = ("valor", "dataVencimento", "diaVencimento", "faturaAtualId")


def preservar_fatura_atual(recebidos: List[Any], existentes: List[Any]) -> List[Any]:
    """A gravação do cadastro pela tela envia o retrato completo do local. Se esse retrato partir de uma
    cópia antiga, não pode apagar nem fazer regredir a fatura atual que o backend preencheu no provedor
    (regra única de nota/fatura associada). Mesmo provedor (por id) chegando sem vencimento ou com
    vencimento mais antigo: mantém os campos da fatura atual. Data igual ou mais nova: vale a da tela.
    """
    por_id = {str(p.get("id")): p for p in existentes if isinstance(p, dict) and p.get("id")}
    resultado = []
    for provedor in recebidos:
        if not isinstance(provedor, dict):
            resultado.append(provedor)
            continue
        antigo = por_id.get(str(provedor.get("id") or ""))
        venc_antigo = str((antigo or {}).get("dataVencimento") or "")
        venc_novo = str(provedor.get("dataVencimento") or "")
        if antigo and venc_antigo and (not venc_novo or venc_novo < venc_antigo):
            provedor = {**provedor, **{c: antigo[c] for c in _CAMPOS_FATURA_ATUAL if antigo.get(c) not in (None, "")}}
        elif antigo and str(antigo.get("diaVencimento") or "").strip() and not str(provedor.get("diaVencimento") or "").strip():
            # Dia de vencimento preenchido (Qualidade do cadastro ou fatura) não some por uma cópia antiga da tela.
            provedor = {**provedor, "diaVencimento": antigo["diaVencimento"]}
        resultado.append(provedor)
    return resultado


def sync_locais(tipo: str, items: List[Dict[str, Any]]) -> Dict[str, int]:
    """Recebe o retrato completo de um tipo de local; quem não vier é marcado inativo (não apagado)."""
    now = _now()
    conn = get_connection()
    conn.execute("BEGIN IMMEDIATE")
    received: set[str] = set()
    for item in items:
        local_id = str(item.get("id") or "").strip()
        if not local_id:
            continue
        received.add(local_id)
        provedores = item.get("provedores") if isinstance(item.get("provedores"), list) else []
        anterior = conn.execute("SELECT provedores_json FROM locais WHERE id = ?", (local_id,)).fetchone()
        if anterior:
            provedores = preservar_fatura_atual(provedores, json.loads(anterior["provedores_json"] or "[]"))
        extras = {
            key: value for key, value in item.items()
            if key not in {
                "id", "tipo", "nome", "cidade", "endereco", "vencimentoFatura", "provedores",
                "ativo", "created_at", "updated_at", "dados",
            }
        }
        conn.execute(
            """
            INSERT INTO locais (id, tipo, nome, cidade, endereco, vencimento_fatura, provedores_json, dados_json, ativo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tipo = excluded.tipo, nome = excluded.nome, cidade = excluded.cidade, endereco = excluded.endereco,
                vencimento_fatura = excluded.vencimento_fatura, provedores_json = excluded.provedores_json,
                dados_json = excluded.dados_json, ativo = 1, updated_at = excluded.updated_at
            """,
            (
                local_id, tipo, str(item.get("nome") or "").strip(), str(item.get("cidade") or "").strip(),
                str(item.get("endereco") or "").strip(), str(item.get("vencimentoFatura") or "").strip(),
                json.dumps(provedores, ensure_ascii=False), json.dumps(extras, ensure_ascii=False), now, now,
            ),
        )
    existing = {row["id"] for row in conn.execute("SELECT id FROM locais WHERE tipo = ? AND ativo = 1", (tipo,))}
    removed = existing - received
    for local_id in removed:
        conn.execute("UPDATE locais SET ativo = 0, updated_at = ? WHERE id = ?", (now, local_id))
    conn.commit()
    conn.close()
    return {"recebidos": len(received), "inativados": len(removed)}


def create_local(tipo: str, nome: str, cidade: str) -> Dict[str, Any]:
    local_id = f"local-{uuid4().hex}"
    now = _now()
    conn = get_connection()
    try:
        duplicate = conn.execute(
            "SELECT id FROM locais WHERE tipo = ? AND ativo = 1 AND lower(trim(nome)) = lower(?) AND lower(trim(cidade)) = lower(?) LIMIT 1",
            (tipo, nome.strip(), cidade.strip()),
        ).fetchone()
        if duplicate:
            raise ValueError("Já existe um local ativo com esse nome e cidade.")
        conn.execute(
            """
            INSERT INTO locais (
                id, tipo, nome, cidade, endereco, vencimento_fatura, provedores_json,
                dados_json, ativo, created_at, updated_at
            ) VALUES (?, ?, ?, ?, '', '', '[]', '{}', 1, ?, ?)
            """,
            (local_id, tipo, nome.strip(), cidade.strip(), now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM locais WHERE id = ?", (local_id,)).fetchone()
        return _serialize_local(row)
    finally:
        conn.close()


def list_locais(tipo: str = "", incluir_inativos: bool = False) -> List[Dict[str, Any]]:
    conditions, params = [], []
    if tipo:
        conditions.append("tipo = ?")
        params.append(tipo)
    if not incluir_inativos:
        conditions.append("ativo = 1")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    conn = get_connection()
    rows = conn.execute(f"SELECT * FROM locais {where} ORDER BY tipo, nome", params).fetchall()
    conn.close()
    return [_serialize_local(row) for row in rows]


def aplicar_fatura_no_local(
    local_id: str, *, nome: str, valor: float, data_vencimento: str, fatura_id: str = "", provedor_id: str = "",
) -> Dict[str, Any]:
    """Atualiza o provedor do local com a fatura associada (regra em backend/provedores.py)."""
    from backend.provedores import aplicar_fatura_no_provedor

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT provedores_json FROM locais WHERE id = ?", (local_id,)).fetchone()
        if not row:
            conn.rollback()
            return {"provedores": [], "provedor": None, "acao": "sem_local", "aviso": "Local não encontrado."}
        resultado = aplicar_fatura_no_provedor(
            json.loads(row["provedores_json"] or "[]"),
            nome=nome, valor=valor, data_vencimento=data_vencimento, fatura_id=fatura_id, provedor_id=provedor_id,
        )
        if resultado["acao"] in ("criado", "atualizado"):
            conn.execute(
                "UPDATE locais SET provedores_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(resultado["provedores"], ensure_ascii=False), _now(), local_id),
            )
        conn.commit()
        return resultado
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def marcar_provedor_pago(local_id: str, provedor_nome: str, pago_ate: str) -> bool:
    """Situação 1: pagamento confirmado pelo provedor marca o provedor do local como pago até o vencimento
    (o mesmo que o botão "Marcar como pago" do cadastro). Só mexe em provedor com o mesmo nome de empresa."""
    from backend.provedores import mesma_empresa

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT provedores_json FROM locais WHERE id = ?", (local_id,)).fetchone()
        if not row:
            conn.rollback()
            return False
        provedores = json.loads(row["provedores_json"] or "[]")
        alterado = False
        for provedor in provedores:
            if isinstance(provedor, dict) and mesma_empresa(provedor.get("nome"), provedor_nome):
                if str(provedor.get("pagoAte") or "") < pago_ate:
                    provedor["pagoAte"] = pago_ate
                    alterado = True
        if alterado:
            conn.execute("UPDATE locais SET provedores_json = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(provedores, ensure_ascii=False), _now(), local_id))
        conn.commit()
        return alterado
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def aprender_codigos_cliente(local_id: str, provedor_nome: str, identificadores: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Situações 3 a 5: a associação ensina o código do cliente/contrato ao provedor deste local.
    Código que já está no mesmo provedor de OUTRO local não é guardado (não distingue os locais)."""
    from backend.identificadores import codigos_do_provedor, normalizar
    from backend.provedores import mesma_empresa

    novos = [i for i in identificadores or [] if i.get("tipo") in ("cliente", "contrato") and normalizar(i.get("valor"))]
    instalacao = next((str(i.get("valor") or "") for i in identificadores or [] if i.get("tipo") == "instalacao"), "")
    resultado: Dict[str, Any] = {"adicionados": [], "emOutroLocal": [], "provedor": None}
    if not novos and not instalacao:
        return resultado
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT id, provedores_json FROM locais").fetchall()
        em_outros = set()
        alvo_provedores = None
        for row in rows:
            provedores = json.loads(row["provedores_json"] or "[]")
            if row["id"] == local_id:
                alvo_provedores = provedores
                continue
            for p in provedores:
                if isinstance(p, dict) and mesma_empresa(p.get("nome"), provedor_nome):
                    em_outros.update(codigos_do_provedor(p))
        if alvo_provedores is None:
            conn.rollback()
            return resultado
        alvo = next((p for p in alvo_provedores if isinstance(p, dict) and mesma_empresa(p.get("nome"), provedor_nome)), None)
        if not alvo:
            conn.rollback()
            return resultado
        atuais = [v.strip() for v in str(alvo.get("codigosCliente") or "").split(",") if v.strip()]
        conhecidos = {normalizar(v) for v in atuais}
        for item in novos:
            valor = str(item["valor"]).strip()
            chave = normalizar(valor)
            if chave in em_outros:
                resultado["emOutroLocal"].append(valor)
            elif chave not in conhecidos and len(atuais) < 8:
                atuais.append(valor)
                conhecidos.add(chave)
                resultado["adicionados"].append(valor)
        mudou = bool(resultado["adicionados"])
        if resultado["adicionados"]:
            alvo["codigosCliente"] = ", ".join(atuais)
        if instalacao and not alvo.get("enderecoInstalacao"):
            alvo["enderecoInstalacao"] = instalacao
            mudou = True
        if mudou:
            conn.execute("UPDATE locais SET provedores_json = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(alvo_provedores, ensure_ascii=False), _now(), local_id))
        conn.commit()
        resultado["provedor"] = alvo
        return resultado
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def vincular_aviso_nota_recebida(
    item_id: str, dados: Dict[str, Any], status: Optional[str] = None,
    entidade_tipo: str = "", entidade_id: str = "", nota_lancada_id: str = "",
) -> Optional[Dict[str, Any]]:
    """Grava o resultado do vínculo de um aviso (situação 1). Com status AVISO, a nota sai da caixa vinculada à cobrança."""
    conn = get_connection()
    try:
        if status:
            conn.execute(
                "UPDATE notas_recebidas SET dados_json = ?, status = ?, entidade_tipo = ?, entidade_id = ?, nota_lancada_id = ?,"
                " updated_at = ? WHERE id = ?",
                (json.dumps(dados, ensure_ascii=False), status, entidade_tipo, entidade_id, nota_lancada_id, _now(), item_id),
            )
        else:
            conn.execute("UPDATE notas_recebidas SET dados_json = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(dados, ensure_ascii=False), _now(), item_id))
        conn.commit()
        row = conn.execute("SELECT * FROM notas_recebidas WHERE id = ?", (item_id,)).fetchone()
        return _serialize_nota_recebida(row) if row else None
    finally:
        conn.close()


def get_local(local_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM locais WHERE id = ?", (local_id,)).fetchone()
    conn.close()
    return _serialize_local(row) if row else None


def get_app_state(keys: List[str]) -> Dict[str, Any]:
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    conn = get_connection()
    rows = conn.execute(
        f"SELECT state_key, value_json FROM app_state WHERE state_key IN ({placeholders})",
        keys,
    ).fetchall()
    conn.close()
    return {row["state_key"]: json.loads(row["value_json"]) for row in rows}


def save_app_state(key: str, value: Any) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO app_state (state_key, value_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(state_key) DO UPDATE SET
            value_json = excluded.value_json, updated_at = excluded.updated_at
        """,
        (key, json.dumps(value, ensure_ascii=False), _now()),
    )
    conn.commit()
    conn.close()


def delete_app_state(key: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM app_state WHERE state_key = ?", (key,))
    conn.commit()
    conn.close()


# --- Correção manual auditada --------------------------------------------------------------

CORRECTABLE_FIELDS = {
    "chave": "chave", "numero": "numero", "serie": "serie", "provedorNome": "provedor_nome",
    "localNome": "local_nome", "localCidade": "local_cidade", "valorTotal": "valor_total",
    "dataEmissao": "data_emissao", "dataVencimento": "data_vencimento", "observacao": "observacao",
    "servicos": "servicos_json", "entidadeTipo": "entidade_tipo", "entidadeId": "entidade_id",
}
CORRECTABLE_PAID_FIELDS = {"valorPago": "valor_pago", "dataPagamento": "data_pagamento"}


def correct_document(table: str, document_id: str, campos: Dict[str, Any], usuario: str, motivo: str) -> Dict[str, Any]:
    """Aplica correções campo a campo e registra antes/depois. Lança KeyError, ValueError ou DuplicateDocumentError."""
    allowed = dict(CORRECTABLE_FIELDS)
    if table == "notas_pagas":
        allowed.update(CORRECTABLE_PAID_FIELDS)
    unknown = sorted(set(campos) - set(allowed))
    if unknown:
        raise ValueError(f"Campos não corrigíveis: {', '.join(unknown)}.")
    conn = get_connection()
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (document_id,)).fetchone()
        if not current:
            raise KeyError(document_id)
        changes: list[tuple[str, Any, Any]] = []
        for field, value in campos.items():
            column = allowed[field]
            if column == "servicos_json":
                value = json.dumps(value if isinstance(value, list) else [], ensure_ascii=False)
            elif column in {"valor_total", "valor_pago"}:
                value = float(value)
                if value < 0 or value != value:
                    raise ValueError(f"Valor inválido para {field}.")
            else:
                value = str(value if value is not None else "").strip()
            if str(current[column] if current[column] is not None else "") != str(value):
                changes.append((column, current[column], value))
        new_key = next((value for column, _old, value in changes if column == "chave"), None)
        if new_key and not eh_padrao(new_key):
            other = conn.execute(
                f"SELECT id FROM {table} WHERE lower(trim(chave)) = lower(?) AND id <> ? LIMIT 1",
                (new_key, document_id),
            ).fetchone()
            if other:
                raise DuplicateDocumentError(str(other["id"]))
        now = _now()
        for column, old, new in changes:
            conn.execute(f"UPDATE {table} SET {column} = ?, updated_at = ? WHERE id = ?", (new, now, document_id))
            conn.execute(
                """INSERT INTO correcoes (documento_tipo, documento_id, campo, valor_anterior, valor_novo, usuario, motivo, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (table, document_id, column, None if old is None else str(old), str(new), usuario, motivo, now),
            )
        conn.commit()
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (document_id,)).fetchone()
        return {"item": serialize_row(row), "alterados": [column for column, _old, _new in changes]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_correcoes(table: str, document_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM correcoes WHERE documento_tipo = ? AND documento_id = ? ORDER BY id DESC",
        (table, document_id),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# --- Faturas e conciliações por nota --------------------------------------------------------

def latest_fatura_for_nota(nota_lancada_id: str) -> Optional[Dict[str, Any]]:
    """Fatura mais recente do provedor/local da nota, com fallback ao vínculo direto legado."""
    nota = get_nota_lancada(nota_lancada_id)
    if nota:
        expected_provider = _normalize_provider_name(nota.get("provedor_nome"))
        if expected_provider:
            local_invoices = list_faturas_locais(
                str(nota.get("entidade_tipo") or ""),
                str(nota.get("entidade_id") or ""),
            )
            provider_invoices = [
                item for item in local_invoices
                if _normalize_provider_name(
                    item.get("provedor_nome") or (item.get("dados") or {}).get("provedorEsperado")
                ) == expected_provider
            ]
            # Documento adicional da cobrança (XML/NFS-e em PDF) não vira a referência: vale a fatura principal.
            provider_invoices = [i for i in provider_invoices if not (i.get("dados") or {}).get("documentoAdicional")] or provider_invoices
            if provider_invoices:
                invoice = provider_invoices[0]
                return {"id": invoice["id"], "dados": invoice["dados"], "created_at": invoice["created_at"]}

    conn = get_connection()
    local = conn.execute(
        "SELECT * FROM faturas_locais WHERE nota_lancada_id = ?"
        " ORDER BY COALESCE(json_extract(dados_json, '$.documentoAdicional'), 0), created_at DESC, rowid DESC LIMIT 1",
        (nota_lancada_id,),
    ).fetchone()
    legacy = conn.execute("SELECT * FROM faturas_provedores WHERE nota_lancada_id = ?", (nota_lancada_id,)).fetchone()
    conn.close()
    if local:
        data = serialize_fatura_local(local)
        return {"id": data["id"], "dados": data["dados"], "created_at": data["created_at"]}
    if legacy:
        dados = json.loads(legacy["dados_extracao_json"] or "{}")
        return {"id": legacy["id"], "dados": dados, "created_at": legacy["created_at"]}
    return None


def list_conciliacoes_da_nota(nota_lancada_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM conciliacoes WHERE nota_lancada_id = ? ORDER BY updated_at DESC, rowid DESC",
        (nota_lancada_id,),
    ).fetchall()
    conn.close()
    return [serialize_row(row) for row in rows]


def list_conciliacoes_da_paga(nota_paga_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM conciliacoes WHERE nota_paga_id = ?", (nota_paga_id,)).fetchall()
    conn.close()
    return [serialize_row(row) for row in rows]


def list_faturas_todas() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM faturas_locais ORDER BY created_at DESC").fetchall()
    legacy = conn.execute("SELECT nota_lancada_id FROM faturas_provedores").fetchall()
    conn.close()
    result = [serialize_fatura_local(row) for row in rows]
    result += [{"nota_lancada_id": row["nota_lancada_id"], "dados": {}} for row in legacy]
    return result


# --- Análises de IA (SIG / SIE) ---------------------------------------------------------------

def save_analise(escopo: str, conteudo: str, titulo: str = "", referencia: str = "", dados: Dict[str, Any] | None = None,
                 modelo: str = "", origem: str = "n8n", status_validacao: str = "") -> Dict[str, Any]:
    item = {
        "id": f"analise-{uuid4().hex}", "escopo": escopo, "referencia": referencia, "titulo": titulo,
        "conteudo": conteudo, "dados_json": json.dumps(dados or {}, ensure_ascii=False), "modelo": modelo,
        "origem": origem, "created_at": _now(), "status_validacao": status_validacao,
    }
    conn = get_connection()
    conn.execute("BEGIN IMMEDIATE")
    if status_validacao == "PENDENTE" and referencia:
        # Nova análise do mesmo ciclo substitui a que ainda aguardava o gerente (o gerente decide a mais recente).
        conn.execute(
            "UPDATE analises SET status_validacao = 'SUBSTITUIDA' WHERE escopo = ? AND referencia = ? AND status_validacao = 'PENDENTE'",
            (escopo, referencia),
        )
    conn.execute(
        """INSERT INTO analises (id, escopo, referencia, titulo, conteudo, dados_json, modelo, origem, created_at, status_validacao)
           VALUES (:id, :escopo, :referencia, :titulo, :conteudo, :dados_json, :modelo, :origem, :created_at, :status_validacao)""",
        item,
    )
    conn.commit()
    conn.close()
    item["dados"] = json.loads(item.pop("dados_json"))
    return item


def get_analise(analise_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM analises WHERE id = ?", (analise_id,)).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item["dados"] = json.loads(item.pop("dados_json") or "{}")
    return item


_DECISAO_STATUS = {"validar": "VALIDADA", "corrigir": "CORRIGIDA", "devolver": "DEVOLVIDA"}


def registrar_decisao_gerente(
    analise_id: str, acao: str, justificativa: str, usuario: str, conteudo_corrigido: str = "",
) -> Optional[Dict[str, Any]]:
    """Decisão do gerente sobre uma análise SIG pendente. Uma decisão por análise (auditoria imutável)."""
    status = _DECISAO_STATUS[acao]
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM analises WHERE id = ?", (analise_id,)).fetchone()
        if not row:
            conn.rollback()
            return None
        if row["escopo"] != "SIG" or row["status_validacao"] != "PENDENTE":
            conn.rollback()
            raise ValueError(
                "Esta análise não aguarda decisão do gerente"
                + (f" (situação: {row['status_validacao'].lower()})." if row["status_validacao"] else ".")
            )
        agora = _now()
        decisao = {
            "id": f"dec-{uuid4().hex}", "analise_id": analise_id, "referencia": row["referencia"], "acao": acao,
            "status": status, "justificativa": justificativa[:2000], "conteudo_corrigido": conteudo_corrigido[:8000],
            "usuario": usuario[:120], "created_at": agora,
        }
        conn.execute(
            """INSERT INTO decisoes_gerente (id, analise_id, referencia, acao, status, justificativa, conteudo_corrigido, usuario, created_at)
               VALUES (:id, :analise_id, :referencia, :acao, :status, :justificativa, :conteudo_corrigido, :usuario, :created_at)""",
            decisao,
        )
        conn.execute(
            "UPDATE analises SET status_validacao = ?, validado_em = ?, validado_por = ? WHERE id = ?",
            (status, agora, usuario[:120], analise_id),
        )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"decisao": decisao, "analise": get_analise(analise_id)}


def list_decisoes_gerente(analise_id: str = "", limite: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    if analise_id:
        rows = conn.execute("SELECT * FROM decisoes_gerente WHERE analise_id = ? ORDER BY created_at DESC", (analise_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM decisoes_gerente ORDER BY created_at DESC LIMIT ?", (limite,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def list_analises(escopo: str = "", limite: int = 20, status_validacao: str = "") -> List[Dict[str, Any]]:
    conn = get_connection()
    conditions, params = [], []
    if escopo:
        conditions.append("escopo = ?")
        params.append(escopo)
    if status_validacao:
        conditions.append("status_validacao = ?")
        params.append(status_validacao)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(f"SELECT * FROM analises {where} ORDER BY created_at DESC LIMIT ?", (*params, limite)).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["dados"] = json.loads(item.pop("dados_json") or "{}")
        result.append(item)
    return result


# --- Fila de eventos de saída para o n8n ---------------------------------------------------------

def enqueue_evento(evento: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    item = {"id": f"evt-{uuid4().hex}", "evento": evento, "payload_json": json.dumps(payload, ensure_ascii=False), "created_at": _now()}
    conn = get_connection()
    conn.execute(
        "INSERT INTO eventos_saida (id, evento, payload_json, created_at) VALUES (:id, :evento, :payload_json, :created_at)",
        item,
    )
    conn.commit()
    conn.close()
    return {"id": item["id"], "evento": evento, "payload": payload, "created_at": item["created_at"]}


def list_eventos(status: str = "", limite: int = 100) -> List[Dict[str, Any]]:
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM eventos_saida WHERE status = ? ORDER BY created_at LIMIT ?", (status, limite)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM eventos_saida ORDER BY created_at DESC LIMIT ?", (limite,)).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        result.append(item)
    return result


def mark_evento(evento_id: str, ok: bool, erro: str = "") -> None:
    conn = get_connection()
    if ok:
        conn.execute(
            "UPDATE eventos_saida SET status = 'ENVIADO', tentativas = tentativas + 1, ultimo_erro = '', enviado_at = ? WHERE id = ?",
            (_now(), evento_id),
        )
    else:
        conn.execute(
            "UPDATE eventos_saida SET status = 'FALHA', tentativas = tentativas + 1, ultimo_erro = ? WHERE id = ?",
            (erro[:500], evento_id),
        )
    conn.commit()
    conn.close()
