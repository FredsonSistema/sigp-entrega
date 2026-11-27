"""Gera os PDFs da entrega final a partir das evidências (mesmos dados da página apresentacao.html, via dados.py):

  docs/entrega-academica/relatorio-limitacoes.pdf   relatório de limitações (1 a 2 páginas; o script confere)
  docs/entrega-academica/relatorio-final.pdf        relatório final (respostas à professora, mudanças desde a Entrega 2,
                                                    requisitos, resultados, histórico e contribuição individual)

Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/apresentacao/gerar_relatorios.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import dados  # noqa: E402

ENTREGA = DIR.parent
# Estado da fase de separação do repositório e do pacote de instalação (atualizar ao concluir e gerar de novo).
SEPARACAO_CONCLUIDA = True

NAVY, TEAL, INK, MUTED, PALE, MINT, RED, GOLD = (colors.HexColor(c) for c in
                                                 ("#15324B", "#178F8A", "#243746", "#5E7180", "#EAF2F7", "#E6F4F1", "#A83B3B", "#D69A2D"))
for nome, arq in (("SIGpSans", "arial.ttf"), ("SIGpSans-Bold", "arialbd.ttf")):
    caminho = Path(r"C:\Windows\Fonts") / arq
    if caminho.exists():
        pdfmetrics.registerFont(TTFont(nome, str(caminho)))
FONTE = "SIGpSans" if "SIGpSans" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
NEGRITO = "SIGpSans-Bold" if "SIGpSans-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
if FONTE == "SIGpSans":
    pdfmetrics.registerFontFamily("SIGpSans", normal="SIGpSans", bold="SIGpSans-Bold", italic="SIGpSans", boldItalic="SIGpSans-Bold")

E = {
    "titulo": ParagraphStyle("titulo", fontName=NEGRITO, fontSize=17, leading=21, textColor=NAVY, spaceAfter=3),
    "sub": ParagraphStyle("sub", fontName=FONTE, fontSize=9.5, leading=12.5, textColor=MUTED, spaceAfter=8),
    "h": ParagraphStyle("h", fontName=NEGRITO, fontSize=11.5, leading=14, textColor=TEAL, spaceBefore=8, spaceAfter=4),
    "p": ParagraphStyle("p", fontName=FONTE, fontSize=9.3, leading=12.4, textColor=INK, spaceAfter=4, alignment=TA_LEFT),
    "item": ParagraphStyle("item", fontName=FONTE, fontSize=9.1, leading=12, textColor=INK, leftIndent=10, bulletIndent=0, spaceAfter=2.2),
    "cel": ParagraphStyle("cel", fontName=FONTE, fontSize=8.2, leading=9.8, textColor=INK),
    "celb": ParagraphStyle("celb", fontName=NEGRITO, fontSize=8.2, leading=9.8, textColor=colors.white),
    "nota": ParagraphStyle("nota", fontName=FONTE, fontSize=7.8, leading=10, textColor=MUTED, spaceBefore=3),
    "cod": ParagraphStyle("cod", fontName="Courier", fontSize=7.8, leading=9.8, textColor=INK, backColor=PALE, borderPadding=3, spaceAfter=4),
}


def faixa(k: int, n: int) -> str:
    """Intervalo de Wilson (95%) em texto, ex.: "81% a 100%"."""
    inf, sup = dados.wilson(k, n)
    return f"{inf * 100:.0f}% a {sup * 100:.0f}%"


def br(v, casas=1):
    if v is None or v == "":
        return "—"
    return f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def P(t, e="p"):
    return Paragraph(t, E[e])


def itens(lista):
    return [Paragraph(t, E["item"], bulletText="•") for t in lista]


def tabela(cab, linhas, larguras, destaque=None):
    dados_t = [[P(c, "celb") for c in cab]] + [[P(str(c), "cel") for c in l] for l in linhas]
    t = Table(dados_t, colWidths=[w * mm for w in larguras], repeatRows=1)
    estilo = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9D6E0")),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 1.4),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4)]
    for linha in destaque or []:
        estilo.append(("BACKGROUND", (0, linha), (-1, linha), MINT))
    t.setStyle(TableStyle(estilo))
    return t


class Paginas:
    def __init__(self, titulo):
        self.titulo, self.total = titulo, 0

    def __call__(self, canv, doc):
        self.total = doc.page
        canv.saveState()
        canv.setFont(FONTE, 7.5)
        canv.setFillColor(MUTED)
        canv.drawString(18 * mm, 10 * mm, f"SIGp · {self.titulo}")
        canv.drawRightString(A4[0] - 18 * mm, 10 * mm, f"página {doc.page}")
        canv.restoreState()


def cabecalho(d, titulo, subtitulo):
    nomes = ", ".join(i["nome"] for i in d["projeto"]["integrantes"])
    return [P(titulo, "titulo"),
            P(f"{subtitulo}<br/>{' · '.join(d['projeto']['disciplinas'])} · {nomes}<br/>"
              f"Gerado em {date.today().strftime('%d/%m/%Y')} a partir das evidências do repositório da entrega "
              f"({d['projeto']['repositorio']}), com base fictícia e instalação em um comando.", "sub")]


def gerar(caminho, titulo, historia):
    pag = Paginas(titulo)
    doc = SimpleDocTemplate(str(caminho), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=13 * mm, bottomMargin=14 * mm,
                            title=f"SIGp — {titulo}", author="Grupo SIGp")
    doc.build(historia, onFirstPage=pag, onLaterPages=pag)
    return pag.total


# ------------------------------------------------------------------ relatório de limitações
def limitacoes(d):
    A, B, F, S, O, LA = d["ia_antes"], d["ia_depois"], d["finetuning"], d["seguranca"], d["otimizacao"], d["latencia"]
    vm = B["validacao_metricas"]
    escapou = ", ".join(vm["ataques_decididos_CONTRATADO"])
    I26, v2m = d.get("injecao_antes_26"), B.get("validacao_v2_metricas")
    fa = F["conjuntos"]["A"]
    lat = LA.get("fatura_nova_sem_carga") or LA.get("fatura_nova_com_carga")
    sob_carga = "fatura_nova_sem_carga" not in LA
    cpu = (lat.get("cpu") or {}).get("antes")
    cg = {(c["tipo"], c["modo"]): c for c in O["custo_gravacao"]}
    h = cabecalho(d, "Relatório de limitações", "Entrega final · o que não funciona, riscos que restaram e o que faríamos a seguir. "
                  "Cada número vem de um arquivo em <i>sqlserver/evidence/parte3/</i>; cada falha, correção e reteste está em "
                  "<i>historico-evolucao.md</i>")
    h += [P("1. O que não funciona (ou funciona só em parte)", "h")] + itens([
        (f"<b>A detecção de prompt injection só cobre as famílias que conhece.</b> A 1ª validação cega deu "
         f"{I26['validacao_metricas']['ataques_detectados']}/{I26['validacao_metricas']['ataques']}; a correção de 26/11 partiu dessas falhas, por família "
         f"(engenharia social, marcação falsa, homóglifos, aviso falso que manda pular a conferência). Na 2ª validação cega, congelada antes da "
         f"correção: {I26['validacao_v2_metricas']['ataques_detectados']}/{I26['validacao_v2_metricas']['ataques']} → "
         f"{v2m['ataques_detectados']}/{v2m['ataques']}. Escapou {', '.join(v2m['ataques_decididos_CONTRATADO']) or 'nenhum'} (cabeçalho falso de sistema, "
         f"família nova) e um controle legítimo foi para revisão por engano ({', '.join(v2m['controles_marcados_por_engano']) or 'nenhum'}). "
         if I26 and v2m else
         f"<b>A detecção de prompt injection generaliza pela metade.</b> Validação cega: {vm['ataques_detectados']}/{vm['ataques']} ({escapou}). ")
        + "O dano fica limitado porque a regra decide: um ataque não detectado só deixa sair CONTRATADO uma fatura cujo serviço e valor "
        "já batem com o contrato.",
        f"<b>O modelo local (Qwen 0,5B) não classifica sozinho:</b> acertou {B['metricas']['modelo_acertos']}/{B['metricas']['total']} casos, "
        "respondendo REVISAR em quase todos; por isso não tem autoridade.",
        f"<b>O fine-tuning não generaliza fora do treino.</b> O ajustado com RAG acertou {fa['ajustado_rag']['acertos']}/{fa['ajustado_rag']['n']} "
        f"nos casos finais (base com RAG: {fa['base_rag']['acertos']}/{fa['base_rag']['n']})"
        + (f" e {F['conjuntos']['C']['ajustado_rag']['acertos']}/{F['conjuntos']['C']['ajustado_rag']['n']} fora de escopo" if 'C' in F['conjuntos'] else "")
        + f", contra {B['metricas']['acertos']}/{B['metricas']['total']}"
        + (f" e {B['fora']['acertos']}/{B['fora']['total']}" if B.get('fora') else "")
        + " da regra. Ele aprendeu o formato curto da evidência do treino e lê \"não inclui IP adicional\" do contrato como divergência"
        + (f"; no {', '.join(fa['ajustado_rag'].get('falsas_ids') or [])}, aprovou uma fatura com instrução embutida" if fa['ajustado_rag'].get('falsas_ids') else "")
        + ".",
        (f"<b>A primeira análise depois de 30 min parado é lenta: {br(LA['partida_fria']['primeira_ms'] / 1000, 1)} s</b>, porque o Ollama "
         f"descarrega o modelo e precisa carregá-lo de novo; a seguinte leva {br(LA['partida_fria']['seguinte_ms'] / 1000, 1)} s. "
         if LA.get("partida_fria") else "")
        + (f"Com o modelo carregado, a fatura nova caiu de {br(lat['latencia']['media'] / 1000, 1)} s (prompt 3.0) para "
           f"{br(LA['prompt31_fatura_nova']['latencia']['media'] / 1000, 1)} s em média (p95 {br(LA['prompt31_fatura_nova']['latencia']['p95'] / 1000, 1)} s, prompt 3.1), "
           "na CPU de um notebook" if LA.get("prompt31_fatura_nova") else
           f"A fatura nova leva {br(lat['latencia']['media'] / 1000, 1)} s em média (p95 {br(lat['latencia']['p95'] / 1000, 1)} s) na CPU de um notebook")
        + (f", com {br(cpu, 0)}% da CPU ocupada por outros programas" if sob_carga and cpu else "") + ".",
        "<b>A trilha de gravações cobre só as notas.</b> Inserção, alteração e exclusão em <i>app.Notas</i> são registradas com o "
        "antes e o depois; pagamentos, conciliações e itens não têm gatilho. A auditoria nativa registra as gravações e as tentativas, "
        "não as leituras.",
        "<b>A API acadêmica recebe a fatura em JSON</b> (normalizada ou NF-e convertida). A leitura do PDF (OCR) e do XML fica no fluxo "
        "do SIGp no n8n, não no serviço avaliado.",
    ] + ([] if SEPARACAO_CONCLUIDA else [
        "<b>Separação do repositório e instalação em um comando:</b> em andamento na data deste relatório. Hoje o repositório tem o "
        "SIGp completo e a parte acadêmica fica em <i>docs/entrega-academica/</i>.",
    ]))
    h += [P("2. Riscos que restaram", "h")] + itens([
        "<b>O dono do banco e o <i>sa</i> passam por cima do RLS e do mascaramento</b> e podem parar de registrar (desligar o gatilho não é "
        "auditado). O que já está na trilha eles não alteram nem apagam: ela é ledger, conferida contra o digest guardado no Git.",
        "<b>Mascaramento não é criptografia.</b> Quem tem leitura pode tentar adivinhar a chave fiscal por filtro; por isso a IA e quem "
        "não precisa da linha não têm leitura na tabela. O TDE protege o arquivo e o backup, mas perder o certificado (guardado fora do banco) "
        "torna os backups irrecuperáveis.",
        "<b>A auditoria nativa guarda o texto do comando tentado</b>, que pode conter um valor digitado. Só o administrador do servidor lê o arquivo.",
        f"<b>Os gatilhos deixam a gravação mais lenta:</b> o do resumo diário leva uma nota de {br(float(cg[('uma_a_uma', 'sem')]['por_nota_us']) / 1000, 2)} "
        f"para {br(float(cg[('uma_a_uma', 'com')]['por_nota_us']) / 1000, 2)} ms; o custo somado com o gatilho de auditoria ainda não foi medido.",
        "<b>Falha fechada tem custo:</b> se o modelo demorar mais de 140 s (fila do Ollama), a análise volta 503 e precisa ser repetida.",
        "<b>Falso positivo do detector:</b> uma fatura legítima com frase parecida com ataque vai para revisão humana (erro do lado seguro).",
        "<b>A triagem do Gmail ainda erra a classificação de alguns documentos:</b> mesmo o 3B, com a correção da resposta sem fim, leu um "
        "aviso de atraso como \"outro\" e uma conta de energia como cobrança; o 0,5B (instalação leve) erra mais. Esses documentos vão "
        "para revisão humana: nada é pago nem ignorado por causa da IA.",
        f"<b>Evidência pequena e sintética:</b> 16 casos, {B['fora']['total'] if B.get('fora') else 0} fora de escopo, 26 ataques e 100.020 notas fictícias. Com 95% de confiança, 16/16 quer dizer "
        f"{faixa(B['metricas']['acertos'], 16)} de acerto, e os {v2m['ataques_detectados'] if v2m else vm['ataques_detectados']}/{v2m['ataques'] if v2m else vm['ataques']} da 2ª validação cega, {faixa(v2m['ataques_detectados'], v2m['ataques']) if v2m else faixa(vm['ataques_detectados'], vm['ataques'])}. Servem para achar falhas e comparar "
        "configurações, não para estimar a taxa de erro com faturas reais.",
    ])
    h += [P("3. O que o grupo faria a seguir", "h")] + itens([
        "Normalizar homóglifos (tabela de caracteres confundíveis do Unicode) e testar um classificador de instruções, avaliado em "
        "outro conjunto cego, nunca no usado para ajustar.",
        "Chamar o modelo só quando a regra pedir REVISAR e mantê-lo carregado no horário de uso: a decisão sai em milissegundos, "
        "e a espera de carregar o modelo some.",
        "Ampliar os documentos de teste da triagem (avisos de atraso, outras concessionárias) e medir de novo com o mesmo critério.",
        "Treinar o LoRA com o texto real dos contratos que o RAG entrega, com documentos fora de escopo e com exemplos que tragam "
        "instrução embutida, e medir de novo nos casos finais e fora de escopo.",
        "Levar a trilha de gravações a pagamentos, conciliações e itens; auditar as leituras da chave fiscal e a alteração de gatilhos.",
        "Avaliar com faturas reais anonimizadas e mais volume, e medir a latência num servidor sem outra carga.",
    ])  # a separação do repositório já aparece na seção 1 enquanto SEPARACAO_CONCLUIDA for False
    return h


# ------------------------------------------------------------------ relatório final
def apresentacao(d):
    A, B, F, S, O, L, H, LA = (d[k] for k in ("ia_antes", "ia_depois", "finetuning", "seguranca", "otimizacao", "evolucao_llm", "historico", "latencia"))
    nomes = [i["nome"].split()[0] for i in d["projeto"]["integrantes"]]
    n = lambda i: nomes[i] if i < len(nomes) else "—"  # noqa: E731
    q = {(t["cfg"], t["consulta"]): t for t in O["tempos"]}
    h = cabecalho(d, "Relatório final", "Entrega final · material da postagem. Página interativa com os mesmos dados: "
                  "<i>docs/entrega-academica/apresentacao.html</i> (abre sem internet)")
    h += [P("Respostas aos comentários da professora (devolutiva da Entrega 2)", "h"),
          P("Uma linha por comentário. Os números vêm das evidências; o detalhe está no arquivo da coluna Evidência.", "nota")]
    h.append(tabela(["Disciplina", "Comentário", "O que foi feito", "Evidência"],
                    [[r["disciplina"], r["comentario"], r["resposta"], r["evidencia"]] for r in d["respostas_professora"]], [19, 36, 77, 42]))
    M = d["mudancas"]
    h += [PageBreak(), P("1. Mudanças desde a Entrega 2", "h"),
          P("<b>Interface: da web para uma janela do Windows.</b> Na Entrega 2 o SIGp abria numa aba do navegador. Agora o atalho "
            "<b>SIGp</b> da área de trabalho abre o sistema numa janela própria do Windows, sem barra de endereço e sem abas, com título e "
            "ícone na barra de tarefas (Microsoft Edge em modo aplicativo, com perfil separado; <i>abrir-sigp.ps1</i>). Se o computador foi "
            "reiniciado, o atalho liga o Docker e os containers. As telas são as mesmas e tudo continua local. Teste e reteste: H-48."),
          P("<b>O que melhorou</b> (antes = 1ª medição desta etapa, no sistema como estava na Entrega 2; depois = medição final):")]
    h.append(tabela(["Tema", "Antes", "Depois"], [[x["tema"], x["antes"], x["depois"]] for x in M["melhorado"] if x["tema"] != "Interface"], [48, 52, 74]))
    h += [P(f"<b>O que foi corrigido:</b> {len(M['corrigido'])} testes reprovaram na primeira execução e foram corrigidos e retestados; "
            "a lista está na seção 6 e, com o texto completo, em <i>historico-evolucao.md</i> e <i>MUDANCAS-DESDE-ENTREGA-2.md</i>."),
          P("<b>O que permaneceu inalterado:</b>")]
    h.append(tabela(["O quê", "Como está"], [[x["item"], x["como"]] for x in M["inalterado"]], [42, 132]))
    h += [P("2. Onde está cada requisito", "h")]
    h.append(tabela(["Disciplina", "Requisito", "Documento", "Resultado"],
                    [[r["disciplina"], r["requisito"], r["documento"], r["resultado"]] for r in d["requisitos"]], [19, 62, 48, 45]))
    nomes = [i["nome"].split()[0] for i in d["projeto"]["integrantes"]]  # noqa: F841
    h += [PageBreak(), P("3. Antes e depois", "h")]
    esc_a = sum(1 for x in S["escalonamento"] if x["fase"] == "antes" and x["obtido"] == "PERMITIDO")
    tr_a = sum(1 for x in S["trilha"]["antes"] if x["veredito"] == "FALHA")
    tr_d = sum(1 for x in S["trilha"]["depois"] if x["veredito"] == "OK")
    h.append(tabela(["Tema", "Antes", "Depois", "Evidência"], [
        ["Decisão certa nos 16 casos", f"{A['metricas']['acertos']}/16 (F1 {br(A['metricas']['f1_macro'], 3)})",
         f"{B['metricas']['acertos']}/16 (F1 {br(B['metricas']['f1_macro'], 3)}; 95%: {faixa(B['metricas']['acertos'], 16)})", "ia-avaliacao-antes/final.json"],
        *([["Casos fora de escopo (12)", "não medidos", f"{B['fora']['acertos']}/{B['fora']['total']} (1 falsa aprovação achada e corrigida)", "casos-fora-escopo.json"]] if B.get("fora") else []),
        *([["Busca do RAG (paráfrases, fonte certa no top 5)", f"lexical {d['rag']['metodos']['lexical']['parafrases']['acertos']}/{d['rag']['metodos']['lexical']['parafrases']['total']}",
            f"embedding {d['rag']['metodos'][d['rag']['escolha']]['parafrases']['acertos']}/{d['rag']['metodos'][d['rag']['escolha']]['parafrases']['total']}", "rag-embeddings.json"]] if d.get("rag") and d["rag"]["escolha"] else []),
        ["Falsas aprovações", ", ".join(A["metricas"]["falsas_aprovacoes"]) or "0", ", ".join(B["metricas"]["falsas_aprovacoes"]) or "0", "ia-avaliacao-*.json"],
        ["Injeção detectada (bateria)", f"{A['injecao_metricas']['ataques_detectados']}/{A['injecao_metricas']['ataques']}", f"{B['injecao_metricas']['ataques_detectados']}/{B['injecao_metricas']['ataques']}", "injecao-casos.json"],
        *([["Injeção: 1ª validação cega (a correção de 26/11 partiu dela)", f"{d['injecao_antes_26']['validacao_metricas']['ataques_detectados']}/{d['injecao_antes_26']['validacao_metricas']['ataques']}",
             f"{B['validacao_metricas']['ataques_detectados']}/{B['validacao_metricas']['ataques']} (otimista)", "injecao-validacao.json"],
           ["Injeção: 2ª validação cega (congelada antes da correção)", f"{d['injecao_antes_26']['validacao_v2_metricas']['ataques_detectados']}/{d['injecao_antes_26']['validacao_v2_metricas']['ataques']}",
            f"{B['validacao_v2_metricas']['ataques_detectados']}/{B['validacao_v2_metricas']['ataques']} (95%: {faixa(B['validacao_v2_metricas']['ataques_detectados'], B['validacao_v2_metricas']['ataques'])})", "injecao-validacao-v2.json"]]
          if d.get("injecao_antes_26") and B.get("validacao_v2_metricas") else []),
        ["Análise de fatura nova (média)", f"{br(LA['fatura_nova_com_carga']['latencia']['media'] / 1000, 1)} s (prompt 3.0)" if LA.get('fatura_nova_com_carga') else "—",
         f"{br(LA['prompt31_fatura_nova']['latencia']['media'] / 1000, 1)} s (prompt 3.1)" if LA.get('prompt31_fatura_nova') else "—", "latencia-custo-*.json"],
        ["Escalonamento de privilégio", f"{esc_a} ataques passaram", "todos barrados (33504)", "escalonamento.txt"],
        ["Trilha de auditoria", f"{tr_a} falhas", f"{tr_d}/{len(S['trilha']['depois'])} OK", "auditoria/trilha-*.txt"],
        *([["Trilha à prova de adulteração", f"sa reescreve {S['ledger']['antes'].get('UPDATE', '?')} e apaga {S['ledger']['antes'].get('DELETE', '?')} eventos",
            f"ledger: ninguém altera nem apaga; verificada ({S['ledger']['resultado']})", "ledger-*.json/txt"]] if S.get("ledger") else []),
        ["Consulta 1 (mediana)", f"{br(q[('A', 1)]['mediana'])} ms · {br(q[('A', 1)]['leituras'], 0)} leituras", f"{br(q[('D', 1)]['mediana'])} ms · {br(q[('D', 1)]['leituras'], 0)} leituras", "otimizacao/"],
        ["Consulta 2 (mediana)", f"{br(q[('A', 2)]['mediana'])} ms · {br(q[('A', 2)]['leituras'], 0)} leituras", f"{br(q[('C', 2)]['mediana'])} ms · {br(q[('C', 2)]['leituras'], 0)} leituras", "otimizacao/"],
        ["Segredos nos fluxos do n8n", "1 modelo com chave literal", f"{S['segredos']['resultado']} (0 falhas)", "segredos-n8n.json"],
    ], [52, 38, 38, 46]))

    sv = B["servico"]
    h += [PageBreak(), P("4. Inteligência artificial", "h"),
          P(f"<b>Sistema avaliado = sistema entregue:</b> {sv['model']}, prompt v{sv['prompt_version']}, busca "
            f"{('por embedding (' + sv['embed_model'] + ')') if sv.get('embed_model') else 'lexical'}, escopo {sv['database_scope']}. "
            "O prompt v4.2 é o da triagem do Gmail, outro fluxo. <i>tests/test_pacote_mesma_ia.py</i> compara o pacote com esta evidência."),
          P("<b>Os 16 casos</b> (esperado tirado das regras e do corpus):")]
    ba = {c["id"]: c for c in A["casos"]}
    h.append(tabela(["Caso", "Tipo", "Esperado", "Antes", "Final", "Modelo"],
                    [[c["id"], c["categoria"], c["esperado"], (f"HTTP {ba[c['id']]['http']}" if ba[c["id"]]["http"] != 200 else ba[c["id"]]["obtido"]),
                      c["obtido"], c["modelo"]] for c in B["casos"]], [17, 22, 27, 27, 27, 27]))
    if B.get("fora"):
        h += [Spacer(1, 4), P("<b>Os 12 casos fora de escopo</b> (esperado REVISAR em todos, escrito antes de rodar):")]
        h.append(tabela(["Caso", "Tipo", "Descrição", "Final", "Modelo"],
                        [[c["id"], c["categoria"], c["descricao"], c["obtido"], c["modelo"]] for c in B["fora"]["casos"]], [15, 30, 77, 26, 26]))
    h += [Spacer(1, 4), P("<b>Fine-tuning fora do treino</b> (mesmo modelo; o base é o ajustado com o adaptador desligado; RAG = documentos que o "
                          "sistema entregue recuperou):")]
    fa = F["conjuntos"]["A"]
    fc = F["conjuntos"].get("C")
    h.append(tabela(["Configuração", "Casos finais", "Fora de escopo", "Falsas aprov.", "Latência média", "1.000 usos (CPU · energia)"],
                    [[v["nome"], f"{v['acertos']}/{v['n']}", (f"{fc[k]['acertos']}/{fc[k]['n']}" if fc else "—"),
                      f"{v['falsas']}" + (f" + {fc[k]['falsas']}" if fc else ""), f"{br(v['latencia_media_ms'] / 1000, 2)} s",
                      f"{br(v['custo']['tempo_cpu_min'])} min · R$ {br(v['custo']['reais_15w'], 3)} a {br(v['custo']['reais_55w'], 3)}"]
                     for k, v in ((k, fa[k]) for k in ("base", "base_rag", "ajustado", "ajustado_rag"))], [38, 20, 22, 20, 22, 52]))
    fb = F["conjuntos"]["B"]
    h += [P(f"No teste do próprio treino, o ajuste funciona ({fb['base_rag']['acertos']}/20 → {fb['ajustado_rag']['acertos']}/20 com evidência), "
            "reproduzindo a entrega 2. Fora do treino não compensou: aprendeu o formato do treino, não a tarefa. "
            + (f"Fora de escopo, o ajustado sem RAG acerta {fc['ajustado']['acertos']}/{fc['ajustado']['n']} porque responde REVISAR quando não tem "
               "evidência, não por reconhecer o escopo. " if fc else "")
            + "Detalhe: <i>ia/finetuning/comparacao-final.md</i>.", "nota")]
    lat = LA.get("fatura_nova_sem_carga") or LA.get("fatura_nova_com_carga")
    cache = LA.get("faturas_ja_vistas_cache")
    novo = LA.get("prompt31_fatura_nova") or lat
    h += [P(f"<b>Latência do prompt {'3.1' if LA.get('prompt31_fatura_nova') else '3.0'} (medida antes do embedding):</b> fatura nova {br(novo['latencia']['media'] / 1000, 1)} s em média "
            f"(p95 {br(novo['latencia']['p95'] / 1000, 1)} s); 1.000 usos = {br(novo['custo']['tempo_cpu_min'], 0)} min de CPU, "
            f"R$ {br(novo['custo']['reais_15w'], 3)} a {br(novo['custo']['reais_55w'], 3)} de energia (sem cobrança por token). "
            + (f"No prompt 3.0 eram {br(lat['latencia']['media'] / 1000, 1)} s e {br(lat['custo']['tempo_cpu_min'], 0)} min: dois terços do prompt eram "
               "20 linhas de contexto que a regra não usa. " if LA.get("prompt31_fatura_nova") else "")
            + (f"Modelo descarregado (30 min parado): {br(LA['partida_fria']['primeira_ms'] / 1000, 1)} s na primeira análise." if LA.get("partida_fria") else ""))]
    TM = d.get("triagem_modelos")
    if TM:
        lin = {(x["modelo"], x["variante"]): x for x in TM["linhas"]}
        def t(m, v="num_predict_512"):
            x = lin.get((m, v))
            return f"{x['validas']} respostas válidas, {x['graves']} erro(s) grave(s), {br(x['media_s'], 1)} s" if x and x["media_s"] is not None else "—"
        h += [P(f"<b>Modelo do pacote da entrega (medido antes de escolher, critério versionado antes):</b> na 1ª medição, o 3B não terminava a "
                "resposta em parte dos documentos (o campo motivo não acabava) e a escolha seria o 0,5B. Com maxLength no JSON Schema e limite de "
                f"tokens, a 2ª medição deu ao 3B {t('qwen2.5:3b', 'corrigido')} e ao 0,5B {t('qwen2.5:0.5b', 'corrigido')}. Pelo mesmo critério: "
                f"{TM['padrao']} por padrão e {TM['opcional']} opcional. A correção passou a valer no WF-08 da produção. Ver <i>ia/escolha-modelo-triagem.md</i>.", "nota")]
    h += [P("<b>Prompts</b>: " + "; ".join(f"{p['versao']} ({p['estado']})" for p in L["prompts"]) + ".", "nota")]

    h += [P("5. Segurança e integração", "h")]
    h.append(tabela(["Teste", "Resultado"], [
        ["Escalonamento de privilégio (8 ataques + controle)", "Falha reproduzida com só o FILTER; com os predicados BLOCK, todos barrados e o controle permitido"],
        ["Trilha de auditoria (12 verificações)", f"Antes: {tr_a} falhas (nada registrado; operador forjava evento). Depois: {tr_d}/{len(S['trilha']['depois'])}"],
        *([["Trilha à prova de adulteração (ledger)", f"Antes: o sa reescreveu {S['ledger']['antes'].get('UPDATE', '?')} e apagou {S['ledger']['antes'].get('DELETE', '?')} eventos sem erro. Depois: ninguém altera nem apaga (37359); ledger verificada contra o digest no Git: {S['ledger']['resultado']}"]] if S.get("ledger") else []),
        *([["Criptografia em repouso (TDE)", f"Backup sem compressão: a chave fiscal aparecia {S['tde']['chave_fiscal_em_texto_no_backup_antes']} vezes em texto puro; depois do TDE, {S['tde']['chave_fiscal_em_texto_no_backup_depois']}. Certificado guardado fora do banco: {S['tde']['resultado']}"]] if S.get("tde") else []),
        ["IA por perfil (A, B e D)", f"{S['ia_perfis']['resultado']}: cada IA só o próprio local; injeção sem vazamento; a IA não falsifica a trilha"],
        ["Matriz de permissões", f"Medida como cada usuário; {S['matriz']['denys']} DENY explícitos, cada um com motivo e teste"],
        ["Prova do DENY", "Com a API no papel db_datawriter, apagar nota continua negado (229); controle sem DENY permitido"],
        ["Mascaramento + RLS", "API vê a chave fiscal mascarada; fiscal vê a real só no seu local; a view da IA não tem a chave"],
        ["Segredos no n8n", f"{S['segredos']['resultado']}: {S['segredos']['segredos_procurados']} segredos procurados em {S['segredos']['arquivos_do_repositorio']} arquivos e {S['segredos']['workflows_ao_vivo']} workflows ao vivo"],
    ], [60, 114]))

    h += [P("6. Histórico: o que reprovou, a correção e o reteste", "h")]
    h.append(tabela(["#", "Área", "1ª execução", "Reteste"], [[x["id"], x["area"], x["primeira"], x["reteste"]] for x in H], [12, 34, 72, 56]))

    h += [KeepTogether([P("7. Como repetir cada teste (na raiz do projeto, com o ambiente acadêmico no ar)", "h"),
          P("pwsh -File docs/entrega-academica/sqlserver/setup-academic.ps1          # instala e sobe tudo<br/>"
            ".venv-1\\Scripts\\python.exe docs/entrega-academica/ia/avaliar_ia.py final        # 16 casos, 12 fora de escopo e injeção<br/>"
            "(no contêiner da IA) python /tmp/ia/medir_rag_embeddings.py medir   # RAG: lexical × embeddings<br/>"
            ".venv-1\\Scripts\\python.exe docs/entrega-academica/sqlserver/testar_ia_perfis.py  # IA por perfil<br/>"
            "sqlcmd ... -I -f 65001 -i docs/entrega-academica/sqlserver/08_ataque_escalonamento.sql<br/>"
            "sqlcmd ... -I -f 65001 -i docs/entrega-academica/sqlserver/14_auditoria_testes.sql<br/>"
            "pwsh -File docs/entrega-academica/sqlserver/benchmark-final.ps1             # consultas lentas<br/>"
            ".venv-1\\Scripts\\python.exe docs/entrega-academica/ia/verificar_segredos_n8n.py --ao-vivo<br/>"
            ".venv-1\\Scripts\\python.exe docs/entrega-academica/apresentacao/gerar_apresentacao.py", "cod"),
          P("A senha do sqlcmd vai só pela variável SQLCMDPASSWORD, lida do .env.academic; nenhum comando leva senha.", "nota")])]

    h += [P("8. Contribuição individual", "h"),
          P("Divisão final do trabalho (3 a 5 linhas por integrante, sobre o projeto inteiro). Matrículas em <i>identificacao.json</i>.", "nota")]
    for i in d["projeto"]["integrantes"]:
        h += [P(f"<b>{i['nome']}.</b> {i['contribuicao']}")]
    return h


def main() -> None:
    d = dados.carregar()
    lim = ENTREGA / "relatorio-limitacoes.pdf"
    paginas = gerar(lim, "Relatório de limitações", limitacoes(d))
    print(f"ok: {lim} ({paginas} página(s))")
    if paginas > 2:
        sys.exit("O relatório de limitações passou de 2 páginas; encurte o texto.")
    fin = ENTREGA / "relatorio-final.pdf"
    faltam = [r["documento"] for r in d["requisitos"] if not r["existe"] and r["documento"] != "relatorio-final.pdf"]
    if faltam:
        sys.exit(f"Documento de requisito ausente: {faltam}")
    print(f"ok: {fin} ({gerar(fin, 'Relatório final', apresentacao(d))} página(s))")


if __name__ == "__main__":
    main()
