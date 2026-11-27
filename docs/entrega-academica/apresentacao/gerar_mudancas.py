"""Gera docs/entrega-academica/MUDANCAS-DESDE-ENTREGA-2.md: o que melhorou (antes → depois, medido), o que foi corrigido
(cada item do histórico que reprovou e foi retestado) e o que permaneceu inalterado (conferido nas evidências e no Git).
Mesmos dados dos relatórios (dados.py); nenhum número digitado à mão.
Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/apresentacao/gerar_mudancas.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import dados  # noqa: E402

ENTREGA = DIR.parent
SAIDA = ENTREGA / "MUDANCAS-DESDE-ENTREGA-2.md"


def link(texto: str) -> str:
    """Transforma os caminhos de "evidencia" em links relativos à pasta da entrega."""
    partes = []
    for item in (x.strip() for x in texto.split("·")):
        caminho, _, resto = item.partition(" ")
        if caminho == "abrir-sigp.ps1":
            alvo = "../../abrir-sigp.ps1"   # na raiz do repositório da entrega
        elif caminho.startswith("entrega/"):
            alvo = "../../" + caminho
        elif caminho.endswith(".json") and "/" not in caminho:
            alvo = "sqlserver/evidence/parte3/" + caminho
        else:
            alvo = caminho
        partes.append(f"[`{caminho}`]({alvo})" + (f" {resto}" if resto else "") if "." in caminho.split("/")[-1] else item)
    return " · ".join(partes)


def curto(texto: str, n: int = 230) -> str:
    texto = re.sub(r"\s+", " ", texto.replace("|", "/")).strip()
    return texto if len(texto) <= n else texto[: texto.rfind(" ", 0, n)] + "…"


def main() -> None:
    d = dados.carregar()
    M = d["mudancas"]
    e2 = M["entrega2"]
    L = ["# Mudanças desde a Entrega 2", "",
         "Gerado por [`apresentacao/gerar_mudancas.py`](apresentacao/gerar_mudancas.py) com os mesmos dados dos relatórios; nenhum número "
         "foi digitado à mão. \"Antes\" é a primeira medição desta etapa, feita no sistema como estava na Entrega 2 "
         f"(a avaliação da Entrega 2, de {e2['data']}, usava {e2['casos']} casos e o prompt {', '.join('v' + p for p in e2['prompt'])}); "
         "\"depois\" é a medição final, no sistema entregue. O detalhe de cada item está no documento da última coluna e em "
         "[`historico-evolucao.md`](historico-evolucao.md).", "",
         "## Mudança de interface: da web para uma janela do Windows", "",
         "Na Entrega 2 o SIGp abria como uma aba do navegador. Agora o atalho **SIGp** da área de trabalho abre o sistema numa **janela "
         "própria do Windows**: sem barra de endereço e sem abas, com título e ícone próprios na barra de tarefas. É o Microsoft Edge em "
         "modo aplicativo (`--app`), com um perfil separado, que já vem no Windows 10 e 11. Se o computador foi reiniciado, o atalho liga o "
         "Docker e os containers e espera a tela responder. As telas são as mesmas: mudou onde elas abrem, não o que fazem. Tudo continua "
         "local (http://127.0.0.1:8000). Código: [`abrir-sigp.ps1`](../../abrir-sigp.ps1), na raiz do repositório da entrega; o instalador cria o atalho "
         "(`SIGp.lnk`). Teste e reteste: H-48 no histórico.", "",
         "## O que melhorou", "",
         "| Tema | Antes | Depois | Evidência |", "|---|---|---|---|"]
    L += [f"| {x['tema']} | {x['antes']} | {x['depois']} | {link(x['evidencia'])} |" for x in M["melhorado"]]
    L += ["", "## O que foi corrigido", "",
          f"Cada linha é um teste que **reprovou** na primeira execução, foi corrigido e retestado ({len(M['corrigido'])} itens). "
          "O texto completo (falha, correção, reteste e commit) está em [`historico-evolucao.md`](historico-evolucao.md).", "",
          "| # | Data | Área | O que foi testado | Reteste | Commit |", "|---|---|---|---|---|---|"]
    L += [f"| {x['id']} | {x['data']} | {x['area']} | {curto(x['teste'])} | {curto(x['reteste'], 160)} | `{x['commit']}` |" for x in M["corrigido"]]
    L += ["", "## O que permaneceu inalterado", "",
          "| O quê | Como está | Onde conferir |", "|---|---|---|"]
    L += [f"| {x['item']} | {x['como']} | {link(x['evidencia'])} |" for x in M["inalterado"]]
    L += ["", "## Respostas aos comentários da professora", "",
          "A tabela com uma linha por comentário da devolutiva da Entrega 2 está no [`README.md`](README.md) e no "
          "[`relatorio-final.pdf`](relatorio-final.pdf).", ""]
    SAIDA.write_text("\n".join(L), encoding="utf-8")
    print(f"ok: {SAIDA}")


if __name__ == "__main__":
    main()
