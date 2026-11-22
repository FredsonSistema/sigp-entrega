"""Gera ia/escolha-modelo-triagem.md: a escolha do modelo da triagem do Gmail, com o critério fixado ANTES da medição
(escolha-modelo-criterio.md, commit anterior ao da evidência), os riscos, as duas medições (antes e depois da correção da
resposta sem fim) e a escolha que sai do critério aplicado por código. Nenhum número é digitado aqui.
Fontes: sqlserver/evidence/parte3/triagem-modelos.json (primeira medição) e triagem-modelos-corrigido.json (com a correção),
ambas de tests/n8n/comparar_modelos_triagem.js.
Uso, na raiz do projeto:  python docs/entrega-academica/ia/gerar_escolha_modelo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

IA = Path(__file__).resolve().parent
EV = IA.parent / "sqlserver" / "evidence" / "parte3"
SAIDA = IA / "escolha-modelo-triagem.md"
REFERENCIA = "qwen2.5:3b"
LEVE = "qwen2.5:0.5b"
TAMANHO_MB = {"qwen2.5:0.5b": 397, "qwen2.5:1.5b": 986, "qwen2.5:3b": 1900}  # `ollama list` na medição
# "Diferença grande" (item 4): o critério não definia; definição usada, escrita junto com a correção: o 3B responde a todos
# os documentos, sem tempo esgotado, e acerta pelo menos 20 pontos percentuais a mais de campos que o modelo leve.
DIFERENCA_GRANDE_PP = 20


def pct(a: int, t: int) -> float:
    return 100.0 * a / t if t else 0.0


def br(v, casas=1) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def carregar() -> tuple[dict, dict | None]:
    primeira = json.loads((EV / "triagem-modelos.json").read_text(encoding="utf-8"))
    arq = EV / "triagem-modelos-corrigido.json"
    corrigida = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
    return primeira, corrigida


def escolher(modelos: dict, variante: str) -> tuple[str | None, list[str]]:
    """Itens 1 a 3 do critério. Devolve (modelo escolhido ou None, explicação passo a passo)."""
    passos = []
    ref = modelos.get(f"{REFERENCIA} · {variante}")
    if not ref:
        return None, ["Sem a medição do 3B nesta variante: não há referência para o critério 2."]
    ref_pct = pct(ref["resumo"]["campos_certos"], ref["resumo"]["campos_total"])
    candidatos = []
    for d in modelos.values():
        if d["variante"] != variante:
            continue
        r = d["resumo"]
        p = pct(r["campos_certos"], r["campos_total"])
        c1 = not r["erros_graves"] and not r.get("tempo_esgotado")
        c2 = p >= ref_pct - 10
        passos.append(f"`{d['modelo']}`: critério 1 {'passa' if c1 else 'não passa'} ({len(r['erros_graves'])} erro(s) grave(s), "
                      f"{r.get('tempo_esgotado', 0)} tempo(s) esgotado(s)); critério 2 {'passa' if c2 else 'não passa'} "
                      f"({br(p)}% dos campos contra {br(ref_pct)}% do 3B).")
        if c1 and c2:
            candidatos.append(d["modelo"])
    if not candidatos:
        passos.append("Nenhum modelo passa nos critérios 1 e 2: vale o item 4 do critério.")
        return None, passos
    escolhido = min(candidatos, key=lambda m: TAMANHO_MB.get(m, 10 ** 6))
    passos.append(f"Critério 3: entre {', '.join(f'`{m}`' for m in candidatos)}, o menor download é `{escolhido}`.")
    return escolhido, passos


def decidir(modelos: dict, variante: str) -> dict:
    """Critério completo, com o item 4 (opção D, leve, ou C, 3B, se a diferença for grande)."""
    escolhido, passos = escolher(modelos, variante)
    if escolhido:
        return {"opcao": "menor que passou", "padrao": escolhido, "opcional": REFERENCIA if escolhido != REFERENCIA else None, "passos": passos}
    ref = modelos[f"{REFERENCIA} · {variante}"]["resumo"]
    leve = modelos.get(f"{LEVE} · {variante}", {}).get("resumo")
    total = len(modelos[f"{REFERENCIA} · {variante}"]["casos"])
    confiavel = not ref.get("tempo_esgotado") and ref["json_valido"] == total
    dif = pct(ref["campos_certos"], ref["campos_total"]) - (pct(leve["campos_certos"], leve["campos_total"]) if leve else 0)
    if confiavel and dif >= DIFERENCA_GRANDE_PP:
        passos.append(f"Item 4: o 3B respondeu {ref['json_valido']}/{total} sem tempo esgotado e acertou {br(dif)} pontos percentuais a mais "
                      f"que o {LEVE} (diferença grande: {DIFERENCA_GRANDE_PP} ou mais): opção C.")
        return {"opcao": "C", "padrao": REFERENCIA, "opcional": LEVE, "passos": passos}
    passos.append(f"Item 4: o 3B {'não é confiável' if not confiavel else 'não é muito melhor'} nesta variante "
                  f"({ref['json_valido']}/{total} respostas válidas, {ref.get('tempo_esgotado', 0)} tempo(s) esgotado(s), {br(dif)} pontos a mais): opção D.")
    return {"opcao": "D", "padrao": LEVE, "opcional": REFERENCIA, "passos": passos}


def tabela(ev: dict) -> list[str]:
    L = ["| Modelo | Variante | Download | Campos certos | Respostas válidas | Tempo esgotado (300 s) | Erros graves | Latência média | p95 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for d in ev["modelos"].values():
        r, lat, n = d["resumo"], d["resumo"]["latencia_ms"], len(d["casos"])
        nao = n - r.get("medidos", n)
        L.append(f"| `{d['modelo']}` | {d['variante'].replace('_', ' ')} | {d.get('tamanho') or '—'} | "
                 f"{r['campos_certos']}/{r['campos_total']} ({br(pct(r['campos_certos'], r['campos_total']))}%) | {r['json_valido']}/{n} | "
                 f"{r.get('tempo_esgotado', 0)}{f' (+{nao} não medidos)' if nao else ''} | {len(r['erros_graves'])} | "
                 f"{br(lat['media'] / 1000) if lat['media'] is not None else '—'} s | {br(lat['p95'] / 1000) if lat['p95'] is not None else '—'} s |")
    return L


def por_campo(ev: dict, variante: str) -> list[str]:
    campos = sorted({k for d in ev["modelos"].values() for k in d["resumo"]["por_campo"]})
    L = ["| Modelo | " + " | ".join(campos) + " |", "|---|" + "---|" * len(campos)]
    for d in ev["modelos"].values():
        if d["variante"] == variante:
            L.append(f"| `{d['modelo']}` | " + " | ".join(d["resumo"]["por_campo"].get(c, "—") for c in campos) + " |")
    L += ["", *[f"- Erros graves de `{d['modelo']}`: " + ("; ".join(d["resumo"]["erros_graves"]) or "nenhum") + "."
                for d in ev["modelos"].values() if d["variante"] == variante]]
    return L


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    primeira, corrigida = carregar()
    d1 = decidir(primeira["modelos"], "num_predict_512")
    final = decidir(corrigida["modelos"], "corrigido") if corrigida else d1
    L = [
        "# Escolha do modelo da triagem do Gmail",
        "",
        "Gerado por `gerar_escolha_modelo.py` a partir das evidências "
        "[`triagem-modelos.json`](../sqlserver/evidence/parte3/triagem-modelos.json) (primeira medição) e "
        "[`triagem-modelos-corrigido.json`](../sqlserver/evidence/parte3/triagem-modelos-corrigido.json) (depois da correção); nenhum número "
        "foi digitado à mão. O critério foi escrito e versionado **antes** da primeira medição: "
        "[`escolha-modelo-criterio.md`](escolha-modelo-criterio.md).",
        "",
        f"**Escolha final: opção {final['opcao']}, `{final['padrao']}` por padrão"
        + (f", `{final['opcional']}` opcional (`instalar.ps1 -ModeloTriagem {final['opcional']}`).**" if final["opcional"] else ".**"),
        "",
        "## A decisão",
        "",
        "O pacote da entrega precisa baixar pouco. Hoje a triagem do Gmail (WF-08) usa o Qwen 2.5 3B (~1,9 GB) e a IA acadêmica usa o "
        "0,5B (~400 MB). Um modelo menor faria a triagem bem o bastante?",
        "",
        "## Riscos de um modelo menor",
        "",
        "- Errar o tipo de documento, o evento ou o provedor e mandar mais documentos para revisão humana.",
        "- Ler uma fatura de internet como \"outro\" (candidata a ser ignorada se as regras também não acharem evidência e não houver boleto).",
        "- Ler um documento que não é de internet como cobrança (iria para associação, com revisão humana).",
        "- Não terminar a resposta: o nó do WF-08 desiste em 300 s e manda o documento para Revisão, mas trava a fila nesse tempo.",
        "",
        "O que não muda com o modelo: valor e vencimento da linha digitável prevalecem sobre a IA, provedor que não aparece no documento "
        "é descartado, e falha ou resposta inválida vai para Revisão, nunca é ignorada.",
        "",
        "## Como foi medido",
        "",
        f"- Método: {primeira['metodo']}.",
        f"- {len(primeira['documentos'])} documentos fictícios, com o esperado tirado das definições do prompt:",
        *[f"  - {d['id']}: {d['descricao']}" for d in primeira["documentos"]],
        "- Campos pontuados quando o documento os tem: tipo, evento, provedor, empresa pagadora, valor e vencimento. Uma resposta "
        "inválida conta como 1 campo errado (`json`), então o percentual só compara bem modelos que responderam aos mesmos documentos.",
        "",
        "## 1ª medição: o pedido como hoje e com limite de 512 tokens",
        "",
        *tabela(primeira),
        "",
        *por_campo(primeira, "num_predict_512"),
        "",
        "Pelo critério, na variante com limite: " + " ".join(d1["passos"]),
        f"Resultado da 1ª aplicação: opção {d1['opcao']} (`{d1['padrao']}` por padrão). O 3B não era confiável: sem limite, esgotou 300 s em "
        "parte dos documentos; com o limite, teve respostas cortadas.",
        "",
        "## A causa e a correção",
        "",
        "Olhando a resposta crua de um documento que travou, o 3B preenchia os campos certos, mas **o campo `motivo` não acabava**: "
        "continuava a frase até 700 tokens e o JSON nunca fechava. A correção, no próprio JSON Schema do WF-08: `maxLength` em cada texto "
        "(`motivo` até 200 caracteres, `vencimento` 10, `competencia` 7...), o que obriga o modelo a fechar o campo, mais `num_predict = 400` "
        "como segunda proteção. Ela passou a valer em produção no WF-08 (`n8n/wf08/schema_classificacao.json` e `build_wf08.ps1`).",
        "",
    ]
    if corrigida:
        L += ["## 2ª medição: com a correção (variante proposta para a produção)", "", *tabela(corrigida), "",
              *por_campo(corrigida, "corrigido"), "",
              "## A escolha, pelo mesmo critério", "",
              "A variante proposta para a produção mudou depois da 1ª medição (era o limite de 512; passou a ser a corrigida). O critério é o "
              f"mesmo, aplicado à nova variante. O item 4 não definia \"diferença grande\"; a definição usada, escrita junto com a correção, "
              f"é: o 3B responde a todos os documentos, sem tempo esgotado, e acerta pelo menos {DIFERENCA_GRANDE_PP} pontos percentuais a mais "
              "que o modelo leve.", "",
              *[f"{i}. {p}" for i, p in enumerate(final["passos"], 1)], ""]
    L += [f"**Escolha final: opção {final['opcao']}, `{final['padrao']}` por padrão"
          + (f", `{final['opcional']}` opcional (`instalar.ps1 -ModeloTriagem {final['opcional']}`)**." if final["opcional"] else "**."),
          "",
          "O que isso significa no pacote: a triagem por IA só roda se o Gmail for conectado. Os dois modelos ainda erram a classificação de "
          "alguns documentos (os erros graves acima): esses vão para a revisão humana, e nada é pago nem ignorado por causa da IA. "
          "O sistema completo da empresa continua com o 3B, agora com a correção.", ""]
    SAIDA.write_text("\n".join(L), encoding="utf-8")
    print(f"ok: {SAIDA} · 1ª aplicação: {d1['opcao']} · final: {final['opcao']} ({final['padrao']})")


if __name__ == "__main__":
    main()
