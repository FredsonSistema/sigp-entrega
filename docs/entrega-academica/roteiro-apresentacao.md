# Roteiro da apresentação final (10 minutos)

Gerado por `apresentacao/gerar_roteiro.py` a partir das evidências (os mesmos números da `apresentacao.html` e dos PDFs). Se uma evidência mudar, gere de novo: `python docs/entrega-academica/apresentacao/gerar_roteiro.py`.

Material usado na apresentação:
- **`apresentacao.html`** (abre no navegador, sem internet): a página dos resultados. As setas do teclado passam de uma seção para a outra.
- **`demo-final.ps1`**: a demonstração ao vivo, passo a passo. Cada passo mostra o que falar e espera Enter.
- **`relatorio-apresentacao.pdf`** e **`relatorio-limitacoes.pdf`**: para entregar e para consulta.
- **Plano B:** `sqlserver/evidence/parte3/demo-final-saida.txt` (a saída completa de uma demonstração já rodada).

## Divisão e tempos

Estrutura pedida: problema 1 min, arquitetura 2 min, demonstração 4 min, resultados 2 min e limitações 1 min. A divisão segue a área de cada um; ajustem se preferirem.

| Tempo | Bloco | Quem | Mostrar |
|---|---|---|---|
| 0:00–1:00 | O problema | Fredson | `apresentacao.html` · Visão geral |
| 1:00–3:00 | A arquitetura | Fredson | Visão geral (fluxo) |
| 3:00–4:30 | Demonstração: IA (passos 1 a 3) | Maciel | terminal: `demo-final.ps1` |
| 4:30–5:00 | Demonstração: trilha da IA (passo 4) | Fredson | terminal |
| 5:00–5:45 | Demonstração: escalonamento e trilha à prova de adulteração (passos 5 e 5b) | Aeverton | terminal |
| 5:45–7:00 | Demonstração: IA por perfil e consultas (passos 6 e 7) | Jonatas | terminal |
| 7:00–7:45 | Resultados: IA | Maciel | Casos de teste · Prompt injection · Fine-tuning |
| 7:45–8:15 | Resultados: segurança | Aeverton | Segurança |
| 8:15–9:00 | Resultados: desempenho | Jonatas | Otimização · Latência e custo |
| 9:00–10:00 | Limitações e aprendizados | Fredson | Histórico (filtro REPROVADO) |

## O que falar em cada bloco

### 0:00–1:00 · O problema (Fredson)

> A empresa paga a internet de dezenas de localidades: agências, rodoviárias e garagens. As faturas chegam por e-mail, em formatos diferentes, e alguém confere uma por uma contra o contrato. Isso atrasa o pagamento e deixa passar cobrança indevida, como um IP adicional que o contrato não prevê. O SIGp busca as faturas, associa cada uma ao local e ao provedor e confere com o contrato. A IA ajuda a explicar, mas não decide nem paga nada.

### 1:00–3:00 · A arquitetura (Fredson)

> Tudo roda local, em Docker: nenhum dado sai da máquina e não há custo por token. O n8n recebe a fatura e chama a API. A API é a única que fala com o SQL Server, e com uma credencial que só enxerga o próprio local: o RLS faz isso no banco, não no código. O RAG busca os trechos do contrato, já filtrados por local e provedor. A regra compara serviço e valor com a evidência estruturada e decide: CONTRATADO, DIVERGENTE ou REVISAR. O modelo local, um Qwen de 0,5B, dá uma sugestão que medimos, mas que não tem autoridade. Toda análise fica na trilha de auditoria: quem pediu, o que a IA consultou e o que respondeu.

Frase para fixar: **a IA sugere, a regra decide, o banco limita e a auditoria registra.**

### 3:00–7:00 · Demonstração ao vivo (todos)

Na raiz do projeto: `pwsh -File docs/entrega-academica/demo-final.ps1`. O passo 0 aquece o modelo; rode-o antes de começar (veja a lista de conferência) e deixe o terminal parado no Enter do passo 1.

