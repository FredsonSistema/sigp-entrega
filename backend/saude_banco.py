"""Saúde do banco SQLite do SIGp: verificação, tamanho, arquivos, backup com rodízio e manutenção.

Backup: API de backup do SQLite (cópia consistente com o sistema rodando) em data/backups. Cada cópia é
aberta e verificada (quick_check + contagem) logo depois: é o teste de restauração. Rodízio: a mais recente
de cada um dos últimos 7 dias e a mais recente de cada uma das 4 semanas anteriores.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

TABELAS = ("notas_recebidas", "notas_lancadas", "notas_pagas", "faturas_locais", "locais", "extracao_feedback")
PREFIXO = "sigp-"
BACKUP_MAXIMO_HORAS = 26


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _tamanho(caminho: Path) -> int:
    try:
        return caminho.stat().st_size
    except OSError:
        return 0


def _contagens(conn: sqlite3.Connection) -> Dict[str, Optional[int]]:
    existentes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return {t: (conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in existentes else None) for t in TABELAS}  # noqa: S608 (nomes fixos)


def listar_backups(pasta: Path) -> List[Dict[str, Any]]:
    if not pasta.is_dir():
        return []
    itens = []
    for arquivo in sorted(pasta.glob(f"{PREFIXO}*.db"), reverse=True):
        try:
            quando = datetime.strptime(arquivo.stem[len(PREFIXO):], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        itens.append({"arquivo": arquivo.name, "em": quando.isoformat(), "bytes": _tamanho(arquivo), "_quando": quando, "_caminho": arquivo})
    return itens


def _publico(backup: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in backup.items() if not k.startswith("_")}


def arquivos_orfaos(conn: sqlite3.Connection, pastas: Dict[str, Path]) -> Dict[str, Any]:
    """PDFs/XMLs na pasta sem registro no banco (órfãos) e registros cujo arquivo sumiu (ausentes)."""
    referenciados = set()
    for tabela, coluna in (("notas_recebidas", "arquivo_storage"), ("faturas_locais", "arquivo_storage"),
                           ("faturas_provedores", "arquivo_storage")):
        try:
            referenciados |= {r[0] for r in conn.execute(f"SELECT {coluna} FROM {tabela} WHERE {coluna} != ''")}  # noqa: S608
        except sqlite3.Error:
            pass
    try:
        for (dados,) in conn.execute("SELECT dados_json FROM notas_recebidas WHERE dados_json LIKE '%xmlArquivo%'"):
            import json
            storage = ((json.loads(dados or "{}").get("xmlArquivo") or {}).get("storage") or "")
            if storage:
                referenciados.add(storage)
    except (sqlite3.Error, ValueError):
        pass
    resultado: Dict[str, Any] = {"pastas": {}, "orfaos": 0, "ausentes": 0}
    presentes = set()
    for nome, pasta in pastas.items():
        arquivos = [a for a in pasta.iterdir() if a.is_file()] if pasta.is_dir() else []
        presentes |= {a.name for a in arquivos}
        resultado["pastas"][nome] = {"arquivos": len(arquivos), "bytes": sum(_tamanho(a) for a in arquivos)}
    resultado["orfaos"] = len(presentes - referenciados)
    resultado["ausentes"] = len(referenciados - presentes)
    return resultado


def verificar(db_path: Path, backup_dir: Path, pastas: Dict[str, Path], completo: bool = False) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        checagem = "integrity_check" if completo else "quick_check"
        resultado_check = [r[0] for r in conn.execute(f"PRAGMA {checagem}").fetchall()]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        paginas = conn.execute("PRAGMA page_count").fetchone()[0]
        livres = conn.execute("PRAGMA freelist_count").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        contagens = _contagens(conn)
        arquivos = arquivos_orfaos(conn, pastas)
    finally:
        conn.close()
    integro = resultado_check == ["ok"]
    backups = listar_backups(backup_dir)
    ultimo = backups[0] if backups else None
    idade_horas = round((_agora() - ultimo["_quando"]).total_seconds() / 3600, 1) if ultimo else None
    avisos = []
    if not integro:
        avisos.append("A verificação do banco encontrou problemas: restaure o último backup verificado.")
    if ultimo is None:
        avisos.append("Nenhum backup automático ainda.")
    elif idade_horas > BACKUP_MAXIMO_HORAS:
        avisos.append(f"Último backup há {idade_horas:.0f} horas (o esperado é 1 por dia).")
    if livres and paginas and livres / paginas > 0.2:
        avisos.append("Mais de 20% do arquivo é espaço livre: rode a manutenção.")
    if arquivos["ausentes"]:
        avisos.append(f"{arquivos['ausentes']} registro(s) apontam para arquivo que não existe mais.")
    status = "erro" if not integro else ("atencao" if avisos else "ok")
    return {
        "status": status,
        "verificacao": {"tipo": checagem, "ok": integro, "detalhes": resultado_check[:5]},
        "tamanho": {"bytes": page_size * paginas, "livresBytes": page_size * livres,
                    "walBytes": _tamanho(Path(str(db_path) + "-wal")), "journal": journal},
        "tabelas": contagens,
        "arquivos": arquivos,
        "backups": {"quantidade": len(backups), "ultimo": _publico(ultimo) if ultimo else None,
                    "idadeHoras": idade_horas, "pasta": backup_dir.name},
        "avisos": avisos,
        "verificadoEm": _agora().isoformat(),
    }


def _manter(backups: List[Dict[str, Any]], dias: int = 7, semanas: int = 4) -> set:
    manter, dias_vistos, semanas_vistas = set(), set(), set()
    for b in backups:  # do mais novo para o mais antigo
        dia = b["_quando"].date()
        if len(dias_vistos) < dias and dia not in dias_vistos:
            dias_vistos.add(dia)
            manter.add(b["arquivo"])
            continue
        semana = dia.isocalendar()[:2]
        if dia in dias_vistos:
            continue
        if len(semanas_vistas) < semanas and semana not in semanas_vistas:
            semanas_vistas.add(semana)
            manter.add(b["arquivo"])
    return manter


def fazer_backup(db_path: Path, backup_dir: Path, agora: Optional[datetime] = None) -> Dict[str, Any]:
    agora = agora or _agora()
    backup_dir.mkdir(parents=True, exist_ok=True)
    destino = backup_dir / f"{PREFIXO}{agora.strftime('%Y%m%d-%H%M%S')}.db"
    temporario = destino.with_suffix(".tmp")
    origem = sqlite3.connect(db_path)
    try:
        copia = sqlite3.connect(temporario)
        try:
            origem.backup(copia)
        finally:
            copia.close()
        contagem_origem = _contagens(origem)
    finally:
        origem.close()
    # Teste de restauração: a cópia abre, passa na verificação e tem as mesmas contagens.
    copia = sqlite3.connect(temporario)
    try:
        check = copia.execute("PRAGMA quick_check").fetchone()[0]
        contagem_copia = _contagens(copia)
    finally:
        copia.close()
    if check != "ok" or contagem_copia != contagem_origem:
        temporario.unlink(missing_ok=True)
        raise RuntimeError("A cópia de segurança não passou na verificação; o backup anterior foi mantido.")
    temporario.replace(destino)
    backups = listar_backups(backup_dir)
    manter = _manter(backups)
    removidos = []
    for b in backups:
        if b["arquivo"] not in manter:
            b["_caminho"].unlink(missing_ok=True)
            removidos.append(b["arquivo"])
    return {"arquivo": destino.name, "bytes": _tamanho(destino), "verificado": True,
            "contagens": contagem_copia, "removidos": removidos, "mantidos": len(manter)}


def manutencao(db_path: Path, vacuum_se_livre_acima: float = 0.2) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA optimize")
        conn.execute("ANALYZE")
        checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        paginas = conn.execute("PRAGMA page_count").fetchone()[0]
        livres = conn.execute("PRAGMA freelist_count").fetchone()[0]
        vacuum = bool(paginas and livres / paginas > vacuum_se_livre_acima)
        if vacuum:
            conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()
    return {"optimize": True, "analyze": True, "walCheckpoint": list(checkpoint) if checkpoint else None, "vacuum": vacuum}
