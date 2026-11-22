"""Verifica que nenhum segredo vazou nos fluxos do n8n exportados (requisito da entrega final).

Olha (1) todos os arquivos JSON de workflow rastreados no Git e (2), com --ao-vivo, uma exportação temporária de todos
os workflows do n8n em execução (container sigp_n8n), apagada no fim. Regras:

  FALHA  valor real de um segredo dos arquivos .env (procura o próprio valor, nunca o imprime)
  FALHA  cabeçalho ou parâmetro de autenticação com valor literal (Authorization, X-API-Key, token, senha...) em vez de
         expressão {{ $env... }} ou credencial do n8n
  FALHA  padrões de chave conhecidos: Bearer literal, JWT, chave privada, chaves de API (Google, GitHub, OpenAI, AWS),
         token de bot do Telegram, chave de integração do SIGp (sigp_...)
  FALHA  bloco "credentials" com algo além de id e nome (a credencial do n8n fica no banco do n8n, não no arquivo)
  FALHA  pinData com dados (execuções gravadas no arquivo podem trazer e-mails e notas reais)
  AVISO  endereço de e-mail no arquivo (dado pessoal; não é segredo, mas o repositório é público)
  AVISO  texto de exemplo num campo de autenticação (ex.: COLE_AQUI_A_APIKEY): não vaza nada, mas convida a colar a
         chave no nó; o certo é {{ $env... }}

Resultado: sqlserver/evidence/parte3/segredos-n8n.json. Nenhum valor encontrado é gravado: só o arquivo, a regra, o
caminho no JSON e um trecho mascarado. Sai com código 1 se houver FALHA.
Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/ia/verificar_segredos_n8n.py --ao-vivo
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
SAIDA = RAIZ / "docs" / "entrega-academica" / "sqlserver" / "evidence" / "parte3" / "segredos-n8n.json"
ARQUIVOS_ENV = [RAIZ / ".env", RAIZ / "docs" / "entrega-academica" / "sqlserver" / ".env.academic"]
NOME_SEGREDO = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|SENHA|PASS|APIKEY|CREDENTIAL|CNPJS)", re.I)
CAMPO_SENSIVEL = re.compile(r"^(authorization|x-api-key|api[-_ ]?key|apikey|token|access[-_ ]?token|refresh[-_ ]?token|"
                            r"client[-_ ]?secret|secret|password|senha|bearer)$", re.I)
EXPRESSAO_OK = re.compile(r"\{\{.*(\$env|\$credentials|\$vars|\$secrets)", re.S)
PADROES = {
    "bearer_literal": re.compile(r"Bearer\s+(?!\{\{)[A-Za-z0-9._~+/=-]{20,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "chave_privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "telegram_bot_token": re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
    "chave_integracao_sigp": re.compile(r"\bsigp_[A-Za-z0-9_-]{24,}\b"),
}
EXEMPLO = re.compile(r"^[A-Z0-9_ -]*(COLE|COLOQUE|SEU|SUA|AQUI|TROQUE|EXEMPLO|PLACEHOLDER|CHANGEME)[A-Z0-9_ -]*$")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_EXEMPLO = re.compile(r"@(example\.(com|org)|exemplo\.(com|local)|teste\.local|sigp\.local|localhost)$", re.I)


def mascarar(texto: str) -> str:
    texto = str(texto)
    return texto[:3] + "…" + f"({len(texto)} caracteres)" if len(texto) > 6 else "…"


def segredos_env() -> dict[str, str]:
    """Valores dos .env cujos nomes indicam segredo (só em memória; nunca são gravados nem impressos)."""
    valores = {}
    for arq in ARQUIVOS_ENV:
        if not arq.exists():
            continue
        for linha in arq.read_text(encoding="utf-8-sig").splitlines():
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", linha.strip())
            if m and NOME_SEGREDO.search(m.group(1)) and len(m.group(2).strip()) >= 8:
                valores[f"{arq.name}:{m.group(1)}"] = m.group(2).strip()
    return valores


def eh_workflow(dados) -> bool:
    if isinstance(dados, list):
        return any(isinstance(x, dict) and isinstance(x.get("nodes"), list) for x in dados)
    return isinstance(dados, dict) and isinstance(dados.get("nodes"), list)


def percorrer(obj, caminho="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from percorrer(v, f"{caminho}.{k}")
        yield caminho, obj
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from percorrer(v, f"{caminho}[{i}]")


def verificar(arquivo: Path, texto: str, segredos: dict[str, str]) -> dict:
    falhas, avisos = [], []
    for nome, valor in segredos.items():
        if valor in texto:
            falhas.append({"regra": "valor_de_segredo_do_env", "onde": nome.split(":", 1)[1], "trecho": mascarar(valor)})
    for regra, rx in PADROES.items():
        for m in rx.finditer(texto):
            falhas.append({"regra": regra, "onde": f"posição {m.start()}", "trecho": mascarar(m.group(0))})
    dados = json.loads(texto)
    workflows = dados if isinstance(dados, list) else [dados]
    for wf in workflows:
        if not isinstance(wf, dict):
            continue
        pin = wf.get("pinData")
        if pin:
            falhas.append({"regra": "pinData_com_dados", "onde": "$.pinData", "trecho": f"{len(pin)} nó(s) com dados gravados"})
        for caminho, d in percorrer(wf.get("nodes", []), "$.nodes"):
            # parâmetro {"name": "Authorization", "value": "..."} (cabeçalhos, query, corpo)
            nome = d.get("name") if isinstance(d.get("name"), str) else None
            if nome and CAMPO_SENSIVEL.match(nome.strip()) and "value" in d:
                v = d.get("value")
                if isinstance(v, str) and v.strip() and not EXPRESSAO_OK.search(v):
                    if EXEMPLO.match(v.strip()):
                        avisos.append({"regra": "texto_de_exemplo_em_autenticacao", "onde": f"{caminho} ({nome})", "quantidade": 1})
                    else:
                        falhas.append({"regra": "autenticacao_com_valor_literal", "onde": f"{caminho} ({nome})", "trecho": mascarar(v)})
            # chaves sensíveis com texto literal dentro dos parâmetros do nó
            for k, v in d.items():
                if k in ("name", "value", "credentials") or not isinstance(v, str) or not v.strip():
                    continue
                if CAMPO_SENSIVEL.match(k) and not EXPRESSAO_OK.search(v):
                    falhas.append({"regra": "parametro_sensivel_literal", "onde": f"{caminho}.{k}", "trecho": mascarar(v)})
            cred = d.get("credentials")
            if isinstance(cred, dict):
                for tipo, ref in cred.items():
                    extra = set(ref) - {"id", "name"} if isinstance(ref, dict) else {"(não é referência)"}
                    if extra:
                        falhas.append({"regra": "credencial_com_conteudo", "onde": f"{caminho}.credentials.{tipo}",
                                       "trecho": f"campos {sorted(extra)}"})
    emails = sorted({e for e in EMAIL.findall(texto) if not EMAIL_EXEMPLO.search(e)})
    if emails:
        avisos.append({"regra": "email_no_arquivo", "quantidade": len(emails),
                       "exemplos": [e[0] + "***@" + e.split("@", 1)[1] for e in emails[:5]]})
    return {"arquivo": arquivo.as_posix(), "falhas": falhas, "avisos": avisos, "ok": not falhas}


def arquivos_rastreados() -> list[Path]:
    r = subprocess.run(["git", "ls-files", "*.json"], cwd=RAIZ, capture_output=True, text=True, check=True)
    return [RAIZ / l for l in r.stdout.splitlines() if l.strip()]


def exportar_ao_vivo(destino: Path) -> list[Path]:
    dentro = "/tmp/sigp_export_verificacao"
    subprocess.run(["docker", "exec", "sigp_n8n", "sh", "-c", f"rm -rf {dentro} && mkdir -p {dentro}"], check=True, capture_output=True)
    r = subprocess.run(["docker", "exec", "sigp_n8n", "n8n", "export:workflow", "--all", "--separate", f"--output={dentro}"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"export:workflow falhou: {r.stderr[-300:]}")
    subprocess.run(["docker", "cp", f"sigp_n8n:{dentro}/.", str(destino)], check=True, capture_output=True)
    subprocess.run(["docker", "exec", "sigp_n8n", "rm", "-rf", dentro], capture_output=True)
    return sorted(destino.glob("*.json"))


def main() -> int:
    segredos = segredos_env()
    resultados = []
    for arq in arquivos_rastreados():
        texto = arq.read_text(encoding="utf-8-sig")
        try:
            if not eh_workflow(json.loads(texto)):
                continue
        except json.JSONDecodeError:
            continue
        r = verificar(arq.relative_to(RAIZ), texto, segredos)
        r["origem"] = "repositório"
        resultados.append(r)
    ao_vivo = []
    if "--ao-vivo" in sys.argv:
        tmp = Path(tempfile.mkdtemp(prefix="sigp-n8n-"))
        try:
            for arq in exportar_ao_vivo(tmp):
                dados = json.loads(arq.read_text(encoding="utf-8-sig"))
                r = verificar(Path("n8n-ao-vivo") / f"{dados.get('name', arq.stem)}.json", arq.read_text(encoding="utf-8-sig"), segredos)
                r["origem"] = "n8n em execução (exportação temporária)"
                r["ativo"] = bool(dados.get("active"))
                ao_vivo.append(r)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    todos = resultados + ao_vivo
    resumo = {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "segredos_procurados": len(segredos),
        "arquivos_do_repositorio": len(resultados),
        "workflows_ao_vivo": len(ao_vivo),
        "arquivos_com_falha": [r["arquivo"] for r in todos if not r["ok"]],
        "arquivos_com_aviso": [r["arquivo"] for r in todos if r["avisos"]],
        "resultado": "APROVADO" if all(r["ok"] for r in todos) else "REPROVADO",
        "arquivos": todos,
    }
    texto = json.dumps(resumo, ensure_ascii=False, indent=2)
    if any(v in texto for v in segredos.values()):
        sys.exit("Um segredo apareceu no relatório; nada foi gravado.")
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(texto + "\n", encoding="utf-8")
    for r in todos:
        sinal = "OK   " if r["ok"] else "FALHA"
        extra = "".join(f" · aviso: {a['regra']} ({a.get('quantidade', 1)})" for a in r["avisos"])
        print(f"{sinal} {r['arquivo']}{extra}")
        for f in r["falhas"]:
            print(f"        {f['regra']}: {f['onde']} {f['trecho']}")
    print(f"\n{resumo['resultado']} · {len(segredos)} segredos do .env procurados · {len(resultados)} arquivos do repositório · "
          f"{len(ao_vivo)} workflows ao vivo · falhas em {len(resumo['arquivos_com_falha'])} · avisos em {len(resumo['arquivos_com_aviso'])}")
    return 0 if resumo["resultado"] == "APROVADO" else 1


if __name__ == "__main__":
    sys.exit(main())
