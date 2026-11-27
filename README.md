# SIGp: gestão de contas de internet de provedores (entrega acadêmica)

Projeto de Inteligência Artificial · Segurança e Otimização de Banco de Dados. Integrantes e matrículas:
[`docs/entrega-academica/identificacao.json`](docs/entrega-academica/identificacao.json).

Este repositório é o **pacote da entrega**: só o fluxo de gestão de contas de provedores, separado do sistema completo da
empresa por um script (`entrega/montar-entrega.ps1` no sistema completo). Todos os dados são fictícios.

<!-- respostas-professora:inicio -->
## Respostas aos comentários da professora

Devolutiva da Entrega 2 (Prof.ª Bruna). Seção gerada por `docs/entrega-academica/apresentacao/gerar_respostas.py` com os mesmos dados dos relatórios; os números vêm das evidências.

| Disciplina | Comentário | O que foi feito | Evidência |
|---|---|---|---|
| IA | O relatório cita a v4.2 como prompt atual, enquanto o fluxo avaliado ainda roda a v3.0. | Cada fluxo tem o seu prompt: a análise de fatura avaliada (/api/analyze) usa o v3.1 e a triagem do Gmail (WF-08/WF-10), o v4.2. A avaliação final foi feita no serviço com o mesmo prompt, modelo e busca que o pacote de entrega sobe, e um teste falha se o pacote divergir da evidência. | [`ia/prompts/CHANGELOG.md`](docs/entrega-academica/ia/prompts/CHANGELOG.md) (Qual prompt cada fluxo usa hoje) · [`ia/casos-de-teste-final.md`](docs/entrega-academica/ia/casos-de-teste-final.md) · [`tests/test_pacote_mesma_ia.py`](tests/test_pacote_mesma_ia.py) |
| IA | RAG com embeddings. | Busca por embedding (embeddinggemma, no Ollama local) escolhida por critério versionado antes da medição, entre 3 modelos e a busca híbrida: fonte certa em 13/14 paráfrases contra 7/14 da lexical, sem perder nenhum caso final (14/14) e sem documento de outro local. Ligada no sistema entregue. | [`sqlserver/evidence/parte3/rag-embeddings.json`](docs/entrega-academica/sqlserver/evidence/parte3/rag-embeddings.json) · [`ia/rag-embeddings-criterio.md`](docs/entrega-academica/ia/rag-embeddings-criterio.md) · [`ia/rag-embeddings.md`](docs/entrega-academica/ia/rag-embeddings.md) |
| IA | Mais casos de teste, incluindo fora de escopo. | 12 casos fora de escopo (outra conta, outro local, outro idioma, não é fatura), com o esperado escrito antes de rodar. A 1ª rodada achou uma falsa aprovação (fatura de outra unidade aprovada com o contrato da Agência Centro), corrigida; final 12/12, segurança 12/12. | [`ia/casos-fora-escopo.json`](docs/entrega-academica/ia/casos-fora-escopo.json) · [`ia/casos-de-teste-final.md`](docs/entrega-academica/ia/casos-de-teste-final.md) · [`ia-avaliacao-final.json`](docs/entrega-academica/sqlserver/evidence/parte3/ia-avaliacao-final.json) |
| IA | Fine-tuning medido em cenários fora do treino. | Medido nos casos finais (7/16) e nos fora de escopo (6/12), com o RAG do sistema entregue; no teste do próprio treino, 18/20. A sobreposição com os 80 exemplos de treino foi conferida caso a caso: nenhum provedor em comum; os 6 casos que usam o nome de serviço do treino saem separados. Conclusão: o ajuste não generaliza fora do treino. | [`ia/finetuning/comparacao-final.md`](docs/entrega-academica/ia/finetuning/comparacao-final.md) · [`finetuning-comparacao.json`](docs/entrega-academica/sqlserver/evidence/parte3/finetuning-comparacao.json) · [`sobreposicao-treino.json`](docs/entrega-academica/sqlserver/evidence/parte3/sobreposicao-treino.json) |
| BD | Explicar nos planos o que mudou (scan × seek, custo). | Cada operador dos planos reais lido do XML: tipo de acesso (scan ou seek), linhas lidas e devolvidas, custo próprio e da consulta, por configuração, com o porquê da mudança. | [`seguranca/otimizacao-consultas.md`](docs/entrega-academica/seguranca/otimizacao-consultas.md) (seção "O que mudou no plano") · [`evidence/parte3/otimizacao/*.sqlplan`](docs/entrega-academica/sqlserver/evidence/parte3/otimizacao/) |
| BD | Melhorar a consulta 1 (ganho ainda pequeno). | Só com índice o ganho era 1,4× (o plano mostra que sobra somar as notas da janela). Com o resumo diário (desnormalização com gatilho e RLS): 168,7 → 25,3 ms (6,7×) e 3.281 → 13 leituras lógicas, com a mesma resposta. | [`seguranca/otimizacao-consultas.md`](docs/entrega-academica/seguranca/otimizacao-consultas.md) · [`evidence/parte3/otimizacao/`](docs/entrega-academica/sqlserver/evidence/parte3/otimizacao/) |
| BD | Proteger a tabela de auditoria contra alteração. | audit.Eventos virou tabela ledger só de inserção: antes o sa reescrevia 280 e apagava 61 eventos; agora ninguém altera nem apaga (erro 37359), e a trilha é conferida contra o digest guardado fora do banco (APROVADO). | [`sqlserver/evidence/parte3/ledger-antes.txt`](docs/entrega-academica/sqlserver/evidence/parte3/ledger-antes.txt) e ledger-verificacao.json |
| IA e BD | Repositório só com a parte acadêmica, com commits de todos os integrantes. | A entrega é o repositório do pacote: só o fluxo avaliado (gestão de contas de provedores), a parte acadêmica e uma base fictícia, com instalação em um comando. É o único repositório citado nos documentos. | <https://github.com/FredsonSistema/sigp-entrega> |

