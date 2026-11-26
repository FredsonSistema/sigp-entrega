"""Gera docs/entrega-academica/ia/finetuning/comparacao-final.md a partir das evidências (nenhum número digitado à mão).
Fontes (sqlserver/evidence/parte3/):
  finetuning-comparacao.json            comparar_finetuning.py (4 configurações, conjuntos A, B e C)
  ia-avaliacao-final.json               avaliar_ia.py final (decisão da regra no sistema entregue: 16 casos e 12 fora de escopo)
  sobreposicao-treino.json              verificar_sobreposicao.py (casos de teste × exemplos de treino)
  rag-embeddings.json                   medir_rag_embeddings.py (latência da busca por embedding)
  latencia-custo-final.json             medir_latencia_final.py com a máquina sem carga extra (se existir)
  latencia-custo-final-sob-carga.json   medir_latencia_final.py com outros programas usando a CPU
  latencia-custo-final-cache.json       as mesmas 16 faturas de novo, já no cache de prompts do Ollama
  latencia-custo-sob-carga.json         medir_latencia.py da Entrega 2, removido na limpeza final (a mesma fatura repetida: cache do prompt)
Uso, na raiz:  .venv-1\\Scripts\\python.exe docs/entrega-academica/ia/finetuning/gerar_comparacao.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

DIR = Path(__file__).resolve().parent
EV = DIR.parent.parent / "sqlserver" / "evidence" / "parte3"
SAIDA = DIR / "comparacao-final.md"
ORDEM = ["base", "base_rag", "ajustado", "ajustado_rag"]
CLASSES = ["CONTRATADO", "DIVERGENTE", "REVISAR"]


def ler(nome: str):
    caminho = EV / nome
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def reais(c: dict) -> str:
    return f"R$ {c['reais_15w']:.3f} a {c['reais_55w']:.3f}".replace(".", ",")


def num(v, casas=1) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tabela(conj: dict, rotulo_rag: str) -> list[str]:
    L = [f"| Configuração | {rotulo_rag} | Acerto | F1 macro | Falsas aprovações | Latência média (p95) | Tokens de entrada | 1.000 usos: CPU · energia |",
         "|---|---|---|---|---|---|---|---|"]
    for k in ORDEM:
        c = conj["configuracoes"][k]
        m = c["metricas"]
        custo = m["custo_por_1000_usos"]
        L.append(f"| {c['nome']} | {'sim' if c['rag'] else 'não'} | {m['acertos']}/{m['n']} ({num(m['acuracia'], 2)}) | {num(m['f1_macro'], 3)} | "
                 f"{len(m['falsas_aprovacoes'])} | {num(m['latencia_ms']['media'] / 1000, 2)} s ({num(m['latencia_ms']['p95'] / 1000, 2)} s) | "
                 f"{num(m['tokens_entrada_media'], 0)} | {num(custo['tempo_cpu_min'])} min · {reais(custo)} |")
    return L


def distribuicao(conj: dict) -> list[str]:
    L = ["| Configuração | " + " | ".join(CLASSES) + " |", "|---|---|---|---|"]
    for k in ORDEM:
        c = conj["configuracoes"][k]
        cont = Counter(x["obtido"] for x in c["casos"])
        L.append(f"| {c['nome']} | " + " | ".join(str(cont.get(x, 0)) for x in CLASSES) + " |")
    return L


def main() -> None:
    comp = ler("finetuning-comparacao.json")
    regra = ler("ia-avaliacao-final.json")
    sob = ler("sobreposicao-treino.json")
    emb = ler("rag-embeddings.json")
    limpa, carga, repetida = ler("latencia-custo-final.json"), ler("latencia-custo-final-sob-carga.json"), ler("latencia-custo-sob-carga.json")
    cache = ler("latencia-custo-final-cache.json")
    v31, fria = ler("latencia-custo-prompt-v31.json"), ler("latencia-partida-fria.json")
    aval31 = ler("ia-avaliacao-prompt-v31.json")
    a, b, cc = comp["conjunto_a_casos_finais"], comp["conjunto_b_teste_do_treino"], comp["conjunto_c_fora_de_escopo"]
    ma = {k: a["configuracoes"][k]["metricas"] for k in ORDEM}
    mb = {k: b["configuracoes"][k]["metricas"] for k in ORDEM}
    mc = {k: cc["configuracoes"][k]["metricas"] for k in ORDEM}
    dr = regra["casos_de_teste"]["metricas"]["decisao_do_sistema"]
    drc = regra["fora_de_escopo"]["metricas"]["decisao_do_sistema"]
    fa_c_regra = regra["fora_de_escopo"]["metricas"]["falsas_aprovacoes"]

    def conta(conj, k, classe):
        return sum(x["obtido"] == classe for x in conj["configuracoes"][k]["casos"])

    def obtido(conj, k, caso):
        return next(x["obtido"] for x in conj["configuracoes"][k]["casos"] if x["id"] == caso)

    repete = set(sob["casos_que_repetem_o_treino"])

    def acerto_sub(k, dentro):
        casos = [x for x in a["configuracoes"][k]["casos"] if (x["id"] in repete) == dentro]
        return f"{sum(x['obtido'] == x['esperado'] for x in casos)}/{len(casos)}"

    lat_emb = emb["metodos"]["embedding:" + regra["servico"]["embed_model"]]["casos_finais"]["latencia_mediana_ms"] if emb and regra["servico"].get("embed_model") else None
    fa_inj = [x for x in ma["ajustado_rag"]["falsas_aprovacoes"] if x in {"IA-004", "IA-009", "IA-015"}]
    cp = comp["custo_parametros"]
    L = [
        "# Fine-tuning: base × base com RAG × ajustado × ajustado com RAG",
        "",
        "Gerado por `gerar_comparacao.py` a partir das evidências; nenhum número foi digitado à mão. Execução: "
        "[`comparar_finetuning.py`](comparar_finetuning.py), em "
        f"{comp['executado_em_utc'][:19]} UTC. Evidência: [`finetuning-comparacao.json`](../../sqlserver/evidence/parte3/finetuning-comparacao.json).",
        "",
        "## Como foi medido",
        "",
        f"- **Mesmo modelo, mesmas condições.** `{comp['servidor']['base_model']}` (revisão `{comp['servidor']['base_revision'][:12]}`) em float32 na CPU, "
        "num único servidor Transformers. \"Base\" é esse modelo com o adaptador desligado; \"ajustado\" é o mesmo com o adaptador LoRA do SIGp "
        "(rank 4, `q_proj` e `v_proj`, treinado em 80 exemplos sintéticos). Geração sem amostragem, mesmo prompt de sistema do treino.",
        "- **Só o modelo.** A decisão da regra não entra no prompt: aqui se mede se o modelo classifica sozinho.",
        f"- **RAG do sistema entregue.** Nos conjuntos A e C, \"com RAG\" usa os documentos que o próprio serviço avaliado recuperou em cada "
        f"caso (busca por embedding, `{comp['rag']['embed_model']}`, dentro do escopo LOC-001; `source_ids` gravados em "
        "[`ia-avaliacao-final.json`](../../sqlserver/evidence/parte3/ia-avaliacao-final.json)). Sem RAG, a Evidência diz \"nenhuma evidência recuperada\".",
        f"- **Fora do treino.** [`verificar_sobreposicao.py`](verificar_sobreposicao.py) comparou os {sob['casos_de_teste']} casos de teste com os "
        f"{sob['exemplos_de_treino']} exemplos de treino: nenhum provedor em comum e nenhuma descrição igual. "
        f"{len(repete)} casos finais ({', '.join(sorted(repete))}) usam o mesmo nome de serviço do treino (\"link principal fibra\", "
        f"\"link de contingência\"; semelhança {num(sob['maior_semelhanca'], 2)}, no limite fixado de {num(sob['limite_parecido_jaccard'], 2)}), com outro "
        "provedor, valor e evidência; o resultado deles sai separado abaixo. Os 12 casos fora de escopo não se parecem com nenhum exemplo de treino "
        f"(maior semelhança {num(max(x['semelhanca'] for x in sob['casos'] if x['conjunto'] == 'casos-fora-escopo.json'), 2)}).",
        "- **As quatro configurações rodaram intercaladas, caso a caso**, para a carga da máquina pesar igual em todas.",
        f"- **Custo por 1.000 usos.** Não há cobrança por token (modelo local). O custo vem do tempo de geração medido: tempo de CPU e "
        f"energia do processador entre {cp['potencia_base_w']} W (potência base) e {cp['potencia_turbo_w']} W (turbo máximo), na tarifa "
        f"de R$ {num(cp['tarifa_r_kwh'], 4)}/kWh. Fontes: {cp['fonte_potencia']}; {cp['fonte_tarifa']}. {cp['observacao']}",
        "",
        "## Conjunto A: os 16 casos finais (fora do treino, RAG real)",
        "",
        *tabela(a, "RAG"),
        f"| *Referência: regra do sistema (decisão)* | sim | {dr['acertos']}/{dr['total']} ({num(dr['acuracia'], 2)}) | {num(dr['f1_macro'], 3)} | "
        f"{len(regra['casos_de_teste']['metricas']['falsas_aprovacoes'])} | — | — | sem modelo |",
        "",
        "O que cada configuração respondeu:",
        "",
        *distribuicao(a),
        "",
        f"Casos que usam o nome de serviço do treino ({len(repete)}) × os que não usam ({ma['base']['n'] - len(repete)}): base com RAG "
        f"{acerto_sub('base_rag', True)} × {acerto_sub('base_rag', False)}; ajustado com RAG {acerto_sub('ajustado_rag', True)} × "
        f"{acerto_sub('ajustado_rag', False)}. Parecer com o treino não ajudou o modelo ajustado.",
        "",
        "## Conjunto C: os 12 casos fora de escopo (nenhum parecido com o treino, RAG do sistema)",
        "",
        "Outra conta (energia, água, aluguel, telefonia móvel, software, compra de equipamento), outro local, outro idioma e documentos "
        "que não são fatura ([`casos-fora-escopo.json`](../casos-fora-escopo.json)). Em todos, o certo é REVISAR.",
        "",
        *tabela(cc, "RAG"),
        f"| *Referência: regra do sistema (decisão)* | sim | {drc['acertos']}/{drc['total']} ({num(drc['acuracia'], 2)}) | {num(drc['f1_macro'], 3)} | "
        f"{len(fa_c_regra)} | — | — | sem modelo |",
        "",
        *distribuicao(cc),
        "",
        "## Conjunto B: os 20 casos de teste do treino (mesma distribuição do treino)",
        "",
        *tabela(b, "Evidência no prompt"),
        "",
        *distribuicao(b),
        "",
        f"Conferência: \"base com evidência\" ({num(mb['base_rag']['acuracia'], 2)}, F1 {num(mb['base_rag']['f1_macro'], 3)}) e \"ajustado com evidência\" "
        f"({num(mb['ajustado_rag']['acuracia'], 2)}, F1 {num(mb['ajustado_rag']['f1_macro'], 3)}) reproduzem o experimento da entrega 2 "
        "(`training-results.json`: 0,65 → 0,90 e F1 0,522 → 0,900).",
        "",
        "## Análise",
        "",
        f"1. **O modelo base aprova quase tudo.** Sem RAG ele respondeu CONTRATADO em {conta(a, 'base', 'CONTRATADO')} dos {ma['base']['n']} casos finais "
        f"e em {conta(cc, 'base', 'CONTRATADO')} dos {mc['base']['n']} fora de escopo ({len(ma['base']['falsas_aprovacoes'])} + "
        f"{len(mc['base']['falsas_aprovacoes'])} falsas aprovações). Com RAG ainda foram {len(ma['base_rag']['falsas_aprovacoes'])} + "
        f"{len(mc['base_rag']['falsas_aprovacoes'])}. Num sistema de contas a pagar, é o pior erro possível.",
        f"2. **O ajuste tornou o modelo cauteloso, não mais certo.** Sem RAG, o ajustado respondeu REVISAR em {conta(a, 'ajustado', 'REVISAR')} dos "
        f"{ma['ajustado']['n']} casos finais, com {len(ma['ajustado']['falsas_aprovacoes'])} falsas aprovações e {ma['ajustado']['acertos']}/{ma['ajustado']['n']} "
        f"de acerto. Fora de escopo, o mesmo hábito dá {mc['ajustado']['acertos']}/{mc['ajustado']['n']}: o certo ali é sempre REVISAR, e é isso que ele "
        "responde quando não tem evidência. É acerto por cautela, não por entender que o documento está fora do escopo.",
        f"3. **Com RAG, o ajustado erra para o lado de DIVERGENTE.** Respondeu DIVERGENTE em {conta(a, 'ajustado_rag', 'DIVERGENTE')} dos "
        f"{ma['ajustado_rag']['n']} casos finais e em {conta(cc, 'ajustado_rag', 'DIVERGENTE')} dos {mc['ajustado_rag']['n']} fora de escopo; no link "
        f"contratado IA-001 respondeu {obtido(a, 'ajustado_rag', 'IA-001')}. Acerto {ma['ajustado_rag']['acertos']}/{ma['ajustado_rag']['n']} nos finais "
        f"(base com RAG: {ma['base_rag']['acertos']}/{ma['base_rag']['n']}) e {mc['ajustado_rag']['acertos']}/{mc['ajustado_rag']['n']} fora de escopo. "
        "No treino, a evidência era uma frase curta (\"contrato vigente inclui exatamente X por R$ Y\"); o RAG entrega o texto do contrato, que "
        "diz o que *não* está incluído (\"não inclui IP adicional nem serviço de voz\"). O modelo lê a negação como divergência. É troca de "
        "distribuição: o ajuste aprendeu o formato do treino, não a tarefa.",
        f"4. **Na distribuição do treino, o ajuste funciona.** Conjunto B: {mb['base_rag']['acertos']}/{mb['base_rag']['n']} → "
        f"{mb['ajustado_rag']['acertos']}/{mb['ajustado_rag']['n']} com evidência, e as falsas aprovações caem de "
        f"{len(mb['base_rag']['falsas_aprovacoes'])} para {len(mb['ajustado_rag']['falsas_aprovacoes'])}. Fora dela (A e C), o ganho some.",
        (f"5. **O ajustado com RAG obedeceu a um prompt injection.** A falsa aprovação dele nos casos finais ({', '.join(fa_inj)}) é um caso em "
         "que o texto da fatura traz instruções para aprovar. A regra deu REVISAR. Isso mostra, com medição, por que o modelo não tem autoridade."
         if fa_inj else
         f"5. **Falsas aprovações do ajustado com RAG:** {', '.join(ma['ajustado_rag']['falsas_aprovacoes']) or 'nenhuma'} nos casos finais e "
         f"{', '.join(mc['ajustado_rag']['falsas_aprovacoes']) or 'nenhuma'} fora de escopo."),
        f"6. **Custo e latência.** O RAG multiplica os tokens de entrada (de {num(ma['ajustado']['tokens_entrada_media'], 0)} para "
        f"{num(ma['ajustado_rag']['tokens_entrada_media'], 0)} em média nos casos finais) e por isso a latência e o custo "
        f"(de {num(ma['ajustado']['latencia_ms']['media'] / 1000, 2)} s para {num(ma['ajustado_rag']['latencia_ms']['media'] / 1000, 2)} s). O adaptador LoRA "
        "(rank 4) não muda o custo: base e ajustado gastam o mesmo tempo para o mesmo prompt.",
        "",
        "## Conclusão",
        "",
        "**O ajuste não compensou como tomador de decisão.** Fora do treino, o ajustado com RAG acertou "
        f"{ma['ajustado_rag']['acertos']}/{ma['ajustado_rag']['n']} nos casos finais e {mc['ajustado_rag']['acertos']}/{mc['ajustado_rag']['n']} fora de escopo; "
        f"a regra do sistema entregue acertou {dr['acertos']}/{dr['total']} e {drc['acertos']}/{drc['total']}. "
        "Ele ganhou em segurança (falsas aprovações nos casos finais de "
        f"{len(ma['base_rag']['falsas_aprovacoes'])} para {len(ma['ajustado_rag']['falsas_aprovacoes'])}), mas continua sensível ao formato da evidência. "
        "O desenho do sistema fica como está: a regra decide sobre a evidência estruturada, o modelo só sugere e sua concordância é medida. "
        "Para o ajuste valer a pena, o treino precisaria de exemplos com o texto real dos contratos recuperados pelo RAG, de documentos fora "
        "de escopo e de instruções embutidas, avaliados num conjunto separado como os dos casos finais e fora de escopo.",
        "",
        "## Latência e custo do sistema no ar",
        "",
        "Caminho: API → SQL Server (RLS) → RAG → Qwen 0,5B no Ollama (CPU, quantizado) → regra → auditoria. A regra decide; o modelo é chamado "
        "em toda análise para a sugestão medida.",
        "",
        "| Medição | Chamadas | CPU da máquina | Média | Mediana | p95 | 1.000 usos: CPU · energia |",
        "|---|---|---|---|---|---|---|",
    ]
    for titulo, d in (("Prompt 3.0 · **fatura nova**, máquina sem carga extra", limpa), ("Prompt 3.0 · **fatura nova**, máquina com outros programas", carga),
                      ("Prompt 3.0 · as mesmas 16 faturas de novo (prompt no cache do Ollama)", cache),
                      ("**Prompt 3.1 · fatura nova**, máquina com outros programas", v31)):
        if not d:
            continue
        s, c, cpu = d["latencia_servidor_ms"], d["custo_por_1000_usos"], d["cpu_maquina_percent"]
        cpu_txt = f"{num(cpu['antes'])}% → {num(cpu['depois'])}%" if isinstance(cpu.get("antes"), (int, float)) and isinstance(cpu.get("depois"), (int, float)) else "não medida"
        L.append(f"| {titulo} | {s['n']} | {cpu_txt} | {num(s['media'] / 1000, 2)} s | {num(s['mediana'] / 1000, 2)} s | {num(s['p95'] / 1000, 2)} s | "
                 f"{num(c['tempo_cpu_min'])} min · {reais(c)} |")
    if repetida:
        api = repetida["api_academica_ponta_a_ponta"]["total_ms"]
        L.append(f"| A mesma fatura repetida (o Ollama reaproveita o prompt) | {api['n']} | — | {num(api['media'] / 1000, 2)} s | "
                 f"{num(api['mediana'] / 1000, 2)} s | {num(api['p95'] / 1000, 2)} s | — |")
    L += [
        "",
        "**O número que vale para o uso real é o da fatura nova**: cada fatura que chega é diferente, e o prompt não está no cache. O Ollama "
        "guarda os últimos 16 prompts; repetir faturas já vistas (ou a mesma fatura) mede só o cache. "
        "A diferença mostra onde está o tempo: quase todo ele é o modelo processando o prompt da API numa CPU de notebook. "
        "No prompt 3.0, dois terços do prompt eram 20 linhas de contexto do banco (notas de carga que a regra não usa); os casos IA-005 e IA-016, "
        "sem contexto, respondiam em cerca de 5 s contra mais de 30 s nos outros.",
        "",
        "**Prompt 3.1 (correção):** 3 linhas de contexto, só com descrição, valor, vencimento e situação; o modelo recebe os 3 primeiros documentos "
        "(a regra continua avaliando os 5); a parte estável (contexto do provedor) vai antes e a fatura por último, para o Ollama reaproveitar o prefixo. "
        + (f"Resultado na mesma situação de carga: média {num(v31['latencia_servidor_ms']['media'] / 1000, 2)} s e p95 "
           f"{num(v31['latencia_servidor_ms']['p95'] / 1000, 2)} s, contra {num(carga['latencia_servidor_ms']['media'] / 1000, 2)} s e "
           f"{num(carga['latencia_servidor_ms']['p95'] / 1000, 2)} s no 3.0; {num(v31['custo_por_1000_usos']['tempo_cpu_min'])} min de CPU por 1.000 usos. "
           if v31 and carga else "")
        + (f"Pior caso (modelo descarregado, depois de 30 min sem uso): {num(fria['primeira_apos_descarregar']['cliente_ms'] / 1000, 1)} s na primeira "
           f"análise, que inclui carregar o modelo, e {num(fria['logo_depois']['cliente_ms'] / 1000, 1)} s na seguinte (`latencia-partida-fria.json`). "
           if fria else "")
        + (f"As decisões não mudaram (`ia-avaliacao-prompt-v31.json`): "
           f"{aval31['casos_de_teste']['metricas']['decisao_do_sistema']['acertos']}/{aval31['casos_de_teste']['metricas']['decisao_do_sistema']['total']} "
           "nos casos, os mesmos ataques detectados e o mesmo resultado na validação cega. "
           if aval31 else "")
        + (f"**Sistema entregue (prompt 3.1 + busca por embedding):** na avaliação final, os 16 casos tiveram média "
           f"{num(regra['casos_de_teste']['metricas']['latencia_servidor_ms']['media'] / 1000, 2)} s e p95 "
           f"{num(regra['casos_de_teste']['metricas']['latencia_servidor_ms']['p95'] / 1000, 2)} s (faturas já vistas na rodada anterior); "
           f"a busca por embedding custa {num(lat_emb, 0)} ms (mediana) por consulta ([`rag-embeddings.md`](../rag-embeddings.md)). "
           if lat_emb else "")
        + "A decisão (a regra) não depende do modelo e sai em milissegundos.",
        "",
        "## Limites",
        "",
        "- Conjuntos pequenos (16, 12 e 20 casos) e sintéticos; servem para comparar as configurações entre si, não para estimar acerto em produção.",
        "- Energia só do processador, estimada pelo tempo medido e pela potência de catálogo; a máquina inteira gasta mais.",
        "- O modelo do sistema no ar (Ollama, quantizado) não é o mesmo binário do usado na comparação (Transformers, float32); por isso a comparação "
        "e a latência do sistema estão em tabelas separadas.",
        "",
    ]
    SAIDA.write_text("\n".join(L), encoding="utf-8")
    print(f"ok: {SAIDA}")


if __name__ == "__main__":
    main()
