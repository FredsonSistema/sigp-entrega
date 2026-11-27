# Mudanças desde a Entrega 2

Gerado por [`apresentacao/gerar_mudancas.py`](apresentacao/gerar_mudancas.py) com os mesmos dados dos relatórios; nenhum número foi digitado à mão. "Antes" é a primeira medição desta etapa, feita no sistema como estava na Entrega 2 (a avaliação da Entrega 2, de 2026-11-14, usava 5 casos e o prompt v3.0); "depois" é a medição final, no sistema entregue. O detalhe de cada item está no documento da última coluna e em [`historico-evolucao.md`](historico-evolucao.md).

## Mudança de interface: da web para uma janela do Windows

Na Entrega 2 o SIGp abria como uma aba do navegador. Agora o atalho **SIGp** da área de trabalho abre o sistema numa **janela própria do Windows**: sem barra de endereço e sem abas, com título e ícone próprios na barra de tarefas. É o Microsoft Edge em modo aplicativo (`--app`), com um perfil separado, que já vem no Windows 10 e 11. Se o computador foi reiniciado, o atalho liga o Docker e os containers e espera a tela responder. As telas são as mesmas: mudou onde elas abrem, não o que fazem. Tudo continua local (http://127.0.0.1:8000). Código: [`abrir-sigp.ps1`](../../abrir-sigp.ps1), na raiz do repositório da entrega; o instalador cria o atalho (`SIGp.lnk`). Teste e reteste: H-48 no histórico.

## O que melhorou

| Tema | Antes | Depois | Evidência |
|---|---|---|---|
| Interface | tela numa aba do navegador | janela própria do Windows, aberta pelo atalho SIGp (Edge em modo aplicativo, sem barra de endereço nem abas); liga os containers se o computador foi reiniciado | [`abrir-sigp.ps1`](../../abrir-sigp.ps1) · [`historico-evolucao.md`](historico-evolucao.md) (H-48) |
| IA: decisão nos 16 casos | 12/16, falsa aprovação em IA-015 | 16/16, nenhuma falsa aprovação | [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) |
| IA: casos fora de escopo (novos) | não havia | 12/12, depois de corrigir a aprovação de fatura de outra unidade | [`ia/casos-fora-escopo.json`](ia/casos-fora-escopo.json) · [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) |
| IA: RAG (fonte certa nas paráfrases) | busca por palavras, 7/14 | embedding embeddinggemma, 13/14 | [`ia/rag-embeddings.md`](ia/rag-embeddings.md) |
| IA: tempo da análise de uma fatura nova | 31,3 s (prompt 3.0) | 3,1 s (prompt 3.1) | [`ia/finetuning/comparacao-final.md`](ia/finetuning/comparacao-final.md) |
| IA: prompt injection detectado | 2/13 na bateria | 13/13 na bateria; 4/8 na validação cega (nova, congelada) | [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) |
| IA: fine-tuning | medido só no teste do próprio treino | medido fora do treino: 7/16 nos casos finais e 6/12 fora de escopo (não generaliza) | [`ia/finetuning/comparacao-final.md`](ia/finetuning/comparacao-final.md) |
| BD: consulta 1 (mediana) | 168,7 ms, 3.281 leituras | 25,3 ms, 13 leituras (resumo diário) | [`seguranca/otimizacao-consultas.md`](seguranca/otimizacao-consultas.md) |
| BD: consulta 2 (mediana) | 54,4 ms, 4.956 leituras | 10,7 ms, 1.012 leituras (índice filtrado) | [`seguranca/otimizacao-consultas.md`](seguranca/otimizacao-consultas.md) |
| BD: escalonamento de privilégio | 2 ataques passaram | 9 verificações OK, todos barrados | [`seguranca/ataque-escalonamento.md`](seguranca/ataque-escalonamento.md) |
| BD: trilha de auditoria | 9 falhas | 12/12 OK | [`seguranca/trilha-auditoria.md`](seguranca/trilha-auditoria.md) |
| BD: trilha à prova de alteração | o sa reescrevia 280 e apagava 61 eventos | tabela ledger só de inserção; verificação APROVADO | [`seguranca/trilha-auditoria.md`](seguranca/trilha-auditoria.md) |
| BD: criptografia do arquivo e do backup (TDE) | chave fiscal 48 vezes em texto no backup | 0 vezes; restauração em outro servidor: APROVADO | [`seguranca/restauracao-tde.md`](seguranca/restauracao-tde.md) |
| BD: avaliação de vulnerabilidades (27 regras) | 21 passando, 4 falhas | 25 passando, 0 falhas, 2 riscos aceitos com justificativa | [`seguranca/avaliacao-vulnerabilidades.md`](seguranca/avaliacao-vulnerabilidades.md) |
| BD: injeção de SQL | não testada | API, procedimentos e primitiva do banco: APROVADO | [`seguranca/injecao-sql.md`](seguranca/injecao-sql.md) |
| Segredos nos fluxos do n8n | 1 modelo com chave literal | APROVADO | [`ia/segredos-n8n.md`](ia/segredos-n8n.md) |
| Instalação | script do ambiente acadêmico e passos do guia, com o Docker já instalado | um comando (Instalar SIGp.cmd): Docker, chaves, banco, modelos, workflows, base fictícia e o acesso | [`GUIA-INSTALACAO.md`](GUIA-INSTALACAO.md) |
| Entrada manual de notas (função nova) | só por e-mail | PDF e/ou XML enviados pela tela passam pela mesma leitura e IA (WF-10) | [`historico-evolucao.md`](historico-evolucao.md) (H-38) |

## O que foi corrigido

Cada linha é um teste que **reprovou** na primeira execução, foi corrigido e retestado (42 itens). O texto completo (falha, correção, reteste e commit) está em [`historico-evolucao.md`](historico-evolucao.md).

| # | Data | Área | O que foi testado | Reteste | Commit |
|---|---|---|---|---|---|
| H-01 | 20/11 | Segurança | Escalonamento horizontal: operador do LOC-001 grava/move nota para o LOC-002 | APROVADO (erro 33504) | `7b243cf` |
| H-02 | 20/11 | Segurança (teste) | Primeira versão do teste de escalonamento | Falha reproduzida e barrada | `7b243cf` |
| H-03 | 20/11 | Segurança (teste) | Ataques depois de uma personificação negada | APROVADO com os códigos certos | `7b243cf` |
| H-04 | 20/11 | Instalação | `01_schema_seed.sql` no banco com índice filtrado | Roda sem erro | `7b243cf` |
| H-05 | 20/11 | IA (teste) | Teste unitário do tempo limite do Ollama | 21/21 passam | `a12e37f` |
| H-06 | 20/11 | Integração | Auditoria registra o que a IA respondeu | APROVADO | `a12e37f` |
| H-07 | 20/11 | Integração (teste) | Leitura da trilha pelo teste | Texto certo | `a12e37f` |
| H-08 | 20/11 | IA | Injeção em português (IA-009) e no XML da NF-e (IA-015) | APROVADO (REVISAR) | `774d620` |
| H-09 | 20/11 | IA | Valor com vírgula decimal (IA-011) | APROVADO | `774d620` |
| H-10 | 20/11 | IA | Provedor com razão social "LTDA" (IA-013) | APROVADO | `774d620` |
| H-11 | 20/11 | IA | Bateria de 13 ataques de prompt injection | 13/13 | `774d620` |
| H-13 | 20/11 | IA (teste) | Varredura de vazamento no IA-016 | Sem vazamento | `774d620` |
| H-14 | 20/11 | IA (teste) | Primeira análise depois de reiniciar o serviço | 16/16 respondidas | `774d620` |
| H-16 | 20/11 | IA (medição) | Latência do sistema no ar | 31,3 s (fatura nova) | `ddaefc9` |
| H-17 | 20/11 | IA (medição) | Carga de CPU da máquina | 44% registrado | `ddaefc9` |
| H-19 | 20/11 | Otimização | Consulta 1 (total por local, provedor e mês) | 168,7 → 25,3 ms | `a09fcf7` |
| H-20 | 20/11 | Otimização (teste) | Testes do resumo diário | APROVADO | `a09fcf7` |
| H-21 | 20/11 | Segurança | Trilha de auditoria: quem gravou, alterou ou apagou notas; trilha protegida | APROVADO (12/12) | `040a806` |
| H-22 | 20/11 | Banco | Acentos nos dados e nas mensagens do banco | 0 linhas quebradas | `040a806` |
| H-23 | 20/11 | Segurança (teste) | Primeiras execuções do teste da trilha e da conferência de acentos | Resultado certo | `040a806` |
| H-24 | 20/11 | Segurança (teste) | Matriz de permissões gerada do banco e prova do DENY | APROVADO (5/5) | `79a37d5` |
| H-25 | 20/11 | Integração | Nenhum segredo nos fluxos do n8n exportados | APROVADO (0 falhas em 35 arquivos) | `79a37d5` |
| H-26 | 21/11 | IA (desempenho) | Latência da análise de uma fatura nova (revisão externa: "35 s na demonstração") | APROVADO (3,1 s, p95 4,8 s; decisões iguais) | `31e1e7d` |
| H-27 | 21/11 | Segurança | Trilha de auditoria à prova de adulteração (revisão externa: "quem tem db_owner ainda altera") | APROVADO (UPDATE e DELETE 37359, TRUNCATE 13545, ledger verificada, digest falso recusado) | `e0e6383` |
| H-30 | 21/11 | IA (medição) | Primeira rodada da comparação de modelos | Latência sem o tempo de carga | `ebbff13` |
| H-31 | 21/11 | Segurança | Dados pessoais no código do pacote | Nenhum achado | `ebbff13` |
| H-32 | 21/11 | Segurança | Criptografia em repouso (limitação do relatório: "um backup roubado é legível") | APROVADO (0 ocorrências; 02, 08, 14, IA por perfil e ledger passam) | `e05be28` |
| H-33 | 21/11 | IA (produção) | Resposta da triagem do WF-08 que não terminava | APROVADO (3B 10/10 respostas válidas, média 36,4 s, p95 56,7 s; leituras automáticas em produção com sucesso) | `190e46b` |
| H-34 | 21/11 | Repositório | Limpeza dos arquivos das entregas 1 e 2 (44 arquivos e o `tokenizer.json` de 11 MB): nenhuma referência quebrada e nenhum número sem evidência | APROVADO (252 testes de unidade, 21 da IA acadêmica, 22/22 da página de apresentação; verificador de links sem alvo quebrado além dos falsos positivos de nome… | `9cc682f` |
| H-35 | 21/11 | Segurança (repositório) | Dados de documentos fiscais reais nos testes (procura por todo CNPJ com dígito verificador válido nos arquivos versionados) | APROVADO (a procura só acha 11.222.333/0001-81, exemplo de documentação, e 00.000.000/0001-91, do Banco do Brasil; 252 testes de unidade, 28 dos extratores no… | `5524557` |
| H-36 | 22/11 | Instalação | Criação do acesso no fim da instalação, com a senha digitada pela pessoa (sem mostrar nem copiar), contra uma API do SIGp e um n8n 2.43.4 descartáveis, no PowerShell 5.1 e no 7 | APROVADO (10/10 nos dois PowerShell: senha fraca recusada sem criar nada pela metade, senha e chave fora da saída e de todo arquivo, login no SIGp e no n8n com… | `iex` até baixar o pacote e o PowerShell 7 portátil, com o PATH e os dados da máquina intactos)` |
| H-37 | 23/11 | Configuração do pacote | Revisão de cada configuração e autenticação do fluxo, para escrever o guia de configuração (endereços, chaves, Gmail, alertas, notificações, assistente) | APROVADO (num n8n 2.43.4 descartável, 7/7: credencial criada uma vez e preservada na 2ª instalação, recusa sem conexão, liga e desliga os 5 fluxos, token fora… | `7c344f9` |
| H-38 | 23/11 | Funcionalidade nova | Entrada manual em Notas recebidas: fatura PDF e/ou XML enviados pela tela passam pela mesma leitura e IA do e-mail (WF-10), sem etiqueta no Gmail, e a cópia que chegar por e-mail vem com o local da entrada manual | APROVADO (11 testes de unidade da entrada manual, 23 do WF-10 em node, 14/14 na tela com a API de teste e um n8n descartável: a IA leu a fatura fictícia em 104… | `421e4c9` |
| H-39 | 24/11 | Instalação (teste limpo) | Instalação em outro computador, com o Docker já instalado, pelo comando de uma linha | Função de novas tentativas testada com comandos que falham de propósito (4/4: cai 2 vezes e segue; sempre cai e para em 5 com a explicação; de primeira, 1… | `49bbbec` |
| H-40 | 24/11 | Instalação (teste limpo) | Segunda tentativa em outro computador: banco acadêmico num SQL Server novo | APROVADO num SQL Server 2022 novo e descartável: 01, provisão, 01, auditoria e TDE (AES 256, chave fiscal 0 vez no backup), login da IA com o usuário contido;… | `d1a2c21` |
| H-41 | 25/11 | Segurança do banco | Avaliação de vulnerabilidades do SQL Server (27 regras no estilo do SQL Vulnerability Assessment e do CIS Benchmark: superfície de ataque, logins, permissões, dados, trilha e rede) | APROVADO: 21 → 25 regras passando, 4 → 0 falhas (num SQL Server novo e no banco acadêmico); depois do TLS obrigatório, a IA entra com o usuário contido, a… | `416d3d9` |
| H-43 | 25/11 | Segurança do banco | Injeção de SQL em três níveis: 10 ataques pela API da IA, 6 direto nos procedimentos com o usuário da IA, e a primitiva que a API usa para falar com o banco | APROVADO (10/10 e 6/6 sem efeito, banco igual, nenhuma senha na trilha, 0 procedimentos com SQL dinâmico, `$(SIGP_AI_API_KEY)` e `$(HOME)` ficam como texto; 21… | `5d737aa` |
| H-44 | 26/11 | IA (RAG) | RAG com embeddings, pedido da Prof.ª Bruna: lexical × 3 modelos de embedding (nomic-embed-text, embeddinggemma, bge-m3) × híbrido RRF, em 14 paráfrases e nos casos finais, com o critério versionado antes de medir… | APROVADO ([`ia/rag-embeddings.md`](ia/rag-embeddings.md): casos finais 14/14 como a lexical, nenhum documento fora do escopo; avaliação completa 16/16, 0… | `4a51c35` |
| H-45 | 26/11 | Pacote de entrega | O pacote roda a mesma IA que foi avaliada? (prompt, modelo de texto, modelo de embedding e perfil do `/health` registrado na avaliação, contra o `docker-compose.yml` do pacote, o ambiente acadêmico, o código e o instalador) | APROVADO (4/4; sem a correção, o teste do pacote falha) | `de896d2` |
| H-46 | 26/11 | IA (casos de teste) | 12 casos fora de escopo, pedido da Prof.ª Bruna: outra conta (energia, água, aluguel, telefonia móvel, software, compra de equipamento), outro local, outro idioma e documentos que não são fatura, com o esperado (REVISAR) escrito… | APROVADO (avaliação final: fora de escopo 12/12, segurança 12/12, casos finais 16/16, injeção 13/13, validação cega igual (4/8); fine-tuning medido fora do… | `f67551b` |
| H-47 | 26/11 | Documentos da entrega | O que os relatórios dizem é o que foi avaliado e o que vai no pacote? (pedido da Prof.ª Bruna: o relatório citava um prompt e o fluxo avaliado rodava outro) | APROVADO (relatórios e página gerados de novo, relatório de limitações com 2 páginas, teste da página 24/24, `tests/test_pacote_mesma_ia.py` 4/4) | `f67551b` |
| H-48 | 26/11 | Interface | O SIGp numa janela própria do Windows, em vez de uma aba do navegador: atalho na área de trabalho (`abrir-sigp.ps1`, Edge em modo aplicativo com perfil separado, ícone desenhado na instalação), que liga os containers se o… | APROVADO (no PowerShell 5.1: atalho com o ícone, a janela abriu com o título do SIGp, sem barra de endereço, num processo do Edge com `--app` e perfil próprio;… | `ce01b8d` |

## O que permaneceu inalterado

| O quê | Como está | Onde conferir |
|---|---|---|
| Quem decide | a regra sobre a evidência estruturada (`structured_evidence_rules_v1` na Entrega 2 e hoje); o modelo só sugere e não tem autoridade | [`sqlserver/evidence/parte2/ai-test-results.json`](sqlserver/evidence/parte2/ai-test-results.json) · [`ia/app.py`](ia/app.py) |
| Modelo da análise de fatura | qwen2.5:0.5b no Ollama local, na Entrega 2 e hoje (qwen2.5:0.5b) | [`sqlserver/evidence/parte2/ai-test-results.json`](sqlserver/evidence/parte2/ai-test-results.json) · [`ia-avaliacao-final.json`](sqlserver/evidence/parte3/ia-avaliacao-final.json) |
| Pagamento | nenhum pagamento automático (automatic_payment sempre falso) | [`ia/app.py`](ia/app.py) |
| Escopo | o local vem da credencial do serviço, não do pedido; RLS por local no banco | [`sqlserver/README.md`](sqlserver/README.md) |
| Adaptador LoRA | o mesmo da Entrega 2 (não foi treinado de novo; só medido de novo); último commit do arquivo: 2026-11-14 | [`ia/finetuning/output/qwen2.5-0.5b-lora/adapter_model.safetensors`](ia/finetuning/output/qwen2.5-0.5b-lora/adapter_model.safetensors) |
| Corpus do RAG | os mesmos 20 documentos fictícios (mudou a forma de buscar, não o conteúdo); último commit do arquivo: 2026-11-14 | [`ia/rag_documents.json`](ia/rag_documents.json) |
| Validação cega da injeção | congelada por SHA-256 e nunca usada para ajustar; o resultado (4/8) é relatado como saiu; último commit do arquivo: 2026-11-20 | [`ia/injecao-validacao.json`](ia/injecao-validacao.json) |
| Regras de competência e vencimento | as regras do SIGp que definem a competência e o vencimento das notas não mudaram nesta etapa (a regra de decisão da IA ganhou uma verificação, H-46) | [`historico-evolucao.md`](historico-evolucao.md) |
| Telas | as mesmas telas do SIGp; mudou só onde elas abrem (janela própria em vez de aba do navegador) | [`abrir-sigp.ps1`](../../abrir-sigp.ps1) |
| Dados | base 100% fictícia no pacote e 100.020 notas sintéticas no banco acadêmico; nenhum dado real | [`entrega/base_ficticia.py`](../../entrega/base_ficticia.py) |
| Triagem do Gmail | prompt v4.2 (WF-08/WF-10); só a resposta sem fim foi corrigida (maxLength e limite de tokens) | [`ia/escolha-modelo-triagem.md`](ia/escolha-modelo-triagem.md) |

## Respostas aos comentários da professora

A tabela com uma linha por comentário da devolutiva da Entrega 2 está no [`README.md`](README.md) e no [`relatorio-final.pdf`](relatorio-final.pdf).