## Onde está cada requisito

Conferido pelo gerador: cada documento abaixo existe no repositório da entrega; o resultado vem das evidências.

| Disciplina | Requisito | Documento | Resultado |
|---|---|---|---|
| IA | Casos de teste com métrica e análise das falhas | [`ia/casos-de-teste-final.md`](docs/entrega-academica/ia/casos-de-teste-final.md) | 16/16 e 12/12 fora de escopo; acurácia, F1, matriz e intervalo de 95% |
| IA | RAG (com embeddings) | [`ia/rag-embeddings.md`](docs/entrega-academica/ia/rag-embeddings.md) | embedding:embeddinggemma: 13/14 paráfrases |
| IA | Fine-tuning: base, base + RAG, ajustado, ajustado + RAG; custo e latência; fora do treino | [`ia/finetuning/comparacao-final.md`](docs/entrega-academica/ia/finetuning/comparacao-final.md) | 4 configurações em 3 conjuntos (finais, fora de escopo, teste do treino) |
| IA | Prompt injection testado e as defesas | [`ia/casos-de-teste-final.md`](docs/entrega-academica/ia/casos-de-teste-final.md) | bateria 13/13, validação cega 4/8, 8 camadas |
| IA | Versionamento do prompt (qual fluxo usa qual) | [`ia/prompts/CHANGELOG.md`](docs/entrega-academica/ia/prompts/CHANGELOG.md) | análise de fatura v3.1; triagem v4.2 |
| IA | Fluxo do n8n sem segredo | [`ia/segredos-n8n.md`](docs/entrega-academica/ia/segredos-n8n.md) | APROVADO |
| BD | Papéis e permissões com DENY justificado | [`seguranca/matriz-permissoes.md`](docs/entrega-academica/seguranca/matriz-permissoes.md) | 23 DENY, cada um com motivo e teste |
| BD | Dados sensíveis (RLS, mascaramento e TDE) | [`seguranca/protecao-dados-sensiveis.md`](docs/entrega-academica/seguranca/protecao-dados-sensiveis.md) | TDE: APROVADO |
| BD | Duas consultas lentas: plano (scan × seek, custo) e tempos | [`seguranca/otimizacao-consultas.md`](docs/entrega-academica/seguranca/otimizacao-consultas.md) | 6,7× e 5,1× |
| BD | Ataque e correção (escalonamento) | [`seguranca/ataque-escalonamento.md`](docs/entrega-academica/seguranca/ataque-escalonamento.md) | falha reproduzida e barrada |
| BD | Trilha 'quem fez o quê', protegida contra alteração | [`seguranca/trilha-auditoria.md`](docs/entrega-academica/seguranca/trilha-auditoria.md) | ledger: APROVADO |
| BD | Auditoria do que a IA respondeu e a IA por perfil | [`seguranca/auditoria-e-ia-por-perfil.md`](docs/entrega-academica/seguranca/auditoria-e-ia-por-perfil.md) | APROVADO |
| BD | Vulnerabilidades, restauração do backup e injeção de SQL | [`seguranca/avaliacao-vulnerabilidades.md`](docs/entrega-academica/seguranca/avaliacao-vulnerabilidades.md) | 25 regras passando, 0 falhas |
| IA e BD | Histórico de falhas, correções e retestes | [`historico-evolucao.md`](docs/entrega-academica/historico-evolucao.md) | 48 itens |
| IA e BD | Mudanças desde a Entrega 2 | [`MUDANCAS-DESDE-ENTREGA-2.md`](docs/entrega-academica/MUDANCAS-DESDE-ENTREGA-2.md) | melhorado, corrigido e inalterado |
| IA e BD | Respostas aos comentários da professora | [`README.md`](docs/entrega-academica/README.md) | 8 comentários |
| IA e BD | Relatório de limitações (até 2 páginas) | [`relatorio-limitacoes.pdf`](docs/entrega-academica/relatorio-limitacoes.pdf) | gerado das evidências |
| IA e BD | Relatório final e contribuição individual | [`relatorio-final.pdf`](docs/entrega-academica/relatorio-final.pdf) | 4 integrantes |
| IA e BD | Instalação reproduzível com base fictícia | [`GUIA-INSTALACAO.md`](docs/entrega-academica/GUIA-INSTALACAO.md) | um comando; janela própria no Windows |

