"""Confere que nenhum caso de teste repete um cenário do treino do fine-tuning (dataset.jsonl, split train).

Para cada caso de casos-finais.json e casos-fora-escopo.json, compara a descrição da cobrança e o provedor com cada
exemplo de treino:
  - repetição exata: mesma descrição (sem acento, maiúsculas e pontuação) ou mesma descrição e mesmo provedor;
  - parecido: semelhança de Jaccard entre as palavras da descrição >= 0,6 (limite fixado aqui, antes de rodar).
Saída: sqlserver/evidence/parte3/sobreposicao-treino.json. Os casos marcados como "repete" são medidos à parte na comparação do fine-tuning (gerar_comparacao.py), para o resultado "fora do treino" usar só os que não repetem.
Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/ia/finetuning/verificar_sobreposicao.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

DIR = Path(__file__).resolve().parent
IA = DIR.parent
SAIDA = IA.parent / "sqlserver" / "evidence" / "parte3" / "sobreposicao-treino.json"
LIMITE_PARECIDO = 0.6


def norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", t))


def palavras(texto: str) -> set[str]:
    return set(norm(texto).split())


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def treino() -> list[dict]:
    itens = []
    for linha in (DIR / "dataset.jsonl").read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        r = json.loads(linha)
        if r["split"] != "train":
            continue
        m = re.match(r"Cobrança: (.*?), R\$ [\d.]+\. Provedor: (.*?)\. ", r["user"])
        if not m:
            raise RuntimeError(f"Formato inesperado em {r['id']}")
        itens.append({"id": r["id"], "descricao": m.group(1), "provedor": m.group(2), "classe": r["classification"]})
    return itens


def casos() -> list[dict]:
    spec = __import__("importlib.util").util.spec_from_file_location("sigp_academic_ai_sobrep", IA / "app.py")
    app = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(app)
    res = []
    for arquivo in ("casos-finais.json", "casos-fora-escopo.json"):
        for c in json.loads((IA / arquivo).read_text(encoding="utf-8"))["casos"]:
            inv = app._normalize_invoice(dict(c["invoice"]))
            res.append({"conjunto": arquivo, "id": c["id"], "descricao": inv.get("description") or "",
                        "provedor": inv.get("provider") or ""})
    return res


def main() -> int:
    tr = treino()
    resultado = []
    for c in casos():
        pc = palavras(c["descricao"])
        melhor = max(tr, key=lambda t: jaccard(pc, palavras(t["descricao"])))
        sim = jaccard(pc, palavras(melhor["descricao"]))
        exata = any(norm(t["descricao"]) == norm(c["descricao"]) for t in tr)
        mesmo_par = any(norm(t["descricao"]) == norm(c["descricao"]) and norm(t["provedor"]) == norm(c["provedor"]) for t in tr)
        resultado.append({**c, "mais_parecido_no_treino": melhor["id"], "descricao_treino": melhor["descricao"],
                          "semelhanca": round(sim, 3), "descricao_igual": exata, "descricao_e_provedor_iguais": mesmo_par,
                          "repete": exata or mesmo_par or sim >= LIMITE_PARECIDO})
    provedores_treino = sorted({t["provedor"] for t in tr})
    provedores_teste = sorted({c["provedor"] for c in resultado if c["provedor"]})
    saida = {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "limite_parecido_jaccard": LIMITE_PARECIDO,
        "exemplos_de_treino": len(tr),
        "casos_de_teste": len(resultado),
        "casos_que_repetem_o_treino": [r["id"] for r in resultado if r["repete"]],
        "maior_semelhanca": max(r["semelhanca"] for r in resultado),
        "provedores_em_comum": sorted({norm(p) for p in provedores_treino} & {norm(p) for p in provedores_teste}),
        "casos": resultado,
    }
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(resultado)} casos × {len(tr)} exemplos de treino · repetem: {saida['casos_que_repetem_o_treino'] or 'nenhum'} · "
          f"maior semelhança {saida['maior_semelhanca']} · provedores em comum: {saida['provedores_em_comum'] or 'nenhum'}")
    for r in sorted(resultado, key=lambda r: -r["semelhanca"])[:5]:
        print(f"  {r['id']:<6} {r['semelhanca']:.3f} {r['descricao'][:50]!r} ~ {r['mais_parecido_no_treino']} {r['descricao_treino']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
