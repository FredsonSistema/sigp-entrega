"""Gera docs/entrega-academica/roteiro-apresentacao.md: o roteiro de 10 minutos da apresentação final, com quem fala,
o que mostrar, o que falar, a lista de conferência, o plano B e as perguntas prováveis do professor.
Os números vêm de dados.carregar() (as mesmas evidências da página e dos PDFs); nenhum número é digitado aqui.
Uso, na raiz do projeto:  python docs/entrega-academica/apresentacao/gerar_roteiro.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados  # noqa: E402

SAIDA = dados.ENTREGA / "roteiro-apresentacao.md"


def br(v, casas=1) -> str:
    return f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def faixa(k: int, n: int) -> str:
    inf, sup = dados.wilson(k, n)
    return f"{inf * 100:.0f}% a {sup * 100:.0f}%"


def main() -> None:
    d = dados.carregar()
    nomes = [i["nome"] for i in d["projeto"]["integrantes"]]
    curto = [n.split()[0] for n in nomes]
    while len(curto) < 4:
        curto.append("(integrante)")
    A, B, F, S, O, LA, H = (d[k] for k in ("ia_antes", "ia_depois", "finetuning", "seguranca", "otimizacao", "latencia", "historico"))
    am, bm, bi, bv = A["metricas"], B["metricas"], B["injecao_metricas"], B["validacao_metricas"]
    fa, fb = F["conjuntos"]["A"], F["conjuntos"]["B"]
    q = {(t["cfg"], t["consulta"]): t for t in O["tempos"]}
    cg = {(c["tipo"], c["modo"]): c for c in O["custo_gravacao"]}
    v30, v31, fria = LA.get("fatura_nova_com_carga"), LA.get("prompt31_fatura_nova"), LA.get("partida_fria")
    esc_a = sum(1 for x in S["escalonamento"] if x["fase"] == "antes" and x["obtido"] == "PERMITIDO")
    esc_d = [x for x in S["escalonamento"] if x["fase"] == "depois"]
    tr_a = sum(1 for x in S["trilha"]["antes"] if x["veredito"] == "FALHA")
    tr_d = sum(1 for x in S["trilha"]["depois"] if x["veredito"] == "OK")
    mz = S["matriz"]
    prova_ok = sum(1 for x in mz["prova_deny"] if str(x.get("veredito", "")).upper().startswith("OK"))
    tipos = collections.Counter(h["tipo"] for h in H)
    seg = S["segredos"]
    lat_txt = (f"{br(v30['latencia']['media'] / 1000)} s → {br(v31['latencia']['media'] / 1000)} s (p95 {br(v31['latencia']['p95'] / 1000)} s)"
               if v30 and v31 else "ver Latência na página")

    L = [
        "# Roteiro da apresentação final (10 minutos)",
        "",
        "Gerado por `apresentacao/gerar_roteiro.py` a partir das evidências (os mesmos números da `apresentacao.html` e dos PDFs). "
        "Se uma evidência mudar, gere de novo: `python docs/entrega-academica/apresentacao/gerar_roteiro.py`.",
        "",
        "Material usado na apresentação:",
        "- **`apresentacao.html`** (abre no navegador, sem internet): a página dos resultados. As setas do teclado passam de uma seção para a outra.",
        "- **`demo-final.ps1`**: a demonstração ao vivo, passo a passo. Cada passo mostra o que falar e espera Enter.",
        "- **`relatorio-apresentacao.pdf`** e **`relatorio-limitacoes.pdf`**: para entregar e para consulta.",
        "- **Plano B:** `sqlserver/evidence/parte3/demo-final-saida.txt` (a saída completa de uma demonstração já rodada).",
        "",
        "## Divisão e tempos",
        "",
        "Estrutura pedida: problema 1 min, arquitetura 2 min, demonstração 4 min, resultados 2 min e limitações 1 min. "
        "A divisão segue a área de cada um; ajustem se preferirem.",
        "",
        "| Tempo | Bloco | Quem | Mostrar |",
        "|---|---|---|---|",
        f"| 0:00–1:00 | O problema | {curto[0]} | `apresentacao.html` · Visão geral |",
        f"| 1:00–3:00 | A arquitetura | {curto[0]} | Visão geral (fluxo) |",
        f"| 3:00–4:30 | Demonstração: IA (passos 1 a 3) | {curto[1]} | terminal: `demo-final.ps1` |",
        f"| 4:30–5:00 | Demonstração: trilha da IA (passo 4) | {curto[0]} | terminal |",
        f"| 5:00–5:45 | Demonstração: escalonamento e trilha à prova de adulteração (passos 5 e 5b) | {curto[2]} | terminal |",
        f"| 5:45–7:00 | Demonstração: IA por perfil e consultas (passos 6 e 7) | {curto[3]} | terminal |",
        f"| 7:00–7:45 | Resultados: IA | {curto[1]} | Casos de teste · Prompt injection · Fine-tuning |",
        f"| 7:45–8:15 | Resultados: segurança | {curto[2]} | Segurança |",
        f"| 8:15–9:00 | Resultados: desempenho | {curto[3]} | Otimização · Latência e custo |",
        f"| 9:00–10:00 | Limitações e aprendizados | {curto[0]} | Histórico (filtro REPROVADO) |",
        "",
        "## O que falar em cada bloco",
        "",
        f"### 0:00–1:00 · O problema ({curto[0]})",
        "",
        "> A empresa paga a internet de dezenas de localidades: agências, rodoviárias e garagens. As faturas chegam por e-mail, "
        "em formatos diferentes, e alguém confere uma por uma contra o contrato. Isso atrasa o pagamento e deixa passar cobrança "
        "indevida, como um IP adicional que o contrato não prevê. O SIGp busca as faturas, associa cada uma ao local e ao provedor "
        "e confere com o contrato. A IA ajuda a explicar, mas não decide nem paga nada.",
        "",
        f"### 1:00–3:00 · A arquitetura ({curto[0]})",
        "",
        "> Tudo roda local, em Docker: nenhum dado sai da máquina e não há custo por token. O n8n recebe a fatura e chama a API. "
        "A API é a única que fala com o SQL Server, e com uma credencial que só enxerga o próprio local: o RLS faz isso no banco, não no código. "
        "O RAG busca os trechos do contrato, já filtrados por local e provedor. A regra compara serviço e valor com a evidência "
        "estruturada e decide: CONTRATADO, DIVERGENTE ou REVISAR. O modelo local, um Qwen de 0,5B, dá uma sugestão que medimos, mas que não "
        "tem autoridade. Toda análise fica na trilha de auditoria: quem pediu, o que a IA consultou e o que respondeu.",
        "",
        "Frase para fixar: **a IA sugere, a regra decide, o banco limita e a auditoria registra.**",
        "",
        f"### 3:00–7:00 · Demonstração ao vivo (todos)",
        "",
        "Na raiz do projeto: `pwsh -File docs/entrega-academica/demo-final.ps1`. O passo 0 aquece o modelo; rode-o antes de começar "
        "(veja a lista de conferência) e deixe o terminal parado no Enter do passo 1.",
        "",
        "| Passo | Quem | O que acontece | Falar |",
        "|---|---|---|---|",
        f"| 1 | {curto[1]} | Fatura que bate com o contrato → **CONTRATADO** | O n8n chamou a API; o banco entregou só o LOC-001; o RAG citou o contrato; a regra conferiu serviço e valor. O modelo sugeriu outra coisa e não importa: ele não decide. |",
        f"| 2 | {curto[1]} | IP adicional → **DIVERGENTE** | O contrato diz que IP adicional não está incluído. A regra marca e cita a fonte. É aqui que o sistema economiza. |",
        f"| 3 | {curto[1]} | Prompt injection mandando aprovar → **REVISAR** | O texto da fatura manda aprovar o pagamento. O detector marca a injeção, a decisão vai para revisão humana, e não existe ação de pagamento (`automatic_payment: false`). |",
        f"| 4 | {curto[0]} | Trilha dos 3 pedidos acima | Cada análise deixa 3 eventos com o mesmo identificador: o contexto lido (quantas linhas e de qual local), as fontes do RAG e a resposta (decisão, sugestão do modelo, versão do prompt). A descrição fica só como hash. |",
        f"| 5 | {curto[2]} | Escalonamento de privilégio | Fase 1: sem a correção, o operador do LOC-001 grava no LOC-002 ({esc_a} ataques passaram). Fase 2: todos os {len(esc_d) - 1} ataques barrados, e o controle positivo continua funcionando. |",
        f"| 5b | {curto[2]} | Trilha à prova de adulteração (ledger) | Agora quem tenta é o próprio sa: alterar, apagar e esvaziar a trilha é recusado. O digest do banco vai para o Git e a ledger confere contra ele; um digest falsificado é recusado. |",
        f"| 6 | {curto[3]} | A mesma IA com cada credencial (cerca de 25 s; fale enquanto roda) | Credencial do LOC-001 só vê o LOC-001; credencial errada dá 503 sem nenhum dado; a injeção pedindo o LOC-002 não traz nada; e a IA não consegue escrever na trilha. |",
        f"| 7 | {curto[3]} | Tempos das duas consultas lentas | Consulta 1: {br(q[('A', 1)]['mediana'])} → {br(q[('D', 1)]['mediana'])} ms com o resumo diário mantido por gatilho, com a mesma resposta. Consulta 2: {br(q[('A', 2)]['mediana'])} → {br(q[('C', 2)]['mediana'])} ms com índice filtrado. |",
        "| 8 | (se sobrar tempo) | Verificador de segredos do n8n | Nenhuma chave real nos fluxos exportados nem no repositório. |",
        "",
        f"### 7:00–7:45 · Resultados da IA ({curto[1]})",
        "",
        f"> Nos 16 casos, a decisão foi de {am['acertos']}/16 (F1 {br(am['f1_macro'], 3)}) para {bm['acertos']}/16, e a falsa aprovação "
        f"({', '.join(am['falsas_aprovacoes']) or 'nenhuma'}) sumiu. Mas 16 casos são poucos: com 95% de confiança, 16/16 quer dizer "
        f"{faixa(bm['acertos'], 16)} de acerto. E esses casos foram olhados durante as correções, então o número limpo é o da validação cega, "
        f"escrita antes de rodar o serviço corrigido e nunca usada para ajustar: {bv['ataques_detectados']}/{bv['ataques']} ataques detectados ({faixa(bv['ataques_detectados'], bv['ataques'])}). "
        "Mesmo quando o detector falha, a regra não deixa aprovar valor ou serviço fora do contrato.",
        f"> No fine-tuning, comparamos 4 configurações. O ajustado com RAG acertou {fa['ajustado_rag']['acertos']}/16, o mesmo que o base com RAG: "
        f"o ajuste aprendeu o formato do treino, não a tarefa (no próprio teste do treino ele foi de {fb['base_rag']['acertos']} para "
        f"{fb['ajustado_rag']['acertos']}/20). Por isso o modelo não tem autoridade.",
        "",
        f"### 7:45–8:15 · Resultados da segurança ({curto[2]})",
        "",
        f"> A trilha de auditoria saiu de {tr_a} falhas para {tr_d}/{len(S['trilha']['depois'])}: gravação, alteração com antes e depois, exclusão, "
        f"e as tentativas negadas ficam registradas. A matriz de permissões foi medida no banco, usuário por usuário, com {mz['denys']} DENY "
        f"justificados; a prova do DENY passou {prova_ok}/{len(mz['prova_deny'])}: mesmo com o papel db_datawriter, apagar nota é negado. "
        f"E nenhum segredo nos fluxos do n8n ({seg['arquivos_do_repositorio']} arquivos do repositório e {seg['workflows_ao_vivo']} workflows no ar). "
        + (f"Por fim, a trilha ficou à prova de adulteração: antes, o próprio sa apagava {S['ledger']['antes'].get('DELETE', '?')} eventos sem deixar rastro; "
           "agora ela é ledger, e nem ele altera ou apaga." if S.get("ledger") else ""),
        "",
        f"### 8:15–9:00 · Resultados de desempenho ({curto[3]})",
        "",
        f"> As consultas: {br(q[('A', 1)]['mediana'])} → {br(q[('D', 1)]['mediana'])} ms e {br(q[('A', 2)]['mediana'])} → {br(q[('C', 2)]['mediana'])} ms, "
        f"com {br(q[('A', 1)]['leituras'], 0)} → {br(q[('D', 1)]['leituras'], 0)} leituras lógicas na primeira. O preço: gravar uma nota passou de "
        f"{br(float(cg[('uma_a_uma', 'sem')]['por_nota_us']) / 1000, 2)} para {br(float(cg[('uma_a_uma', 'com')]['por_nota_us']) / 1000, 2)} ms, "
        f"aceitável para algumas notas por dia. A análise de uma fatura nova foi de {lat_txt}: dois terços do prompt eram "
        "contexto que a regra nem usava. "
        + (f"Por 1.000 análises: {br(v31['custo']['tempo_cpu_min'], 0)} min de CPU e R$ {br(v31['custo']['reais_15w'], 3)} a "
           f"R$ {br(v31['custo']['reais_55w'], 3)} de energia, sem custo por token." if v31 else ""),
        "",
        f"### 9:00–10:00 · Limitações e aprendizados ({curto[0]})",
        "",
        "> O que não está resolvido: o detector de injeção generaliza pela metade (homóglifos e engenharia social escapam); o modelo de 0,5B "
        "não classifica sozinho; o dono do banco passa por cima de tudo; e os dados são sintéticos. "
        f"Registramos cada teste que reprovou ({tipos['REPROVADO']}) e cada erro dos nossos próprios testes ({tipos['ERRO DO TESTE']}), "
        "com causa, correção e reteste. O maior aprendizado foi desconfiar do próprio teste: uma medição com cache chegou a mostrar 0,8 s, "
        "quando o real era mais de 30 s.",
        "",
        "## Lista de conferência",
        "",
        "**Na véspera**",
        "- `git push origin main` e conferir que o GitHub mostra os últimos commits.",
        "- Rodar a demonstração inteira sem pausa (gera o plano B): `pwsh -File docs/entrega-academica/demo-final.ps1 -SemPausa`.",
        "- Ensaiar com cronômetro. Se passar de 10 min, corte o passo 8 e encurte a arquitetura.",
        "",
        "**30 minutos antes**",
        "- Fechar programas pesados (a CPU dividida deixa a IA mais lenta).",
        "- Conferir os containers: `docker ps --format \"{{.Names}} {{.Status}}\"` deve mostrar `sigp_sqlserver_academic`, `sigp_academic_ai`, `sigp_n8n` e `sigp_ollama`.",
        "- Abrir `docs/entrega-academica/apresentacao.html` no navegador e deixar na Visão geral.",
        "- Abrir o terminal na raiz do projeto, com fonte grande (Ctrl + roda do mouse).",
        "",
        "**5 minutos antes**",
        f"- Rodar `pwsh -File docs/entrega-academica/demo-final.ps1` e deixar parado no Enter do passo 1. O passo 0 já carregou o modelo; "
        + (f"sem isso, a primeira análise leva cerca de {br(fria['primeira_ms'] / 1000, 0)} s." if fria else "sem isso, a primeira análise é bem mais lenta."),
        "- Não abrir `.env` nem `.env.academic` com a tela compartilhada.",
        "",
        "## Plano B",
        "",
        "| Se… | Faça |",
        "|---|---|",
        "| Um container não está no ar | `docker start sigp_sqlserver_academic sigp_academic_ai sigp_n8n sigp_ollama` e espere 30 s. |",
        "| O n8n não responde (passos 1 a 3) | `docker restart sigp_n8n` (30 s) e enquanto isso mostre a seção Casos de teste da página. |",
        f"| A IA demora mais de 15 s | É o modelo carregando (partida a frio). Diga isso, espere e siga: a regra decide em milissegundos. |",
        "| Algo falha e não volta | Abra `sqlserver/evidence/parte3/demo-final-saida.txt` (a saída de uma demonstração completa) e a página, que funciona sem internet. |",
        "",
        "## Perguntas prováveis e respostas",
        "",
        f"**16 casos bastam?** Não para estimar o erro em produção, e dizemos isso. Com 95% de confiança, 16/16 é {faixa(bm['acertos'], 16)} e "
        f"0 falsas aprovações em 16 pode chegar a {faixa(0, 16).split(' a ')[1]}. Por isso separamos a validação cega, congelada por hash "
        "(`ia/conjuntos-congelados.json`; mudar o arquivo quebra um teste). Ela é o número limpo.",
        "",
        f"**Por que o modelo não decide?** Porque medimos: sozinho, ele acertou {B['metricas']['modelo_acertos']}/16, respondendo REVISAR em quase tudo; o modelo base sem RAG aprovou "
        f"{fa['base']['falsas']} cobranças indevidas. A regra sobre evidência estruturada acerta e é auditável.",
        "",
        f"**O fine-tuning valeu a pena?** Não, e mostramos por quê: fora do treino, {fa['ajustado_rag']['acertos']}/16 nos casos finais com RAG "
        f"(base com RAG: {fa['base_rag']['acertos']}/16)"
        + (f" e {F['conjuntos']['C']['ajustado_rag']['acertos']}/{F['conjuntos']['C']['ajustado_rag']['n']} fora de escopo" if 'C' in F['conjuntos'] else "")
        + ". O treino tinha frases curtas; o RAG entrega o texto do contrato, que diz o que não está incluído, e o modelo leu a negação como divergência. "
        + ("No IA-009 ele ainda obedeceu à injeção. " if 'IA-009' in (fa['ajustado_rag'].get('falsas_ids') or []) else "")
        + "O próximo passo seria treinar com o texto real do RAG, com documentos fora de escopo e com exemplos de injeção.",
        "",
        "**Qual prompt o sistema avaliado usa?** A análise de fatura (`/api/analyze`) usa o v"
        f"{B['servico']['prompt_version']}, com busca {('por embedding (' + B['servico']['embed_model'] + ')') if B['servico'].get('embed_model') else 'lexical'}; "
        "o v4.2 é o da triagem do Gmail, outro fluxo. A avaliação final rodou no serviço com a mesma configuração que o pacote sobe, e "
        "`tests/test_pacote_mesma_ia.py` falha se o pacote divergir.",
        "",
        "**O RAG com embeddings ajudou?** "
        + (f"Nas paráfrases (a cobrança com outras palavras), a fonte certa veio em {d['rag']['metodos'][d['rag']['escolha']]['parafrases']['acertos']}/"
           f"{d['rag']['metodos'][d['rag']['escolha']]['parafrases']['total']} contra {d['rag']['metodos']['lexical']['parafrases']['acertos']}/"
           f"{d['rag']['metodos']['lexical']['parafrases']['total']} da busca por palavras, sem perder caso final. O critério foi versionado antes "
           "de medir, e a busca só ordena o que o escopo do local já permite." if d.get('rag') and d['rag']['escolha'] else "Ver ia/rag-embeddings.md."),
        "",
        "**E se um ataque não for detectado?** O pior caso é uma fatura cujo serviço e valor já batem com o contrato sair CONTRATADO sem a "
        "marca de revisão. O ataque não aprova valor diferente, não traz dado de outro local (credencial, RLS e RAG filtrado) e não paga nada.",
        "",
        "**Mascaramento protege a chave fiscal?** Só na exibição: dá para inferir por filtro. Por isso a IA e quem não precisa da linha nem têm "
        "leitura na tabela, e o RLS limita o local. Não usamos Always Encrypted: a conciliação procura nota pela chave, e o banco só compara com a "
        "chave criptográfica dentro da API (a versão determinística permitiria a igualdade, mas quem usa a API continuaria vendo a chave). "
        + (f"O TDE está ligado: o arquivo e os backups ficam criptografados (num backup sem compressão, a chave fiscal saiu de "
           f"{S['tde']['chave_fiscal_em_texto_no_backup_antes']} ocorrências em texto puro para {S['tde']['chave_fiscal_em_texto_no_backup_depois']}), "
           "mas ele não muda quem vê o quê numa consulta." if S.get("tde") else ""),
        "",
        "**O db_owner pode tudo?** Passa por cima do RLS e do mascaramento, e está nas limitações. Mas não apaga o passado: a trilha é uma "
        "tabela ledger do SQL Server 2022. Antes da mudança, numa cópia do banco, o sa reescreveu e apagou eventos sem erro; agora UPDATE e "
        "DELETE dão 37359 até para ele, e o digest guardado no Git denuncia qualquer alteração feita direto no arquivo. O que ele ainda pode é "
        "parar de registrar daqui em diante. A senha dele só existe no `.env.academic`, fora do Git.",
        "",
        f"**Por que não uma view indexada?** O SQL Server não permite view indexada sobre tabela com RLS, e ela exporia os totais de todos os "
        "locais. O resumo diário por gatilho respeita o RLS e dá a mesma resposta (0 linhas diferentes).",
        "",
        f"**Por que a consulta original ficou mais lenta que na entrega 2?** As consultas são idênticas e as leituras lógicas são as mesmas; "
        "mudou a CPU disponível na hora da medição. Por isso cada ganho é calculado dentro da mesma rodada, sempre com mediana e p95.",
        "",
        "**Como vocês sabem que a IA não vaza dado de outro local?** Teste perfil por perfil (passo 6): a credencial define o local, o banco "
        "nega o resto, o RAG é filtrado antes da busca, e a resposta não devolve linhas do banco, só a contagem.",
        "",
        "**Por que o pacote baixa o modelo de 3B, se o pedido era baixar pouco?** Porque medimos antes de escolher, com o critério escrito "
        "antes da medição (`ia/escolha-modelo-criterio.md`). Na 1ª medição, o 3B às vezes não terminava a resposta e a escolha seria o 0,5B. "
        "Olhando a resposta crua, achamos a causa (o campo motivo não acabava) e corrigimos no JSON Schema; na 2ª medição o 3B respondeu a "
        "todos os documentos e acertou bem mais, e pelo mesmo critério virou o padrão. A instalação leve continua disponível. A correção "
        "também foi para a produção: antes, um documento podia travar a fila por 300 s.",
        "",
        "**O que a auditoria guarda da IA?** Quem pediu, quantas linhas leu e de qual local, as fontes citadas, a decisão, a sugestão do "
        "modelo, a versão do prompt e o hash da descrição. Se a auditoria falhar, a análise não sai (503).",
        "",
        "**Tem segredo no repositório?** Não. Um verificador procura as chaves reais do `.env` nos fluxos do n8n e no repositório; as "
        "credenciais ficam em variáveis de ambiente.",
        "",
        "## Onde está cada requisito",
        "",
        "| Requisito | Documento |",
        "|---|---|",
        "| Casos de teste com métrica e análise das falhas | `ia/casos-de-teste-final.md` |",
        "| Fine-tuning: base, base + RAG, ajustado, ajustado + RAG; custo e latência | `ia/finetuning/comparacao-final.md` |",
        "| Prompt injection testado e as defesas | `ia/casos-de-teste-final.md` (bateria, validação cega, camadas) |",
        "| Fluxo do n8n sem segredo | `ia/segredos-n8n.md` |",
        "| Papéis e permissões com DENY justificado | `seguranca/matriz-permissoes.md` |",
        "| Dados sensíveis (RLS e mascaramento) | `seguranca/protecao-dados-sensiveis.md` |",
        "| Duas consultas lentas, plano e tempos | `seguranca/otimizacao-consultas.md` |",
        "| Ataque e correção (escalonamento) | `seguranca/ataque-escalonamento.md` |",
        "| Trilha \"quem fez o quê\", à prova de adulteração (ledger) | `seguranca/trilha-auditoria.md` |",
        "| Auditoria do que a IA respondeu e a IA por perfil | `seguranca/auditoria-e-ia-por-perfil.md` |",
        "| Histórico de falhas, correções e retestes | `historico-evolucao.md` |",
        "| Limitações | `relatorio-limitacoes.pdf` |",
        "",
    ]
    SAIDA.write_text("\n".join(L), encoding="utf-8")
    print(f"ok: {SAIDA}")


if __name__ == "__main__":
    main()