<!-- respostas-professora:fim -->

## O problema

Uma empresa paga a internet de dezenas de localidades (agências, rodoviárias e garagens), a vários provedores. As faturas
chegam por e-mail, em formatos diferentes, e alguém confere cada uma contra o contrato. Isso atrasa o pagamento e deixa
passar cobrança indevida, como um IP adicional que o contrato não prevê.

O SIGp busca as faturas no Gmail, lê o PDF, associa cada fatura ao local e ao provedor, confere com o contrato e registra
tudo. **A IA ajuda, mas não decide nem paga nada:** a regra decide sobre a evidência estruturada, o banco limita o que cada
um vê e a auditoria registra quem fez o quê.

## Arquitetura

```text
Gmail ──► n8n (WF-08, a cada 5 min) ──► OCR local ──► regras do SIGp ──► Qwen local (Ollama) ──► API do SIGp
                                                                                                    │
         tela do SIGp (associação ao local e ao provedor, faturas, notas, painel da IA) ◄──────────┘

n8n (webhook) ──► API da IA ──► SQL Server (RLS por local) ──► RAG (contratos do local e do provedor)
                                   │                                │
                                   │                                └──► regra decide · Qwen 0,5B sugere
                                   └──► trilha ledger: quem pediu, o que a IA leu e o que respondeu
```

| Serviço | Para quê | Endereço |
|---|---|---|
| `sigp_web` + `sigp_api` | Tela e API do SIGp (SQLite), só com os módulos do fluxo (`SIGP_MODULOS=gestao`) | http://127.0.0.1:8000/agencias.html · :5001 |
| `sigp_n8n` | Fluxos: Gmail (WF-08), etiquetas (WF-09), alertas com IA (WF-06), erros (WF-99), IA acadêmica | http://127.0.0.1:5678 |
| `sigp_fatura_ocr` | Leitura do PDF, sem rede externa | interno |
| `sigp_ollama` | LLM local (Qwen 2.5): nenhum dado sai da máquina, sem custo por token | interno |
| `sigp_sqlserver_academic` | SQL Server 2022: RLS, mascaramento, DENY, trilha ledger, auditoria nativa | 127.0.0.1:14333 |
| `sigp_academic_ai` | API da IA: RAG + regra + modelo, com auditoria de cada resposta | http://127.0.0.1:5010 |