| Passo | Quem | O que acontece | Falar |
|---|---|---|---|
| 1 | Maciel | Fatura que bate com o contrato → **CONTRATADO** | O n8n chamou a API; o banco entregou só o LOC-001; o RAG citou o contrato; a regra conferiu serviço e valor. O modelo sugeriu outra coisa e não importa: ele não decide. |
| 2 | Maciel | IP adicional → **DIVERGENTE** | O contrato diz que IP adicional não está incluído. A regra marca e cita a fonte. É aqui que o sistema economiza. |
| 3 | Maciel | Prompt injection mandando aprovar → **REVISAR** | O texto da fatura manda aprovar o pagamento. O detector marca a injeção, a decisão vai para revisão humana, e não existe ação de pagamento (`automatic_payment: false`). |
| 4 | Fredson | Trilha dos 3 pedidos acima | Cada análise deixa 3 eventos com o mesmo identificador: o contexto lido (quantas linhas e de qual local), as fontes do RAG e a resposta (decisão, sugestão do modelo, versão do prompt). A descrição fica só como hash. |
| 5 | Aeverton | Escalonamento de privilégio | Fase 1: sem a correção, o operador do LOC-001 grava no LOC-002 (2 ataques passaram). Fase 2: todos os 8 ataques barrados, e o controle positivo continua funcionando. |
| 5b | Aeverton | Trilha à prova de adulteração (ledger) | Agora quem tenta é o próprio sa: alterar, apagar e esvaziar a trilha é recusado. O digest do banco vai para o Git e a ledger confere contra ele; um digest falsificado é recusado. |
| 6 | Jonatas | A mesma IA com cada credencial (cerca de 25 s; fale enquanto roda) | Credencial do LOC-001 só vê o LOC-001; credencial errada dá 503 sem nenhum dado; a injeção pedindo o LOC-002 não traz nada; e a IA não consegue escrever na trilha. |
| 7 | Jonatas | Tempos das duas consultas lentas | Consulta 1: 168,7 → 25,3 ms com o resumo diário mantido por gatilho, com a mesma resposta. Consulta 2: 54,4 → 10,7 ms com índice filtrado. |
| 8 | (se sobrar tempo) | Verificador de segredos do n8n | Nenhuma chave real nos fluxos exportados nem no repositório. |

### 7:00–7:45 · Resultados da IA (Maciel)

> Nos 16 casos, a decisão foi de 12/16 (F1 0,753) para 16/16, e a falsa aprovação (IA-015) sumiu. Mas 16 casos são poucos: com 95% de confiança, 16/16 quer dizer 81% a 100% de acerto. E esses casos foram olhados durante as correções, então o número limpo é o da validação cega, escrita antes de rodar o serviço corrigido e nunca usada para ajustar: 4/8 ataques detectados (22% a 78%). Mesmo quando o detector falha, a regra não deixa aprovar valor ou serviço fora do contrato.
> No fine-tuning, comparamos 4 configurações. O ajustado com RAG acertou 7/16, o mesmo que o base com RAG: o ajuste aprendeu o formato do treino, não a tarefa (no próprio teste do treino ele foi de 13 para 18/20). Por isso o modelo não tem autoridade.

### 7:45–8:15 · Resultados da segurança (Aeverton)

> A trilha de auditoria saiu de 9 falhas para 12/12: gravação, alteração com antes e depois, exclusão, e as tentativas negadas ficam registradas. A matriz de permissões foi medida no banco, usuário por usuário, com 23 DENY justificados; a prova do DENY passou 5/5: mesmo com o papel db_datawriter, apagar nota é negado. E nenhum segredo nos fluxos do n8n (21 arquivos do repositório e 14 workflows no ar). Por fim, a trilha ficou à prova de adulteração: antes, o próprio sa apagava 61 eventos sem deixar rastro; agora ela é ledger, e nem ele altera ou apaga.

### 8:15–9:00 · Resultados de desempenho (Jonatas)

