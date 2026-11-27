"""Gera as versões HTML simples (um arquivo cada, sem JavaScript, sem internet, prontas para imprimir) para envio individual:

  docs/entrega-academica/relatorio-final.html        o mesmo conteúdo do relatorio-final.pdf, seguido do relatório de limitações
  docs/entrega-academica/apresentacao-sistema.html   apresentação do sistema, com foco nas mudanças desde a Entrega 2

O relatório é convertido do mesmo conteúdo que gera os PDFs (gerar_relatorios.py), para o HTML e o PDF não divergirem.
Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/apresentacao/gerar_html.py
"""
from __future__ import annotations

import html
import sys
from datetime import date
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import dados  # noqa: E402
import gerar_relatorios as gr  # noqa: E402
from reportlab.platypus import KeepTogether, Paragraph, Table  # noqa: E402

ENTREGA = DIR.parent
CSS = """
body{font-family:Segoe UI,Arial,sans-serif;color:#243746;max-width:1000px;margin:32px auto;padding:0 20px;line-height:1.45}
h1{color:#15324B;margin-bottom:4px}h2{color:#178F8A;border-bottom:2px solid #EAF2F7;padding-bottom:4px;margin-top:30px}
.sub{color:#5E7180;font-size:14px}.nota{color:#5E7180;font-size:13px}
table{border-collapse:collapse;width:100%;margin:10px 0 16px;font-size:13.5px}
th{background:#15324B;color:#fff;text-align:left;padding:6px 8px}td{border:1px solid #C9D6E0;padding:5px 8px;vertical-align:top}
tr:nth-child(even) td{background:#F5F9FB}code,.cod{font-family:Consolas,monospace;font-size:12.5px;background:#EAF2F7;padding:1px 4px}
.cod{display:block;padding:8px;white-space:normal}.destaque{background:#E6F4F1;border-left:4px solid #178F8A;padding:10px 14px;margin:14px 0}
.grade{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:12px 0}
.kpi{border:1px solid #C9D6E0;border-radius:8px;padding:10px 12px}.kpi b{display:block;font-size:22px;color:#178F8A}.kpi span{font-size:13px;color:#5E7180}
footer{margin-top:40px;color:#5E7180;font-size:12px;border-top:1px solid #C9D6E0;padding-top:8px}
@media print{body{margin:0;max-width:none}h2{break-after:avoid}table{break-inside:auto}tr{break-inside:avoid}}
"""


def pagina(titulo: str, corpo: list[str]) -> str:
    return ("<!doctype html>\n<html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{html.escape(titulo)}</title>"
            f"<style>{CSS}</style></head><body>\n" + "\n".join(corpo) +
            f"\n<footer>SIGp · {html.escape(titulo)} · gerado em {date.today().strftime('%d/%m/%Y')} a partir das evidências do repositório "
            "da entrega; nenhum número digitado à mão.</footer>\n</body></html>\n")


def converter(historia) -> list[str]:
    """Story do ReportLab (Paragraph, Table, KeepTogether) → HTML, com a mesma marcação (<b>, <i>, <br/>)."""
    out, lista = [], []

    def fecha_lista():
        if lista:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in lista) + "</ul>")
            lista.clear()

    for f in historia:
        if isinstance(f, KeepTogether):
            fecha_lista()
            out += converter(f._content)
        elif isinstance(f, Paragraph):
            estilo, texto = f.style.name, f.text
            if estilo == "item":
                lista.append(texto)
                continue
            fecha_lista()
            tag = {"titulo": "h1", "h": "h2"}.get(estilo)
            if tag:
                out.append(f"<{tag}>{texto}</{tag}>")
            else:
                classe = {"sub": "sub", "nota": "nota", "cod": "cod"}.get(estilo)
                out.append(f"<p class=\"{classe}\">{texto}</p>" if classe else f"<p>{texto}</p>")
        elif isinstance(f, Table):
            fecha_lista()
            linhas = f._cellvalues
            cab = "".join(f"<th>{c.text if isinstance(c, Paragraph) else html.escape(str(c))}</th>" for c in linhas[0])
            corpo = "".join("<tr>" + "".join(f"<td>{c.text if isinstance(c, Paragraph) else html.escape(str(c))}</td>" for c in l) + "</tr>"
                            for l in linhas[1:])
            out.append(f"<table><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table>")
    fecha_lista()
    return out


def e(t) -> str:
    return html.escape(str(t))