Todas as portas ficam em `127.0.0.1`. Nenhuma chave vem no pacote: o instalador gera todas.

## Instalar (um comando)

Num Windows 10 22H2 ou 11 sem nada instalado (8 GB de memória, 15 GB livres), abra o PowerShell e cole:

```powershell
irm https://raw.githubusercontent.com/FredsonSistema/sigp-entrega/main/instalar-sigp.ps1 | iex
```

Ou clique duas vezes em [`Instalar SIGp.cmd`](Instalar%20SIGp.cmd). O `instalar-sigp.ps1` liga o WSL 2 se faltar (a única
janela de administrador, seguida de um reinício; depois a instalação continua sozinha), instala o Docker Desktop no modo do
usuário, baixa o PowerShell 7 portátil e este pacote (sem Git) e roda o `instalar.ps1`. No fim, cria o atalho **SIGp** na
área de trabalho e abre o SIGp numa janela própria do Windows (`abrir-sigp.ps1`). Detalhes e problemas comuns: [`docs/entrega-academica/GUIA-INSTALACAO.md`](docs/entrega-academica/GUIA-INSTALACAO.md).

Com o Docker Desktop já instalado, dá para rodar só o instalador do pacote: `pwsh -File instalar.ps1`. Ele:
1. confere o Docker;
2. gera as chaves e senhas no `.env` e no `docs/entrega-academica/sqlserver/.env.academic` (ignorados pelo Git; os valores não aparecem na tela);
3. sobe os containers;
4. cria o banco acadêmico (schema, RLS, mascaramento, trilha ledger, usuários da IA e auditoria);
5. baixa os modelos locais;
6. importa os workflows no n8n e publica o da IA acadêmica;
7. grava a base fictícia (6 locais, 3 provedores e 3 faturas para associar);
8. cria o seu acesso (`primeiro-acesso.ps1`): pede nome, usuário, e-mail e uma senha que vale para a tela do SIGp e para o
   n8n. A senha é digitada por você e não aparece na tela, não vai para a área de transferência nem para arquivo.

### Qual modelo de IA é baixado

Por padrão, o **Qwen 2.5 0,5B (~400 MB)** para a IA acadêmica e o **3B (~1,9 GB)** para a triagem do Gmail. A escolha foi
**medida antes de decidir**, com um critério escrito e versionado antes da medição
([`escolha-modelo-criterio.md`](docs/entrega-academica/ia/escolha-modelo-criterio.md); resultado em
[`escolha-modelo-triagem.md`](docs/entrega-academica/ia/escolha-modelo-triagem.md)):
- na 1ª medição, o 3B às vezes não terminava a resposta (o campo `motivo` não acabava) e o pacote ficaria só com o 0,5B;
- a causa foi corrigida no JSON Schema do WF-08 (`maxLength` em cada texto e limite de tokens); na 2ª medição o 3B respondeu
  a todos os documentos e acertou bem mais que o 0,5B, então, pelo mesmo critério, ele passou a ser o padrão;
- o 1,5B não terminou nenhuma resposta válida.

Nada é pago nem ignorado por causa da IA: a regra, a linha digitável do boleto e a revisão humana decidem. Instalação leve
(~1,5 GB a menos, triagem mais fraca): `pwsh -File instalar.ps1 -ModeloTriagem qwen2.5:0.5b`.

Pode rodar de novo: o que já existe é mantido. Opções: `-ModeloTriagem qwen2.5:3b`, `-SemBaseFicticia`, `-ComVolume`
(carrega as 100.020 notas sintéticas do benchmark).

## Usar