> As consultas: 168,7 → 25,3 ms e 54,4 → 10,7 ms, com 3.281 → 13 leituras lógicas na primeira. O preço: gravar uma nota passou de 0,09 para 0,70 ms, aceitável para algumas notas por dia. A análise de uma fatura nova foi de 31,3 s → 3,1 s (p95 4,8 s): dois terços do prompt eram contexto que a regra nem usava. Por 1.000 análises: 51 min de CPU e R$ 0,016 a R$ 0,059 de energia, sem custo por token.

### 9:00–10:00 · Limitações e aprendizados (Fredson)

> O que não está resolvido: o detector de injeção generaliza pela metade (homóglifos e engenharia social escapam); o modelo de 0,5B não classifica sozinho; o dono do banco passa por cima de tudo; e os dados são sintéticos. Registramos cada teste que reprovou (26) e cada erro dos nossos próprios testes (11), com causa, correção e reteste. O maior aprendizado foi desconfiar do próprio teste: uma medição com cache chegou a mostrar 0,8 s, quando o real era mais de 30 s.

## Lista de conferência

**Na véspera**
- `git push origin main` e conferir que o GitHub mostra os últimos commits.
- Rodar a demonstração inteira sem pausa (gera o plano B): `pwsh -File docs/entrega-academica/demo-final.ps1 -SemPausa`.
- Ensaiar com cronômetro. Se passar de 10 min, corte o passo 8 e encurte a arquitetura.

**30 minutos antes**
- Fechar programas pesados (a CPU dividida deixa a IA mais lenta).
- Conferir os containers: `docker ps --format "{{.Names}} {{.Status}}"` deve mostrar `sigp_sqlserver_academic`, `sigp_academic_ai`, `sigp_n8n` e `sigp_ollama`.
- Abrir `docs/entrega-academica/apresentacao.html` no navegador e deixar na Visão geral.
- Abrir o terminal na raiz do projeto, com fonte grande (Ctrl + roda do mouse).

**5 minutos antes**
- Rodar `pwsh -File docs/entrega-academica/demo-final.ps1` e deixar parado no Enter do passo 1. O passo 0 já carregou o modelo; sem isso, a primeira análise leva cerca de 12 s.
- Não abrir `.env` nem `.env.academic` com a tela compartilhada.

## Plano B

| Se… | Faça |
|---|---|
| Um container não está no ar | `docker start sigp_sqlserver_academic sigp_academic_ai sigp_n8n sigp_ollama` e espere 30 s. |
| O n8n não responde (passos 1 a 3) | `docker restart sigp_n8n` (30 s) e enquanto isso mostre a seção Casos de teste da página. |
| A IA demora mais de 15 s | É o modelo carregando (partida a frio). Diga isso, espere e siga: a regra decide em milissegundos. |
| Algo falha e não volta | Abra `sqlserver/evidence/parte3/demo-final-saida.txt` (a saída de uma demonstração completa) e a página, que funciona sem internet. |

## Perguntas prováveis e respostas

**16 casos bastam?** Não para estimar o erro em produção, e dizemos isso. Com 95% de confiança, 16/16 é 81% a 100% e 0 falsas aprovações em 16 pode chegar a 19%. Por isso separamos a validação cega, congelada por hash (`ia/conjuntos-congelados.json`; mudar o arquivo quebra um teste). Ela é o número limpo.

**Por que o modelo não decide?** Porque medimos: sozinho, ele respondeu REVISAR nos 16 casos; o modelo base sem RAG aprovou 12 cobranças indevidas. A regra sobre evidência estruturada acerta e é auditável.

**O fine-tuning valeu a pena?** Não, e mostramos por quê: 7/16 com RAG, igual ao base. O treino tinha frases curtas; o RAG entrega o texto do contrato, que diz o que não está incluído, e o modelo leu a negação como divergência. No IA-009 ele ainda obedeceu à injeção. O próximo passo seria treinar com o texto real do RAG e com exemplos de injeção.

**E se um ataque não for detectado?** O pior caso é uma fatura cujo serviço e valor já batem com o contrato sair CONTRATADO sem a marca de revisão. O ataque não aprova valor diferente, não traz dado de outro local (credencial, RLS e RAG filtrado) e não paga nada.