def apresentacao_sistema(d) -> list[str]:
    M, B, R, O = d["mudancas"], d["ia_depois"], d.get("rag"), d["otimizacao"]
    q = {(t["cfg"], t["consulta"]): t for t in O["tempos"]}
    v2, I26 = B.get("validacao_v2_metricas"), d.get("injecao_antes_26")
    nomes = ", ".join(i["nome"] for i in d["projeto"]["integrantes"])
    c = [f"<h1>SIGp: apresentação do sistema</h1>",
         f"<p class=\"sub\">{e(' · '.join(d['projeto']['disciplinas']))}<br>{e(nomes)}<br>Repositório da entrega: "
         f"<a href=\"{e(d['projeto']['repositorio'])}\">{e(d['projeto']['repositorio'])}</a></p>",
         "<h2>O sistema em um parágrafo</h2>",
         "<p>Um grupo de empresas de transporte paga as contas de internet de dezenas de agências, rodoviárias e garagens. As faturas chegam "
         "por e-mail, em PDF e XML. O SIGp busca as faturas no Gmail (n8n), lê o documento, associa ao local e ao provedor, confere com o "
         "contrato e registra tudo no SQL Server, com permissão por local, dados sensíveis mascarados e criptografados e trilha de auditoria "
         "que ninguém altera. Uma IA local (Ollama, sem serviço externo) busca o contrato certo (RAG) e sugere; <b>quem decide é a regra sobre "
         "a evidência</b>, e nada é pago automaticamente.</p>",
         "<p class=\"cod\">Gmail → n8n → leitura do PDF/XML → SIGp → SQL Server (RLS, mascaramento, TDE, ledger) → RAG por embedding → "
         "Qwen local sugere → regra decide → trilha de auditoria</p>",
         "<h2>Da web para uma janela do Windows</h2>",
         "<div class=\"destaque\">Na Entrega 2 o SIGp abria numa aba do navegador. Agora o atalho <b>SIGp</b> da área de trabalho abre o sistema "
         "numa <b>janela própria do Windows</b>: sem barra de endereço e sem abas, com título e ícone na barra de tarefas (Microsoft Edge em modo "
         "aplicativo, com perfil separado; <code>abrir-sigp.ps1</code>). Se o computador foi reiniciado, o atalho liga o Docker e os containers e "
         "espera a tela responder. As telas são as mesmas e tudo continua local.</div>",
         "<h2>Os números que mudaram</h2>", "<div class=\"grade\">"]
    kpis = [("Decisão da IA nos 16 casos", f"{d['ia_antes']['metricas']['acertos']}/16 → {B['metricas']['acertos']}/16"),
            ("Casos fora de escopo (novos)", f"{B['fora']['acertos']}/{B['fora']['total']}" if B.get("fora") else "—")]
    if R and R["escolha"]:
        kpis.append(("RAG: fonte certa nas paráfrases", f"{R['metodos']['lexical']['parafrases']['acertos']}/14 → "
                     f"{R['metodos'][R['escolha']]['parafrases']['acertos']}/14"))
    if v2 and I26:
        kpis.append(("Injeção: 2ª validação cega", f"{I26['validacao_v2_metricas']['ataques_detectados']}/12 → {v2['ataques_detectados']}/12"))
    kpis += [("Consulta 1 (mediana)", f"{gr.br(q[('A', 1)]['mediana'])} → {gr.br(q[('D', 1)]['mediana'])} ms"),
             ("Consulta 2 (mediana)", f"{gr.br(q[('A', 2)]['mediana'])} → {gr.br(q[('C', 2)]['mediana'])} ms")]
    c += [f"<div class=\"kpi\"><span>{e(r)}</span><b>{e(v)}</b></div>" for r, v in kpis] + ["</div>"]
    c += ["<h2>O que melhorou</h2>",
          "<p class=\"nota\">Antes = 1ª medição desta etapa, no sistema como estava na Entrega 2; depois = medição final, no sistema entregue.</p>",
          "<table><thead><tr><th>Tema</th><th>Antes</th><th>Depois</th><th>Onde conferir</th></tr></thead><tbody>"
          + "".join(f"<tr><td>{e(x['tema'])}</td><td>{e(x['antes'])}</td><td>{e(x['depois'])}</td><td><code>{e(x['evidencia'])}</code></td></tr>"
                    for x in M["melhorado"]) + "</tbody></table>"]
    c += ["<h2>Respostas aos comentários da professora</h2>",
          "<table><thead><tr><th></th><th>Comentário</th><th>O que foi feito</th></tr></thead><tbody>"
          + "".join(f"<tr><td>{e(r['disciplina'])}</td><td>{e(r['comentario'])}</td><td>{e(r['resposta'])}</td></tr>" for r in d["respostas_professora"])
          + "</tbody></table>"]
    c += [f"<h2>O que foi corrigido ({len(M['corrigido'])} testes que reprovaram e foram retestados)</h2>",
          "<table><thead><tr><th>#</th><th>Área</th><th>O que foi testado</th><th>Reteste</th></tr></thead><tbody>"
          + "".join(f"<tr><td>{e(x['id'])}</td><td>{e(x['area'])}</td><td>{e(x['teste'])}</td><td>{e(x['reteste'])}</td></tr>" for x in M["corrigido"])
          + "</tbody></table>"]
    c += ["<h2>O que permaneceu inalterado</h2>",
          "<table><thead><tr><th>O quê</th><th>Como está</th></tr></thead><tbody>"
          + "".join(f"<tr><td>{e(x['item'])}</td><td>{e(x['como'])}</td></tr>" for x in M["inalterado"]) + "</tbody></table>"]
    c += ["<h2>Onde está cada requisito</h2>",
          "<table><thead><tr><th></th><th>Requisito</th><th>Documento</th><th>Resultado</th></tr></thead><tbody>"
          + "".join(f"<tr><td>{e(r['disciplina'])}</td><td>{e(r['requisito'])}</td><td><code>{e(r['documento'])}</code></td><td>{e(r['resultado'])}</td></tr>"
                    for r in d["requisitos"]) + "</tbody></table>",
          "<p class=\"nota\">Os caminhos são relativos a <code>docs/entrega-academica/</code> no repositório da entrega. Relatório completo: "
          "<code>relatorio-final.html</code> (ou o PDF); resultados interativos: <code>apresentacao.html</code>.</p>"]
    return c


def main() -> None:
    d = dados.carregar()
    rel = ENTREGA / "relatorio-final.html"
    corpo = converter(gr.apresentacao(d)) + ["<h2 style=\"margin-top:48px\">Anexo: relatório de limitações</h2>"] + \
        [x.replace("<h1>", "<h2>").replace("</h1>", "</h2>") for x in converter(gr.limitacoes(d))]
    rel.write_text(pagina("Relatório final", corpo), encoding="utf-8")
    print(f"ok: {rel}")
    apr = ENTREGA / "apresentacao-sistema.html"
    apr.write_text(pagina("Apresentação do sistema", apresentacao_sistema(d)), encoding="utf-8")
    print(f"ok: {apr}")


if __name__ == "__main__":
    main()