1. **Tela:** clique no atalho **SIGp**, que abre a janela própria do SIGp no Windows (`abrir-sigp.ps1`; também dá para abrir http://127.0.0.1:8000/agencias.html no navegador) e entre com o usuário e a senha que
   você criou. Em **Notas recebidas** estão as 3 faturas fictícias: associe cada uma ao local e ao provedor e veja a
   comparação com o contrato. Fatura que não chega por e-mail: **Adicionar documento** (PDF e/ou XML), que passa pela
   mesma leitura e IA do e-mail (WF-10).
2. **IA acadêmica:** `POST http://127.0.0.1:5678/webhook/sigp-academic-ai` com a fatura no corpo, por exemplo
   `{"provider":"Conecta Alfa Fictícia","description":"IP adicional mensal","amount":"35.00"}`. Resposta: decisão da regra,
   fontes do contrato, sugestão do modelo e `automatic_payment: false`.
3. **Assistente da IA** (Análise › Assistente): perguntas sobre contas e locais; cada 👍/👎 e cada termo ensinado
   vira material de treino da IA (exportável em JSONL).
4. **Demonstração completa** (IA, ataques, trilha, perfis, consultas): `pwsh -File docs/entrega-academica/demo-final.ps1`.
   Para ela e para os testes de avaliação: **Python 3.12** e **sqlcmd** (`winget install sqlcmd`).

### Configurar o fluxo (Gmail, alertas, chaves e assistente)

O instalador já liga os serviços entre si (endereços, chaves e senhas) e cria o seu acesso. Para buscar faturas no
Gmail, falta conectar a conta Google no n8n (login no Google: não dá para automatizar), conferir os remetentes e rodar
`pwsh -File ligar-gmail.ps1`. Passo a passo, com o mapa de endereços, chaves, alertas, Telegram/WhatsApp e o assistente
da IA (que junta o material de treino): [`docs/entrega-academica/GUIA-CONFIGURACAO.md`](docs/entrega-academica/GUIA-CONFIGURACAO.md).
Sem o Gmail, todo o resto funciona com a base fictícia.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `instalar-sigp.ps1`, `Instalar SIGp.cmd` | Instalação numa máquina sem nada (WSL, Docker, PowerShell 7 e o pacote) |
| `instalar.ps1`, `primeiro-acesso.ps1`, `ligar-gmail.ps1`, `docker-compose.yml` | Instalação do pacote, criação do seu acesso, fluxos do Gmail e os serviços |
| `backend/` | API do SIGp (Flask): locais, notas recebidas, associação, faturas, perfis, cofre de chaves, métricas da IA |
| `agencias.html`, `frontend/`, `web/` | Tela do SIGp |
| `ocr/` | Serviço de OCR do PDF |
| `n8n/workflows/` | Workflows importados pelo instalador; `n8n/wf08`, `n8n/wf06` e `n8n/lib` são as fontes deles |
| `docs/entrega-academica/` | Tudo da entrega: relatórios, IA (`ia/`), segurança (`seguranca/`), SQL Server (`sqlserver/`), evidências e a página de resultados |
| `entrega/base_ficticia.py` | Base de demonstração (locais, provedores e faturas inventados) |
| `tests/` | Testes unitários (`python -m unittest discover -s tests`) e dos workflows |

## Documentos da entrega

- Mudanças desde a Entrega 2: [`docs/entrega-academica/MUDANCAS-DESDE-ENTREGA-2.md`](docs/entrega-academica/MUDANCAS-DESDE-ENTREGA-2.md)
- Resultados interativos (abre sem internet): [`docs/entrega-academica/apresentacao.html`](docs/entrega-academica/apresentacao.html)
- Relatório de limitações: [`docs/entrega-academica/relatorio-limitacoes.pdf`](docs/entrega-academica/relatorio-limitacoes.pdf)
- Índice de todos os documentos e evidências: [`docs/entrega-academica/README.md`](docs/entrega-academica/README.md)
- Histórico de cada falha, correção e reteste: [`docs/entrega-academica/historico-evolucao.md`](docs/entrega-academica/historico-evolucao.md)
