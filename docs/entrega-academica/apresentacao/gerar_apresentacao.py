"""Gera docs/entrega-academica/apresentacao.html: a página interativa da apresentação final.

Junta o modelo (apresentacao/modelo.html: estrutura, estilo e interação) com os dados das evidências (dados.py).
A página funciona sozinha, sem internet nem bibliotecas externas. Nenhum número é digitado à mão: rode de novo depois de
qualquer nova medição.
Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/apresentacao/gerar_apresentacao.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import dados  # noqa: E402

SAIDA = DIR.parent / "apresentacao.html"


def main() -> None:
    d = dados.carregar()
    faltam = [k for k in ("ia_antes", "ia_depois", "finetuning") if not d.get(k)]
    if faltam:
        sys.exit(f"Faltam evidências para: {', '.join(faltam)}")
    modelo = (DIR / "modelo.html").read_text(encoding="utf-8")
    if "/*__DADOS__*/" not in modelo:
        sys.exit("O modelo não tem o marcador /*__DADOS__*/.")
    # "</" dentro de um <script> fecharia a tag: escapa a barra.
    bloco = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    SAIDA.write_text(modelo.replace("/*__DADOS__*/", bloco), encoding="utf-8")
    print(f"ok: {SAIDA} ({SAIDA.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