**Mascaramento protege a chave fiscal?** Só na exibição: dá para inferir por filtro. Por isso a IA e quem não precisa da linha nem têm leitura na tabela, e o RLS limita o local. Não usamos Always Encrypted: a conciliação procura nota pela chave, e o banco só compara com a chave criptográfica dentro da API (a versão determinística permitiria a igualdade, mas quem usa a API continuaria vendo a chave). O TDE está ligado: o arquivo e os backups ficam criptografados (num backup sem compressão, a chave fiscal saiu de 48 ocorrências em texto puro para 0), mas ele não muda quem vê o quê numa consulta.

**O db_owner pode tudo?** Passa por cima do RLS e do mascaramento, e está nas limitações. Mas não apaga o passado: a trilha é uma tabela ledger do SQL Server 2022. Antes da mudança, numa cópia do banco, o sa reescreveu e apagou eventos sem erro; agora UPDATE e DELETE dão 37359 até para ele, e o digest guardado no Git denuncia qualquer alteração feita direto no arquivo. O que ele ainda pode é parar de registrar daqui em diante. A senha dele só existe no `.env.academic`, fora do Git.

**Por que não uma view indexada?** O SQL Server não permite view indexada sobre tabela com RLS, e ela exporia os totais de todos os locais. O resumo diário por gatilho respeita o RLS e dá a mesma resposta (0 linhas diferentes).

**Por que a consulta original ficou mais lenta que na entrega 2?** As consultas são idênticas e as leituras lógicas são as mesmas; mudou a CPU disponível na hora da medição. Por isso cada ganho é calculado dentro da mesma rodada, sempre com mediana e p95.

**Como vocês sabem que a IA não vaza dado de outro local?** Teste perfil por perfil (passo 6): a credencial define o local, o banco nega o resto, o RAG é filtrado antes da busca, e a resposta não devolve linhas do banco, só a contagem.

**Por que o pacote baixa o modelo de 3B, se o pedido era baixar pouco?** Porque medimos antes de escolher, com o critério escrito antes da medição (`ia/escolha-modelo-criterio.md`). Na 1ª medição, o 3B às vezes não terminava a resposta e a escolha seria o 0,5B. Olhando a resposta crua, achamos a causa (o campo motivo não acabava) e corrigimos no JSON Schema; na 2ª medição o 3B respondeu a todos os documentos e acertou bem mais, e pelo mesmo critério virou o padrão. A instalação leve continua disponível. A correção também foi para a produção: antes, um documento podia travar a fila por 300 s.

**O que a auditoria guarda da IA?** Quem pediu, quantas linhas leu e de qual local, as fontes citadas, a decisão, a sugestão do modelo, a versão do prompt e o hash da descrição. Se a auditoria falhar, a análise não sai (503).

**Tem segredo no repositório?** Não. Um verificador procura as chaves reais do `.env` nos fluxos do n8n e no repositório; as credenciais ficam em variáveis de ambiente.

## Onde está cada requisito

| Requisito | Documento |
|---|---|
| Casos de teste com métrica e análise das falhas | `ia/casos-de-teste-final.md` |
| Fine-tuning: base, base + RAG, ajustado, ajustado + RAG; custo e latência | `ia/finetuning/comparacao-final.md` |
| Prompt injection testado e as defesas | `ia/casos-de-teste-final.md` (bateria, validação cega, camadas) |
| Fluxo do n8n sem segredo | `ia/segredos-n8n.md` |
| Papéis e permissões com DENY justificado | `seguranca/matriz-permissoes.md` |
| Dados sensíveis (RLS e mascaramento) | `seguranca/protecao-dados-sensiveis.md` |
| Duas consultas lentas, plano e tempos | `seguranca/otimizacao-consultas.md` |
| Ataque e correção (escalonamento) | `seguranca/ataque-escalonamento.md` |
| Trilha "quem fez o quê", à prova de adulteração (ledger) | `seguranca/trilha-auditoria.md` |
| Auditoria do que a IA respondeu e a IA por perfil | `seguranca/auditoria-e-ia-por-perfil.md` |
| Histórico de falhas, correções e retestes | `historico-evolucao.md` |
| Limitações | `relatorio-limitacoes.pdf` |
