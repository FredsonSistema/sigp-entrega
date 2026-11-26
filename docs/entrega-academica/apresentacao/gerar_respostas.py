"""Escreve a seção "Respostas aos comentários da professora" nos READMEs, entre os marcadores
<!-- respostas-professora:inicio --> e <!-- respostas-professora:fim -->, com os mesmos dados dos relatórios (dados.py).
Nenhum número é digitado à mão: as respostas são montadas em dados._respostas a partir das evidências.

  docs/entrega-academica/README.md   links relativos à pasta da entrega
  entrega/README.md                  README do pacote (o mesmo texto, com links a partir da raiz do pacote)

Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/apresentacao/gerar_respostas.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import dados  # noqa: E402

ENTREGA = DIR.parent
RAIZ = ENTREGA.parent.parent
INICIO, FIM = "<!-- respostas-professora:inicio -->", "<!-- respostas-professora:fim -->"
DESTINOS = [(ENTREGA / "README.md", ""), (RAIZ / "entrega" / "README.md", "docs/entrega-academica/")]


def _evidencia(texto: str, prefixo: str) -> str:
    partes = []
    for item in (x.strip() for x in texto.split("·")):
        caminho = item.split(" ")[0]
        if caminho.startswith("http"):
            partes.append(f"<{caminho}>")
        elif "/" in caminho or caminho.endswith((".md", ".json", ".py")):
            alvo = caminho if caminho.startswith(("ia/", "seguranca/", "sqlserver/", "tests/")) else f"sqlserver/evidence/parte3/{caminho}"
            alvo = alvo.replace("evidence/parte3/otimizacao/*.sqlplan", "evidence/parte3/otimizacao/")
            alvo = re.sub(r"^sqlserver/evidence/parte3/evidence/", "sqlserver/evidence/", alvo)
            link = f"../../{alvo}" if alvo.startswith("tests/") and not prefixo else alvo if alvo.startswith("tests/") else prefixo + alvo
            resto = item[len(caminho):].strip()
            partes.append(f"[`{caminho}`]({link})" + (f" {resto}" if resto else ""))
        else:
            partes.append(item)
    return " · ".join(partes)


def secao(prefixo: str) -> str:
    d = dados.carregar()
    L = [INICIO, "## Respostas aos comentários da professora", "",
         "Devolutiva da Entrega 2 (Prof.ª Bruna). Seção gerada por `docs/entrega-academica/apresentacao/gerar_respostas.py` com os "
         "mesmos dados dos relatórios; os números vêm das evidências.", "",
         "| Disciplina | Comentário | O que foi feito | Evidência |", "|---|---|---|---|"]
    for r in d["respostas_professora"]:
        L.append(f"| {r['disciplina']} | {r['comentario']} | {r['resposta']} | {_evidencia(r['evidencia'], prefixo)} |")
    L += ["", FIM]
    return "\n".join(L)


def main() -> None:
    for caminho, prefixo in DESTINOS:
        raw = caminho.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        t = raw.decode("utf-8-sig")
        crlf = "\r\n" in t
        t = t.replace("\r\n", "\n")
        novo = secao(prefixo)
        if INICIO in t:
            t = re.sub(re.escape(INICIO) + r".*?" + re.escape(FIM), lambda _m: novo, t, flags=re.S)
        else:
            # logo antes da primeira seção depois do título e da introdução
            pos = t.index("\n## ", t.index("\n## ") + 1) if prefixo == "" else t.index("\n## ")
            t = t[:pos + 1] + novo + "\n\n" + t[pos + 1:]
        if crlf:
            t = t.replace("\n", "\r\n")
        caminho.write_bytes((b"\xef\xbb\xbf" if bom else b"") + t.encode("utf-8"))
        print(f"ok: {caminho}")


if __name__ == "__main__":
    main()
