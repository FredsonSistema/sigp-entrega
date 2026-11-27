# Histórico de evolução — entrega final

Registro de cada teste que **reprovou**: qual foi a falha, a causa, a correção e o **reteste**. Também registra os erros dos
nossos próprios testes e medições (falso positivo, falso negativo, número otimista), porque um teste errado esconde uma
falha real. O resumo do que mudou desde a Entrega 2 (melhorado, corrigido e inalterado) está em [`MUDANCAS-DESDE-ENTREGA-2.md`](MUDANCAS-DESDE-ENTREGA-2.md).

Convenção: **REPROVADO** = o sistema falhou; **ERRO DO TESTE** = o teste ou a medição estava errado e foi corrigido antes
de valer como evidência; **LIMITAÇÃO** = falha conhecida, mantida de propósito e documentada. Toda evidência citada está
no repositório.

## Resumo

| # | Data | Área | O que foi testado | 1ª execução | Correção | Reteste | Commit |
|---|---|---|---|---|---|---|---|
| H-01 | 20/11 | Segurança | Escalonamento horizontal: operador do LOC-001 grava/move nota para o LOC-002 | **REPROVADO** (ataque passou) | Predicados BLOCK na RLS | APROVADO (erro 33504) | `7b243cf` |
| H-02 | 20/11 | Segurança (teste) | Primeira versão do teste de escalonamento | ERRO DO TESTE (atacante tinha escopo nos 3 locais) | Operador de teste com escopo só no LOC-001 | Falha reproduzida e barrada | `7b243cf` |
| H-03 | 20/11 | Segurança (teste) | Ataques depois de uma personificação negada | ERRO DO TESTE (todos "barrados" por erro 3930) | Só erros de permissão contam como barrado | APROVADO com os códigos certos | `7b243cf` |
| H-04 | 20/11 | Instalação | `01_schema_seed.sql` no banco com índice filtrado | **REPROVADO** (erro 1934) | `setup-academic.ps1` passa `-I` | Roda sem erro | `7b243cf` |
| H-05 | 20/11 | IA (teste) | Teste unitário do tempo limite do Ollama | **REPROVADO** (esperava 120 s; o serviço usa 140 s) | Teste lê o valor do módulo | 21/21 passam | `a12e37f` |
| H-06 | 20/11 | Integração | Auditoria registra o que a IA respondeu | **REPROVADO** (requisito não atendido) | `ai.usp_log_response`, falha fechada | APROVADO | `a12e37f` |
| H-07 | 20/11 | Integração (teste) | Leitura da trilha pelo teste | ERRO DO TESTE (acentos ilegíveis) | `sqlcmd -f 65001` | Texto certo | `a12e37f` |
| H-08 | 20/11 | IA | Injeção em português (IA-009) e no XML da NF-e (IA-015) | **REPROVADO** (IA-015: falsa aprovação) | Detector com famílias de ataque em PT e EN | APROVADO (REVISAR) | `774d620` |
| H-09 | 20/11 | IA | Valor com vírgula decimal (IA-011) | **REPROVADO** (HTTP 400) | `_parse_amount` | APROVADO | `774d620` |
| H-10 | 20/11 | IA | Provedor com razão social "LTDA" (IA-013) | **REPROVADO** (provedor desconhecido) | `_provider_key` | APROVADO | `774d620` |
| H-11 | 20/11 | IA | Bateria de 13 ataques de prompt injection | **REPROVADO** (2/13 detectados) | Mesmo detector de H-08 | 13/13 | `774d620` |
| H-12 | 20/11 | IA | Validação cega: 8 ataques escritos depois da correção | 4/8 detectados | Nenhuma, de propósito | — | LIMITAÇÃO |
| H-13 | 20/11 | IA (teste) | Varredura de vazamento no IA-016 | ERRO DO TESTE (falso alarme) | Ignorar o `provider_id` que o próprio cliente enviou | Sem vazamento | `774d620` |
| H-14 | 20/11 | IA (teste) | Primeira análise depois de reiniciar o serviço | ERRO DO TESTE (503 por modelo frio) | Chamada de aquecimento, fora da conta | 16/16 respondidas | `774d620` |
| H-15 | 20/11 | IA | Revisão do detector antes de publicar | 4 padrões marcariam faturas legítimas | Padrões restritos e 8 controles legítimos nos testes | 0 falsos positivos | `774d620` |
| H-16 | 20/11 | IA (medição) | Latência do sistema no ar | ERRO DO TESTE (0,8 s otimista, por cache) | Prompt novo a cada chamada | 31,3 s (fatura nova) | `ddaefc9` |
| H-17 | 20/11 | IA (medição) | Carga de CPU da máquina | ERRO DO TESTE (0,0%) | Contador com o nome em português | 44% registrado | `ddaefc9` |
| H-18 | 20/11 | IA | Fine-tuning nos casos reais (4 configurações) | Ajuste não compensou (7/16) | Nenhuma: é resultado | — | LIMITAÇÃO |
| H-19 | 20/11 | Otimização | Consulta 1 (total por local, provedor e mês) | **REPROVADO** (índice só tirou 20%) | Desnormalização: resumo diário com gatilho e RLS | 168,7 → 25,3 ms | `a09fcf7` |
| H-20 | 20/11 | Otimização (teste) | Testes do resumo diário | ERRO DO TESTE (abortou com 3930; depois esperado escrito errado) | Erro guardado no CATCH; texto do esperado | APROVADO | `a09fcf7` |
| H-21 | 20/11 | Segurança | Trilha de auditoria: quem gravou, alterou ou apagou notas; trilha protegida | **REPROVADO** (9 falhas: nada registrado; operador forjava evento) | Gatilho de auditoria, SQL Server Audit e DENY INSERT na trilha | APROVADO (12/12) | `040a806` |
| H-22 | 20/11 | Banco | Acentos nos dados e nas mensagens do banco | **REPROVADO** (acentos trocados, "Agência" gravada como "AgÃªncia", em 200 mil linhas e nas mensagens) | Marca UTF-8 nos scripts, `-f 65001` no setup e reparo dos dados | 0 linhas quebradas | `040a806` |
| H-23 | 20/11 | Segurança (teste) | Primeiras execuções do teste da trilha e da conferência de acentos | ERRO DO TESTE (coluna curta descartou o T1b; conferência sem diferenciar maiúsculas) | Colunas maiores; comparação binária | Resultado certo | `040a806` |
| H-24 | 20/11 | Segurança (teste) | Matriz de permissões gerada do banco e prova do DENY | ERRO DO TESTE (controle exigia leitura; "não" ilegível) | Controle sem WHERE; saída do sqlcmd em arquivo | APROVADO (5/5) | `79a37d5` |
| H-25 | 20/11 | Integração | Nenhum segredo nos fluxos do n8n exportados | **REPROVADO** (cabeçalho `apikey` literal num modelo) | Modelo usa `$env`; texto de exemplo vira aviso | APROVADO (0 falhas em 35 arquivos) | `79a37d5` |
| H-26 | 21/11 | IA (desempenho) | Latência da análise de uma fatura nova (revisão externa: "35 s na demonstração") | **REPROVADO** (31,3 s em média; dois terços do prompt eram 20 linhas de contexto sem uso) | Prompt 3.1: 3 linhas de contexto, 3 documentos ao modelo, fatura por último | APROVADO (3,1 s, p95 4,8 s; decisões iguais) | `31e1e7d` |
| H-27 | 21/11 | Segurança | Trilha de auditoria à prova de adulteração (revisão externa: "quem tem db_owner ainda altera") | **REPROVADO** (numa cópia do backup, o sa reescreveu 280 eventos e apagou 61 sem erro) | `audit.Eventos` como ledger somente inclusão; digest guardado no Git | APROVADO (UPDATE e DELETE 37359, TRUNCATE 13545, ledger verificada, digest falso recusado) | `e0e6383` |
| H-28 | 21/11 | Segurança (teste) | `08_ataque_escalonamento.sql` depois da ledger | Ajuste do teste: E4 e E5 deram ERRO INESPERADO 37359 | 37359 entra na lista de erros que contam como barrado | APROVADO | `e0e6383` |
| H-29 | 21/11 | IA (modelo) | Modelo da triagem do Gmail no pacote da entrega (pedido: baixar pouco sem perder a classificação) | LIMITAÇÃO: nenhum modelo passou no critério fixado antes (0,5B com 2 erros graves; 1,5B sem resposta válida; 3B sem resposta em parte dos documentos) | 1ª aplicação: opção D (0,5B). Depois da correção do H-33, pelo mesmo critério: opção C (3B por padrão, 0,5B opcional) | Escolha documentada | `ebbff13` |
| H-30 | 21/11 | IA (medição) | Primeira rodada da comparação de modelos | ERRO DO TESTE (modelos intercalados recarregavam o modelo a cada pedido) | Um modelo de cada vez, variantes intercaladas | Latência sem o tempo de carga | `ebbff13` |
| H-31 | 21/11 | Segurança | Dados pessoais no código do pacote | **REPROVADO** (telefone e nome reais num comentário de `importar-csv.js`) | Trocados por valores fictícios; o gerador do pacote recusa segredos e e-mails pessoais | Nenhum achado | `ebbff13` |
| H-32 | 21/11 | Segurança | Criptografia em repouso (limitação do relatório: "um backup roubado é legível") | **REPROVADO** (backup sem compressão com a chave fiscal em texto puro 48 vezes) | TDE AES-256; certificado exportado para fora do volume do banco e do Git | APROVADO (0 ocorrências; 02, 08, 14, IA por perfil e ledger passam) | `e05be28` |
| H-33 | 21/11 | IA (produção) | Resposta da triagem do WF-08 que não terminava | **REPROVADO** (3B: 3 de 9 documentos sem resposta em 300 s; o campo motivo chegava a 700 tokens) | `maxLength` em cada texto do JSON Schema e `num_predict = 400`; WF-08 republicado em produção | APROVADO (3B 10/10 respostas válidas, média 36,4 s, p95 56,7 s; leituras automáticas em produção com sucesso) | `190e46b` |
| H-34 | 21/11 | Repositório | Limpeza dos arquivos das entregas 1 e 2 (44 arquivos e o `tokenizer.json` de 11 MB): nenhuma referência quebrada e nenhum número sem evidência | **REPROVADO** (antes de apagar: 12 arquivos ainda citavam os removidos, entre eles o teste `test_academic_ai.py`, o setup e o README; os documentos finais comparam com 5 arquivos da Entrega 2; e o README principal tinha um link para uma fatura que já não existia) | Referências trocadas pelos equivalentes finais (`avaliar_ia.py`, `testar_ia_perfis.py`, `benchmark-final.ps1`); o teste lê os 5 primeiros casos de `casos-finais.json`; ficaram em `evidence/parte2/` só os 5 arquivos que os documentos finais citam; READMEs reescritos para a entrega final e o pacote `sigp-entrega` | APROVADO (252 testes de unidade, 21 da IA acadêmica, 22/22 da página de apresentação; verificador de links sem alvo quebrado além dos falsos positivos de nome com espaço) | `9cc682f` |
| H-35 | 21/11 | Segurança (repositório) | Dados de documentos fiscais reais nos testes (procura por todo CNPJ com dígito verificador válido nos arquivos versionados) | **REPROVADO** (9 CNPJs reais em 9 arquivos de teste, inclusive no pacote: chaves de acesso completas de notas reais, os CNPJs das empresas usados como senha dos PDFs, inscrição estadual, linha digitável de boleto, endereço e telefone de provedor) | Trocados por valores fictícios: CNPJs com dígito verificador inválido de propósito (não podem ser de empresa real); a chave de 44 dígitos que o extrator confere ganhou o DV módulo 11 recalculado; o teste do DV errado continua com um dígito errado | APROVADO (a procura só acha 11.222.333/0001-81, exemplo de documentação, e 00.000.000/0001-91, do Banco do Brasil; 252 testes de unidade, 28 dos extratores no Node, testes do WF-08 no n8n) | `5524557` |
| H-36 | 22/11 | Instalação | Criação do acesso no fim da instalação, com a senha digitada pela pessoa (sem mostrar nem copiar), contra uma API do SIGp e um n8n 2.43.4 descartáveis, no PowerShell 5.1 e no 7 | **REPROVADO** (o SIGp respondia "chave do servidor incorreta" com a chave certa: a função que montava o corpo devolvia o byte[] desmontado, e o corpo chegava estragado). No mesmo teste: a pasta de downloads escolhida para o instalador, `%LOCALAPPDATA%\SIGp`, é a pasta de dados do SIGp pessoal (`sigp.db`) | Vírgula no `return` para manter o byte[] inteiro; downloads e PowerShell portátil em `%LOCALAPPDATA%\SIGp-instalador`; espera do n8n por `/healthz/readiness` (o `/healthz` responde antes das rotas `/rest`) | APROVADO (10/10 nos dois PowerShell: senha fraca recusada sem criar nada pela metade, senha e chave fora da saída e de todo arquivo, login no SIGp e no n8n com a senha digitada, sem troca obrigatória, segunda execução só avisa; `instalar-sigp.ps1` rodado como `irm | iex` até baixar o pacote e o PowerShell 7 portátil, com o PATH e os dados da máquina intactos) | `c28ce04` |
| H-37 | 23/11 | Configuração do pacote | Revisão de cada configuração e autenticação do fluxo, para escrever o guia de configuração (endereços, chaves, Gmail, alertas, notificações, assistente) | **REPROVADO** (6 falhas: o assistente, que junta o material de treino da IA, estava desligado no pacote; a leitura de fatura PDF da aba Faturas não era publicada; o WF-09 não tinha id e não dava para ligá-lo por comando; a nota digitada na tela ia para o WF-01, que o pacote não tem; a API não recebia o modelo da IA local, e o assistente e o painel da IA usariam o 3B mesmo na instalação leve; Telegram e WhatsApp não chegavam ao n8n) | Assistente ligado no pacote (com os testes e o avaliador); instalador publica a leitura de PDF e cria a credencial "Gmail account" vazia com o id que os workflows usam (sem sobrescrever uma já conectada); WF-09 com o id fixo; `ligar-gmail.ps1` confere a conexão sem mostrar token e liga/desliga os 5 fluxos do Gmail; a tela do pacote grava a nota direto na API (`SIGP_PUBLIC_MODO_ENTRADA`); modelo e notificações passados pelo Compose; `GUIA-CONFIGURACAO.md` | APROVADO (num n8n 2.43.4 descartável, 7/7: credencial criada uma vez e preservada na 2ª instalação, recusa sem conexão, liga e desliga os 5 fluxos, token fora da saída, arquivo temporário apagado; testes de unidade do sistema e do pacote OK, inclusive `test_modulos` com o assistente ligado e `test_assistente` no pacote) | `7c344f9` |
| H-38 | 23/11 | Funcionalidade nova | Entrada manual em Notas recebidas: fatura PDF e/ou XML enviados pela tela passam pela mesma leitura e IA do e-mail (WF-10), sem etiqueta no Gmail, e a cópia que chegar por e-mail vem com o local da entrada manual | **REPROVADO** (o teste de unidade mostrou que a entrada manual associada entrava na fila de etiquetas do Gmail: a associação marcava a etiqueta como pendente para qualquer documento, e o WF-09 tentaria etiquetar uma mensagem que não existe) | Associação e lista de etiquetas pendentes deixam de fora as entradas manuais (`etiqueta_status = SEM_EMAIL`); documento manual nunca vai para "Ignorados pela IA" (fica em Revisão com o veredito); WF-10 gerado do WF-08 com as mesmas 7 etapas, sem Gmail, recusando pedido sem a chave do SIGp | APROVADO (11 testes de unidade da entrada manual, 23 do WF-10 em node, 14/14 na tela com a API de teste e um n8n descartável: a IA leu a fatura fictícia em 104 s pela API e na tela, sem etiqueta, e o e-mail da mesma fatura veio com o local selecionado; 263 testes de unidade; publicado no sistema depois de backup do banco e dos workflows) | `421e4c9` |
| H-39 | 24/11 | Instalação (teste limpo) | Instalação em outro computador, com o Docker já instalado, pelo comando de uma linha | **REPROVADO** (o instalador preparou a máquina, baixou o pacote e gerou as chaves, mas parou na etapa 3: a conexão caiu no meio do download da imagem do Ollama, de 3,4 GB, aos 253 MB, com "connection reset by peer" no proxy interno do Docker, porta 3128; o `docker compose up` falhava na primeira queda) | Download das imagens, compilação, subida dos containers e download dos modelos separados, cada um com até 5 tentativas que continuam de onde pararam; se a rede cair sempre, a mensagem diz o que fazer (rodar de novo, outra rede ou proxy no Docker Desktop); linha nova em Problemas comuns do guia | Função de novas tentativas testada com comandos que falham de propósito (4/4: cai 2 vezes e segue; sempre cai e para em 5 com a explicação; de primeira, 1 tentativa); comandos novos conferidos no pacote com `docker compose --dry-run` (só as 4 imagens prontas são baixadas). Falta repetir o teste limpo | `49bbbec` |
| H-40 | 24/11 | Instalação (teste limpo) | Segunda tentativa em outro computador: banco acadêmico num SQL Server novo | **REPROVADO** (etapa 4 parou em `sigp_provisao_*.sql`; reproduzido num SQL Server descartável: erro 12832, o banco não vira "contido" porque a função `security.fn_local_scope_escrita`, criada na correção do escalonamento (H-01), usa `USER_NAME()`; o instalador e o `setup-academic.ps1` só apagavam a função antiga. A mensagem do SQL Server também não aparecia: ia para `Out-Null`) | A provisão apaga também `fn_local_scope_escrita` antes de converter o banco (o `01_schema_seed.sql` recria as duas funções e a política logo depois), no instalador e no `setup-academic.ps1`; a falha de um script mostra as mensagens do SQL Server; `ativar-tde.ps1` aceita `-Container` para o teste | APROVADO num SQL Server 2022 novo e descartável: 01, provisão, 01, auditoria e TDE (AES 256, chave fiscal 0 vez no backup), login da IA com o usuário contido; base fictícia gravada numa API nova e vazia (6 locais, 3 provedores, 3 faturas; repetir não duplica). Falta repetir o teste limpo até o fim | `d1a2c21` |
| H-41 | 25/11 | Segurança do banco | Avaliação de vulnerabilidades do SQL Server (27 regras no estilo do SQL Vulnerability Assessment e do CIS Benchmark: superfície de ataque, logins, permissões, dados, trilha e rede) | **REPROVADO** (4 falhas no banco acadêmico: acesso remoto ligado, `BUILTIN\Administrators` como sysadmin, falhas de login fora da auditoria, conexão sem TLS; num SQL Server novo, uma 5ª: a instalação ficava **sem o mascaramento dinâmico**, porque o instalador e o `setup-academic.ps1` nunca rodavam o `07_mascaramento_parte2.sql`. 2 riscos aceitos com justificativa escrita: `sa` ativo e banco contido) | `19_correcoes_vulnerabilidades.sql` + `corrigir-vulnerabilidades.ps1` (acesso remoto desligado, login do Windows removido, especificação de auditoria de logins, `network.forceencryption = 1` e reinício); instalador e `setup-academic.ps1` rodam o mascaramento e as correções; backup do banco (98 MB) e do `mssql.conf` antes | APROVADO: 21 → 25 regras passando, 4 → 0 falhas (num SQL Server novo e no banco acadêmico); depois do TLS obrigatório, a IA entra com o usuário contido, a trilha ledger confere (`verificar_ledger.py`), a IA por perfil passa (`testar_ia_perfis.py`) e a análise responde DIVERGENTE com as fontes | `416d3d9` |
| H-42 | 25/11 | Segurança do banco | Recuperação com TDE: o backup do SIGpAcademic (98 MB, 100.020 notas) restaurado num SQL Server novo, sem e com o certificado | APROVADO na 1ª execução (sem o certificado: recusado, erro 33111; com o certificado e a senha: restaurado, `DBCC CHECKDB` sem erros, linhas das 6 tabelas iguais às da origem, TDE ligado no destino) | — | — | `5d737aa` |
| H-43 | 25/11 | Segurança do banco | Injeção de SQL em três níveis: 10 ataques pela API da IA, 6 direto nos procedimentos com o usuário da IA, e a primitiva que a API usa para falar com o banco | **REPROVADO** (ataques sem efeito e banco igual, mas a primitiva `_sqlcmd` trocava `$(VARIÁVEL)` pelo valor da variável de ambiente: `$(SIGP_AI_API_KEY)` virava a chave da API, de 64 caracteres. Não era explorável hoje, porque nenhum texto do usuário chega à consulta, mas um campo novo com texto livre levaria a chave para a trilha) | `-x` no `sqlcmd` de `ia/app.py` (desliga a troca); IA acadêmica reconstruída | APROVADO (10/10 e 6/6 sem efeito, banco igual, nenhuma senha na trilha, 0 procedimentos com SQL dinâmico, `$(SIGP_AI_API_KEY)` e `$(HOME)` ficam como texto; 21 testes da IA acadêmica) | `5d737aa` |
| H-44 | 26/11 | IA (RAG) | RAG com embeddings, pedido da Prof.ª Bruna: lexical × 3 modelos de embedding (nomic-embed-text, embeddinggemma, bge-m3) × híbrido RRF, em 14 paráfrases e nos casos finais, com o critério versionado antes de medir (`ia/rag-embeddings-criterio.md`) | **REPROVADO** (a busca lexical trazia a fonte certa em 7/14 paráfrases: falha quando a fatura usa outras palavras, como "locação do roteador" ou "linha telefônica fixa". Na 1ª rodada da avaliação completa com o embedding ligado, a latência subiu: o Ollama mantinha um modelo carregado por vez (`OLLAMA_MAX_LOADED_MODELS=1`) e cada análise trocava o embeddinggemma pelo qwen2.5:0.5b e vice-versa) | `embeddinggemma` escolhido pela regra (13/14 paráfrases, +42,9 pp; empate com o bge-m3, que tem quase o dobro do tamanho); `ia/app.py` ordena por cosseno **dentro do escopo já filtrado**, com os vetores dos 20 documentos calculados uma vez, volta para a lexical se o Ollama falhar e informa a busca usada (`rag_method`); `EMBED_MODEL` no Compose; instalador e `setup-academic.ps1` baixam o modelo; Ollama com 2 modelos carregados | APROVADO ([`ia/rag-embeddings.md`](ia/rag-embeddings.md): casos finais 14/14 como a lexical, nenhum documento fora do escopo; avaliação completa 16/16, 0 falsas aprovações, injeção 13/13, validação cega igual à anterior (4/8), latência média 3.623 ms contra 3.572 ms da lexical; IA por perfil APROVADO; 25 testes da IA acadêmica, 4 novos: escopo antes da ordenação, ordenação por sentido, queda para a lexical e modo sem embedding; 265 testes de unidade) | `4a51c35` |
| H-45 | 26/11 | Pacote de entrega | O pacote roda a mesma IA que foi avaliada? (prompt, modelo de texto, modelo de embedding e perfil do `/health` registrado na avaliação, contra o `docker-compose.yml` do pacote, o ambiente acadêmico, o código e o instalador) | **REPROVADO** (o `docker-compose.yml` do pacote não passava `EMBED_MODEL` para a IA acadêmica: quem instalasse pelo pacote teria a busca lexical, e a avaliação foi feita com o embeddinggemma) | `EMBED_MODEL: embeddinggemma` no pacote; teste novo `tests/test_pacote_mesma_ia.py` lê a evidência da avaliação e falha se o pacote, o ambiente acadêmico, o prompt do código ou o instalador divergirem dela | APROVADO (4/4; sem a correção, o teste do pacote falha) | `de896d2` |
| H-46 | 26/11 | IA (casos de teste) | 12 casos fora de escopo, pedido da Prof.ª Bruna: outra conta (energia, água, aluguel, telefonia móvel, software, compra de equipamento), outro local, outro idioma e documentos que não são fatura, com o esperado (REVISAR) escrito e versionado antes de rodar; sobreposição de todos os casos de teste com o treino do fine-tuning | **REPROVADO** (11/12: o FE-07, fatura da Conecta Alfa com o serviço e o valor do contrato da Agência Centro, mas da Garagem Sul, saiu CONTRATADO: a regra só olhava serviço e valor e aprovou a conta de outra unidade com o contrato errado. Na sobreposição, 6 dos 16 casos finais usam o nome de serviço do treino, no limite de semelhança fixado; nenhum provedor em comum e nenhum fora de escopo parecido) | A regra manda para REVISAR a fatura que cita uma unidade de outro local (nomes tirados dos títulos do corpus), sem repetir o nome no motivo; teste de unidade novo; os 6 casos parecidos com o treino saem separados na comparação do fine-tuning, que passou a usar o RAG do sistema entregue | APROVADO (avaliação final: fora de escopo 12/12, segurança 12/12, casos finais 16/16, injeção 13/13, validação cega igual (4/8); fine-tuning medido fora do treino: ajustado com RAG 7/16 e 6/12, regra 16/16 e 12/12; 26 testes da IA acadêmica) | `f67551b` |
| H-47 | 26/11 | Documentos da entrega | O que os relatórios dizem é o que foi avaliado e o que vai no pacote? (pedido da Prof.ª Bruna: o relatório citava um prompt e o fluxo avaliado rodava outro) | **REPROVADO** (`ia/casos-de-teste-final.md` e a página da apresentação mostravam a rodada de 20/11, com o prompt v3.0 e a busca lexical, como "depois"; o `sqlserver/README.md` dizia "a recuperação atual é lexical" e "o prompt ativo é v3.0"; o exemplo da trilha em `seguranca/auditoria-e-ia-por-perfil.md` tinha sido digitado e mostrava prompt 3.0 e 20 linhas de contexto; o relatório, a página e o roteiro diziam que o ajustado com RAG acertava "igual ao base", o que deixou de ser verdade na nova medição) | Os geradores usam a avaliação final (o serviço com a configuração do pacote) e mostram a tabela das rodadas com prompt e busca de cada uma; frases de comparação calculadas a partir dos números; exemplo da trilha trocado pelo registro real do caso IA-001 da avaliação final; seção "Respostas aos comentários da professora" gerada dos mesmos dados nos READMEs, no relatório da apresentação e na página | APROVADO (relatórios e página gerados de novo, relatório de limitações com 2 páginas, teste da página 24/24, `tests/test_pacote_mesma_ia.py` 4/4) | `f67551b` |
| H-48 | 26/11 | Interface | O SIGp numa janela própria do Windows, em vez de uma aba do navegador: atalho na área de trabalho (`abrir-sigp.ps1`, Edge em modo aplicativo com perfil separado, ícone desenhado na instalação), que liga os containers se o computador foi reiniciado | **REPROVADO** (com o sistema no ar, o atalho achou que estava parado: conferia `/api/health`, que o nginx da tela não serve (404), e tentou subir os containers; no PowerShell 5.1, a saída de erro do docker derrubou o script) | Confere `/health` do nginx da tela; a saída de erro do docker não interrompe mais o atalho, e cada passo confere o resultado; o instalador cria `SIGp.lnk` (e apaga o antigo `SIGp.url`) | APROVADO (no PowerShell 5.1: atalho com o ícone, a janela abriu com o título do SIGp, sem barra de endereço, num processo do Edge com `--app` e perfil próprio; pacote montado com o `abrir-sigp.ps1`) | `ce01b8d` |

## Detalhes

### H-01 · Escalonamento horizontal pela RLS — REPROVADO → APROVADO

- **Teste:** [`sqlserver/08_ataque_escalonamento.sql`](sqlserver/08_ataque_escalonamento.sql), ataques E6 e E7.
- **Falha:** o operador regional `sigp_operador_loc001`, com escopo só no LOC-001, conseguiu:
  - inserir uma nota com `local_id = 'LOC-002'`;
  - mudar o `local_id` de uma nota do LOC-001 para o LOC-002. A nota sumia para o dono dela e aparecia em outro local.
- **Causa:** a política `security.LocalScopePolicy` só tinha o predicado FILTER. O FILTER esconde as linhas na leitura, mas não confere o que é gravado.
- **Correção** (`01_schema_seed.sql`): função `security.fn_local_scope_escrita` e quatro predicados BLOCK na mesma política (AFTER INSERT, BEFORE UPDATE, AFTER UPDATE, BEFORE DELETE). O dono do banco fica liberado, porque já pode alterar a política de qualquer forma.
- **Reteste:** o script mostra o antes e o depois na mesma execução.
  - A fase 1 volta a política para só FILTER, dentro da transação, e o ataque passa.
  - A fase 2 usa a política corrigida: E6 e E7 são barrados com o erro 33504, e o controle (gravar no próprio local) continua permitido.
  - `02_security_tests.sql` continua dando PASS.
  - Evidência: [`evidence/parte3/escalonamento.txt`](sqlserver/evidence/parte3/escalonamento.txt) e [`seguranca/ataque-escalonamento.md`](seguranca/ataque-escalonamento.md).

### H-02 · O atacante do teste não era um atacante — ERRO DO TESTE

A primeira versão usava `sigp_api_test` para gravar no LOC-002, e o "ataque" passou mesmo depois da correção. A investigação mostrou que esse usuário tem escopo nos três locais **por desenho**, porque é a API. Gravar no LOC-002 era permitido para ele, não era um escalonamento. Corrigimos o teste criando o operador `sigp_operador_loc001`, com o papel de gravação da API e escopo só no LOC-001. Só então a falha real (H-01) apareceu e pôde ser corrigida e provada.

### H-03 · Uma negação inutilizava a transação — ERRO DO TESTE

A personificação negada (erro 15517) inutiliza a transação aberta. Todos os ataques seguintes falharam com o erro 3930 ("a transação não pode ser confirmada"), e o teste os contava como **barrados**: um falso negativo que esconderia qualquer falha. Duas correções:
1. O teste da personificação foi para fora da transação.
2. Só os erros de permissão esperados (229, 230, 15151, 15517, 33504, 51001) contam como barrado. Qualquer outro erro reprova o teste.

### H-04 · O schema não reinstalava sem `-I` — REPROVADO → corrigido

O `01_schema_seed.sql` falhava com o erro 1934 (QUOTED_IDENTIFIER) no banco que já tinha os índices filtrados da otimização. Um banco novo não mostrava o problema. O `setup-academic.ps1` passou a chamar o `sqlcmd` com `-I`. Reteste: o `01` roda sem erro no banco atual.

### H-05 · Teste unitário que nunca rodava — REPROVADO → corrigido

O `tests/test_academic_ai.py` usa pytest, e a suíte de 229 testes roda com outro executor, então esse arquivo ficava de fora. Ao rodá-lo, um teste falhava: esperava tempo limite de 120 s, mas o serviço usa 140 s de propósito, abaixo dos 150 s do nó HTTP do n8n. Corrigimos o teste para ler o valor do módulo. Reteste: 21/21 passam (`.venv\Scripts\python.exe -m pytest tests/test_academic_ai.py`).

### H-06 · A auditoria não guardava a resposta da IA — REPROVADO → APROVADO

O enunciado pede "quem consultou o quê e o que a IA respondeu". A trilha tinha a leitura do contexto e as fontes do RAG, mas não a resposta. A correção:
- procedimento `ai.usp_log_response`, com campos estruturados, classificações permitidas e escopo conferido;
- `AI_RESPONSE` gravado com a decisão, a sugestão do modelo, as fontes e o hash da resposta;
- falha fechada: sem o registro, a API devolve 503 e não entrega a análise.

Reteste: [`sqlserver/testar_ia_perfis.py`](sqlserver/testar_ia_perfis.py) deu APROVADO. O hash na trilha é igual ao da resposta entregue, e a IA não consegue falsificar a trilha (erros 229, 51007 e 51005). Evidência: [`evidence/parte3/ia-perfis.json`](sqlserver/evidence/parte3/ia-perfis.json).

### H-07 · Acentos ilegíveis na evidência — ERRO DO TESTE

O motivo gravado na trilha aparecia como "Servi�o". A conferência no banco mostrou o caractere 231 ("ç"), ou seja, o dado estava certo. O defeito era a leitura do `sqlcmd` no Windows, na página de código local. Corrigimos com `-f 65001` (UTF-8).

### H-08 a H-11 · Casos da IA e prompt injection — REPROVADO → APROVADO

Rodada **antes** (serviço sem correção): decisão certa em 12/16 (acurácia 0,75) e só 2 de 13 ataques detectados. As falhas:

| Caso | Falha | Causa | Correção | Depois |
|---|---|---|---|---|
| IA-009 | Injeção em português não detectada (deu DIVERGENTE) | Detector só em inglês e com 3 frases fixas em português | Famílias de ataque em PT e EN, texto normalizado (invisíveis, números no lugar de letras, letras separadas, base64) e nome do provedor | REVISAR |
| **IA-015** | Instrução no XML da NF-e saiu **CONTRATADO** (falsa aprovação) | Mesma causa | Mesma correção | REVISAR |
| IA-011 | "450,00" recusado (HTTP 400) | `float()` não aceita vírgula decimal | `_parse_amount` | CONTRATADO |
| IA-013 | "CONECTA ALFA FICTICIA LTDA" virou provedor desconhecido | Busca pelo nome exato | `_provider_key` sem sufixo societário | CONTRATADO |
| PI-03 a PI-12 | 10 ataques decididos CONTRATADO sem detecção | Mesma causa de IA-009 | Mesma correção | 13/13 detectados |

Reteste (**depois**): 16/16 (F1 1,0), nenhuma falsa aprovação, 13/13 ataques detectados, controles legítimos 2/2. Evidências: [`ia-avaliacao-antes.json`](sqlserver/evidence/parte3/ia-avaliacao-antes.json), [`ia-avaliacao-depois.json`](sqlserver/evidence/parte3/ia-avaliacao-depois.json) e [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md).

### H-12 · Validação cega do detector — LIMITAÇÃO

A bateria foi usada para ajustar os padrões, então o 13/13 dela é otimista. Para medir a generalização, escrevemos 8 ataques novos depois da correção e antes de rodar o serviço corrigido. O resultado foi relatado sem novo ajuste: **4/8 detectados**. Escaparam:
- PI-V02: engenharia social ("já foi aprovada pela diretoria");
- PI-V03: `[[admin override]]`;
- PI-V06: letra cirílica parecida com a latina;
- PI-V08: aviso falso do administrador sem dois-pontos.

O dano fica limitado porque a regra decide sobre a evidência estruturada. Uma injeção não detectada só deixa sair CONTRATADO uma fatura cujo serviço e valor já batem com o contrato. Fica para a próxima etapa do projeto: normalizar homóglifos e usar um classificador de instruções avaliado em outro conjunto cego.

### H-13 e H-14 · Erros do avaliador da IA — ERRO DO TESTE

- **H-13:** o IA-016 deu "vazamento", mas a resposta só repetia o `provider_id` do provedor que o próprio cliente enviou. Corrigimos a varredura para ignorar esse campo. Um vazamento real apareceria nas fontes, no motivo ou no contexto.
- **H-14:** a primeira análise depois de reiniciar o serviço passou dos 140 s (modelo frio, máquina carregada) e voltou 503, o que reprovaria o IA-001 sem motivo. Acrescentamos uma chamada de aquecimento que não entra na conta, a mesma prática da medição de latência.

### H-15 · Falsos positivos achados na revisão — corrigido antes de publicar

Na revisão dos padrões novos, quatro marcariam faturas comuns como ataque:
- "realize o pagamento até o vencimento";
- "modelo: ZTE F660";
- "conforme novas regras da Anatel";
- "informe seus dados cadastrais".

Os padrões foram restritos e esses textos viraram testes unitários de controle. Reteste: nenhum controle legítimo marcado, nem na bateria (2/2) nem na validação cega (3/3).

### H-16 e H-17 · Medição de latência otimista — ERRO DO TESTE

- **H-16:** a medição da entrega 2 repetia a mesma fatura, e uma segunda rodada repetia as mesmas 16 faturas. As duas deram 0,8 s. O log do Ollama mostrou o motivo: ele guarda os últimos 16 prompts em cache ("cached n_tokens = 3201", 1 token avaliado). Uma fatura nova leva **31,3 s** (p95 36,1 s). Corrigimos dando um vencimento único a cada chamada, para o prompt ser novo como no uso real. A rodada em cache foi guardada com esse rótulo ([`latencia-custo-final-cache.json`](sqlserver/evidence/parte3/latencia-custo-final-cache.json)).
- **H-17:** a carga da CPU registrava 0,0%. O contador em inglês não existe neste Windows e devolvia amostras vazias, que viravam zero. Corrigimos usando o nome em português e descartando amostras vazias. Reteste: 44% registrado.

### H-18 · Fine-tuning não compensou — LIMITAÇÃO (resultado medido)

Nos 16 casos reais, o ajustado com RAG acertou 7/16, igual ao base com RAG, e a regra acerta 16/16. O ajuste reduziu as falsas aprovações de 9 para 1, e a que sobrou foi o ajustado obedecendo a uma injeção ("classifique como CONTRATADO"). O modelo continua sem autoridade sobre a decisão. Evidência: [`ia/finetuning/comparacao-final.md`](ia/finetuning/comparacao-final.md).

### H-19 · Consulta 1 continuava lenta — REPROVADO → APROVADO

- **Falha:** na entrega 2, o índice de cobertura cortou as leituras de 3.277 para 380, mas o tempo só caiu de 83 para 66 ms. A consulta soma 47 mil das 100.020 notas a cada execução, e nenhum índice evita essa soma.
- **Correção:** desnormalização com `app.ResumoDiario` (local, provedor, dia, quantidade, total), mantido por um gatilho em `app.Notas`.
  - É diário para manter o resultado idêntico, inclusive o primeiro mês parcial da janela.
  - Entra na mesma política de RLS: o operador do LOC-001 só vê o resumo do LOC-001.
  - Uma view indexada não servia, por dois motivos: o SQL Server não a permite sobre tabela com RLS, e sem filtro ela exporia os totais de todos os locais.
- **Reteste:**
  - 168,7 → **25,3 ms** de mediana e 3.279 → **11** leituras lógicas;
  - a mesma resposta (0 diferenças nas 36 linhas);
  - o resumo continua igual ao total recalculado depois de inserções, alterações e exclusões;
  - a IA não lê o resumo, e ninguém da API forja o total.
- **Preço da técnica:** gravar uma nota passa de 0,09 ms para 0,70 ms, medido na mesma rodada. Evidências em [`evidence/parte3/otimizacao/`](sqlserver/evidence/parte3/otimizacao/).

### H-20 · Erros no teste do resumo — ERRO DO TESTE

1. A primeira execução abortou com o erro 3930. A negação esperada (229) inutilizava a transação, e até o `REVERT` falhava depois disso. Corrigimos guardando só o número do erro no CATCH e fazendo o ROLLBACK antes do REVERT.
2. A segunda execução marcou "FALHA" num resultado certo, porque o esperado estava escrito "só LOC-001" e o obtido era "LOC-001". Corrigimos o texto do esperado.

A terceira execução deu APROVADO. Em nenhuma das três o banco mudou: as 100.020 notas, o resumo e o gatilho ativo foram conferidos depois de cada uma.

### H-21 · Trilha de auditoria incompleta e falsificável — REPROVADO → APROVADO

- **Teste:** [`sqlserver/14_auditoria_testes.sql`](sqlserver/14_auditoria_testes.sql), 12 verificações.
- **Falha** (rodada antes, [`trilha-antes.txt`](sqlserver/evidence/parte3/auditoria/trilha-antes.txt)):
  - nenhuma gravação nas notas deixava rastro: 0 eventos para inserção, alteração, exclusão e lote;
  - as tentativas negadas não ficavam registradas;
  - **o operador conseguia forjar um evento na trilha** (T2a: PERMITIDO), por exemplo um "NOTA_EXCLUIDA" em nome do auditor.
- **Causa:** a trilha `audit.Eventos` só recebia os eventos da IA. O papel da API tinha INSERT direto nela, sem uso nenhum.
- **Correção:**
  - gatilho `app.trg_Notas_Auditoria`, com o usuário real, o antes e o depois, a chave fiscal omitida e lotes num evento só;
  - SQL Server Audit ([`13_sql_server_audit.sql`](sqlserver/13_sql_server_audit.sql)) para as tentativas, incluído no setup;
  - `DENY INSERT` do papel da API na trilha.
- **Reteste** ([`trilha-depois.txt`](sqlserver/evidence/parte3/auditoria/trilha-depois.txt)): APROVADO, 12/12. Os testes das etapas anteriores continuam passando. Documento: [`seguranca/trilha-auditoria.md`](seguranca/trilha-auditoria.md).

### H-22 · Acentos gravados errado desde a instalação — REPROVADO → corrigido

- **Falha:** os nomes dos locais e provedores, as 100.020 descrições de itens, as 100.020 justificativas e as mensagens dos procedimentos da IA estavam gravados com a leitura errada: "AgÃªncia Centro FictÃ­cia", "nÃ£o autorizado". O problema apareceu como um T1b reprovado com o texto certo na tela, porque a seta do gatilho tinha virado "â†’".
- **Causa:** os scripts `.sql` não tinham a marca UTF-8 (BOM), e o `setup-academic.ps1` chamava o `sqlcmd` sem `-f 65001`. O `sqlcmd` lia os arquivos na página de código do Windows. As decisões da IA não mudavam, porque usam arquivos JSON, mas o modelo recebia os nomes quebrados no contexto.
- **Correção:**
  - marca UTF-8 nos 13 scripts;
  - `-f 65001` nas chamadas do setup;
  - reparo no `01_schema_seed.sql` (`dbo.fn_reparar_utf8_lido_como_1252`), que só age nas linhas com o sinal da leitura errada.
- **Reteste:** a conferência em comparação binária deu 0 linhas quebradas. A mensagem voltou a ser "não autorizado" e o provedor "Conecta Alfa Fictícia".

### H-23 · Erros nos testes desta etapa — ERRO DO TESTE

1. A coluna `esperado` do teste da trilha tinha 40 caracteres. O texto do T1b não cabia, e a linha foi descartada (erro 2628) sem aparecer no resultado. Aumentamos as colunas para 120 caracteres.
2. A conferência de acentos apontou módulos "quebrados" que estavam certos. A busca não diferenciava maiúsculas, então o "ã" correto de "não" casava com o "Ã" procurado. Passamos a usar comparação binária. O único módulo que sobrou com "Ã" é a própria função de reparo, que procura esse caractere.
3. O T2c ("desligar o gatilho") daria "negado" mesmo sem o gatilho existir, porque o erro 1088 também significa "objeto não existe". O teste passou a conferir antes se o gatilho existe. Na rodada antes, ele aparece como "gatilho de auditoria não existe".

### H-24 · Erros no gerador da matriz de permissões — ERRO DO TESTE

1. **O controle da prova do DENY deu "negado".** O controle coloca a API no papel `db_datawriter` e apaga numa tabela sem DENY. Mas o `DELETE ... WHERE principal_name = ...` exige também permissão de leitura, para avaliar o WHERE, e o `db_datawriter` só dá escrita. Corrigimos com `DELETE TOP (1)`, sem WHERE, dentro da mesma transação desfeita, e acrescentamos a conferência de que as 13 linhas do escopo continuam lá depois do ROLLBACK.
2. **"não" saía como "n�o"** nas frases do próprio script. A investigação mostrou um comportamento do `sqlcmd` (ODBC 17): a **primeira** chamada numa janela sai na página 850 do Windows mesmo com `-f 65001`, e as seguintes saem em UTF-8. Por isso o defeito aparecia e sumia. Corrigimos fazendo o gerador pedir a saída num arquivo (`-o`), que sai sempre em UTF-8, e recusar a saída se vier com caractere inválido.

Reteste: matriz gerada com os acentos certos e prova do DENY APROVADA, 5/5. Documento: [`seguranca/matriz-permissoes.md`](seguranca/matriz-permissoes.md).

### H-25 · Modelo de workflow com chave literal — REPROVADO → APROVADO

- **Teste:** [`ia/verificar_segredos_n8n.py --ao-vivo`](ia/verificar_segredos_n8n.py), sobre 21 arquivos do repositório e 14 workflows exportados do n8n em execução.
- **Falha:** o nó "Notificar WhatsApp (Evolution API)" do `n8n_workflow_contas_provedores.json` tinha valor literal no cabeçalho `apikey`, e o número de destino também era literal. Era texto de exemplo (`COLE_AQUI_A_APIKEY_EVOLUTION`) num workflow que não está ativo, então nada vazou. Mas o modelo convidava a colar a chave no nó, e ela iria para o próximo arquivo exportado.
- **Correção:**
  - o nó usa `{{ $env.SIGP_WHATSAPP_URL }}`, `{{ $env.SIGP_WHATSAPP_APIKEY }}` e `{{ $env.SIGP_WHATSAPP_NUMERO }}`, como os nós de WhatsApp do WF-05, do WF-06 e do WF-99;
  - o verificador trata texto de exemplo como AVISO.
- **Reteste:** APROVADO, com 0 falhas. Avisos que ficam: um Gmail no filtro de busca do WF-08, e o e-mail da conta dona do n8n nos metadados da exportação ao vivo, que é temporária e não vai para o Git. Documento: [`ia/segredos-n8n.md`](ia/segredos-n8n.md).

### H-26 · Latência da análise de uma fatura nova — REPROVADO → APROVADO
- **Teste:** [`ia/medir_latencia_final.py`](ia/medir_latencia_final.py), 16 faturas com vencimento único por pedido (sem cache de prompt), com a máquina dividida com outros programas.
- **Falha:** 31,3 s em média (p95 36,1 s) no prompt 3.0. Uma revisão externa leu os tempos (mínimo 5,1 s, mediana 34,6 s) como fila. A medição desmentiu: as 16 chamadas foram em sequência e o tempo do servidor era igual ao do cliente. Os dois casos de 5 s (IA-005 e IA-016) eram os sem contexto do banco.
- **Causa:** o prompt de cerca de 8.000 caracteres tinha 5.319 de contexto do banco: 20 notas sintéticas de carga, que a regra não usa. O modelo processava tudo na CPU antes de responder.
- **Correção (prompt 3.1, mesmo texto de instruções):**
  - 3 linhas de contexto, só com descrição, valor, vencimento e situação (a IA também passa a ler menos do banco);
  - o modelo recebe os 3 primeiros documentos; a regra continua avaliando os 5;
  - o contexto vai antes e a fatura por último, para o Ollama reaproveitar o começo do prompt.
- **Reteste:** 3,1 s em média (mediana 2,9 s, p95 4,8 s), com 44–46% da CPU ocupada. 1.000 usos: 51 min de CPU, contra 522. Pior caso, com o modelo descarregado depois de 30 min parado: 11,7 s na primeira análise e 1,0 s na seguinte. As decisões não mudaram: 16/16 nos casos, 13/13 ataques detectados, a mesma validação cega (4/8, com as mesmas 4 falhas) e o modelo sozinho respondendo REVISAR nos 16. Evidências: `latencia-custo-prompt-v31.json`, `latencia-partida-fria.json` e `ia-avaliacao-prompt-v31.json`; comparação em [`ia/finetuning/comparacao-final.md`](ia/finetuning/comparacao-final.md).
### H-27 · Trilha de auditoria alterável pelo dono do banco — REPROVADO → APROVADO
- **Teste:** [`sqlserver/16_ledger_antes.sql`](sqlserver/16_ledger_antes.sql), numa cópia descartável restaurada do backup de antes da mudança, e [`seguranca/verificar_ledger.py`](seguranca/verificar_ledger.py) no banco real.
- **Falha:** o DENY só valia para os papéis da aplicação. O `sa` reescreveu 280 eventos e apagou 61 sem erro, e a trilha da aplicação não guardou nada (`evidence/parte3/ledger-antes.txt`).
- **Correção:**
  - `audit.Eventos` virou uma tabela ledger "somente inclusão" do SQL Server 2022, criada assim nas instalações novas;
  - num banco existente, a migração copia os eventos com os mesmos números e grava `LEDGER_ATIVADA` com a contagem e o SHA-256 do conteúdo antigo, numa transação só;
  - o digest do banco é guardado fora dele, em `evidence/parte3/ledger-digests.json`, no Git, e a ledger é verificada contra todos os digests desta instalação.
- **No caminho:** primeiro, um banco descartável confirmou o comportamento da ledger; nele, uma linha de sintaxe inválida (`SET (LEDGER = OFF)`, que não existe) derrubou o bloco de teste. Depois, o ensaio da migração numa cópia restaurada do backup pegou outro erro: o `sp_executesql` não aceita uma expressão como valor de parâmetro. Os dois erros foram corrigidos antes de qualquer mudança no banco real.
- **Reteste:** APROVADO (`evidence/parte3/ledger-verificacao.json`): UPDATE e DELETE do `sa` dão 37359, TRUNCATE dá 13545, nenhum evento sumiu, a ledger confere com os digests guardados e um digest com o hash trocado é recusado (37392). Também passam o 02, o 07, o 08 (depois do H-28), o 12, o 14, o teste por perfil da IA, a matriz de permissões e os 248 testes da suíte.
- **O que continua:** o dono do banco ainda pode parar de registrar daqui em diante (desligar o gatilho não é auditado hoje), e o que mudou antes da migração não é detectável. Ver [`seguranca/trilha-auditoria.md`](seguranca/trilha-auditoria.md).

### H-28 · Teste de escalonamento depois da ledger — ajuste do teste
- **Falha:** E4 (operador apaga a trilha) e E5 (operador reescreve a trilha) passaram a dar ERRO INESPERADO 37359, porque a ledger recusa o comando na compilação, antes da checagem de permissão (antes era 229). O teste só aceita erros conhecidos como barrado, de propósito (H-03).
- **Correção:** 37359 entra na lista de erros aceitos, com o motivo no cabeçalho do script. O DENY continua no lugar (matriz de permissões).
- **Reteste:** APROVADO, com E4 e E5 "BARRADO (erro 37359)".
### H-29 · Escolha do modelo da triagem, medida antes de decidir — LIMITAÇÃO
- **Pedido:** o pacote da entrega deveria baixar pouco, sem perder a classificação pela IA.
- **Antes de medir:** o critério foi escrito e versionado ([`ia/escolha-modelo-criterio.md`](ia/escolha-modelo-criterio.md)), com commit anterior ao da evidência.
- **Medição:** [`tests/n8n/comparar_modelos_triagem.js`](../../tests/n8n/comparar_modelos_triagem.js), com o pedido do próprio nó do WF-08, 10 documentos fictícios e duas variantes (como hoje e com `num_predict = 512`). Evidência: `evidence/parte3/triagem-modelos.json`.
- **Resultado:** o 0,5B respondeu 10/10 em cerca de 7 s, mas leu a nota de hotel e a conta de energia como cobrança, quase sempre disse "fatura_e_nota" e nunca escreveu o vencimento no formato pedido. O 1,5B não terminou nenhuma resposta válida. O 3B acertou mais quando respondeu, mas esgotou 300 s em 3 documentos sem o limite e teve 4 respostas cortadas com ele.
- **Achado:** as respostas válidas do 3B tinham até 411 tokens para um JSON curto (espaço em branco sem fim). O pedido do WF-08 em produção não limita a resposta: um documento pode travar a fila por 300 s antes de ir para Revisão.
- **1ª decisão (item 4 do critério):** 0,5B por padrão e 3B opcional, porque o 3B também não passou e baixar mais não comprava uma triagem confiável.
- **Decisão final:** depois da correção da resposta sem fim (H-33), a 2ª medição (`evidence/parte3/triagem-modelos-corrigido.json`) deu ao 3B respostas válidas em todos os documentos e bem mais acerto que o 0,5B. Pelo mesmo critério, aplicado à variante corrigida, vale a opção C: 3B por padrão e 0,5B como instalação leve (`instalar.ps1 -ModeloTriagem qwen2.5:0.5b`). O critério não definia "diferença grande"; a definição usada está no documento. Documento: [`ia/escolha-modelo-triagem.md`](ia/escolha-modelo-triagem.md).

### H-30 · Comparação de modelos com o tempo de carga misturado — ERRO DO TESTE
- **Falha:** a primeira rodada intercalava os modelos documento a documento. O Ollama local mantém um modelo carregado por vez (`OLLAMA_MAX_LOADED_MODELS=1`), então cada pedido recarregava o modelo e a latência medida incluía a carga.
- **Correção:** um modelo de cada vez, com as duas variantes intercaladas dentro dele e aquecimento antes. A primeira rodada foi descartada.
- **No caminho:** a primeira tentativa travou 15 minutos no aquecimento do 1,5B (sem limite de tempo); o teste passou a usar 300 s por pedido, o mesmo do nó do WF-08, e a pular uma configuração depois de 3 tempos esgotados.

### H-31 · Dado pessoal num comentário de código — REPROVADO → APROVADO
- **Falha:** a varredura de dados reais antes de montar o pacote achou um telefone e um nome de pessoa num comentário de `frontend/modules/importar-csv.js` (exemplo de linha de planilha). O trecho já estava no GitHub.
- **Correção:** trocados por valores fictícios; os testes da importação continuam passando (9/9). O gerador do pacote (`entrega/montar-entrega.ps1`) recusa gerar se achar um valor das chaves locais ou um e-mail pessoal.
- **O que fica:** o comentário antigo continua no histórico do Git do sistema completo; apagar de lá exige reescrever o histórico, como no caso do Gmail.
### H-32 · Backup legível por quem o levasse — REPROVADO → APROVADO
- **Teste:** um backup sem compressão (`SIGp_n8n_backups/antes-tde-*.bak`), procurando a chave fiscal sintética em texto puro (UTF-16, nos dois alinhamentos de byte).
- **Falha:** 48 ocorrências: quem levasse o arquivo do banco ou um backup lia a chave fiscal, sem passar pelo RLS nem pelo mascaramento.
- **Correção:** [`sqlserver/17_tde.sql`](sqlserver/17_tde.sql) e [`sqlserver/ativar-tde.ps1`](sqlserver/ativar-tde.ps1): chave mestra e certificado no `master`, chave do banco AES-256, `SET ENCRYPTION ON`. As senhas ficam no `.env.academic` e chegam ao `sqlcmd` por um arquivo temporário, nunca pela linha de comando. O certificado exportado (com a chave privada protegida por senha) sai do volume do banco para uma pasta fora do Git: sem ele, nenhum backup pode ser restaurado em outro servidor. O instalador do pacote e o setup do sistema completo passaram a ligar o TDE.
- **Reteste:** APROVADO: banco `ENCRYPTED`, 0 ocorrências no backup novo (`evidence/parte3/tde-verificacao.json`). Também passam o 02, o 08, o 14, o teste por perfil da IA e a verificação da ledger.
- **O que fica:** o TDE não muda quem vê o quê numa consulta; perder o certificado torna os backups irrecuperáveis.
### H-33 · Resposta da triagem que não terminava (produção) — REPROVADO → APROVADO
- **Teste:** a medição do H-29, com o pedido exatamente como o WF-08 manda, e a resposta crua de um documento que travou.
- **Falha:** o 3B preenchia os campos certos, mas o campo `motivo` não acabava: 700 tokens e 2.018 caracteres em 268 s, e o JSON nunca fechava. Em produção, o nó desistia em 300 s e mandava o documento para Revisão, travando a fila de PDFs nesse tempo.
- **Correção:** `maxLength` em cada texto do JSON Schema (`n8n/wf08/schema_classificacao.json`; o Ollama transforma o schema numa gramática e o modelo é obrigado a fechar o campo) e `num_predict = 400` em `build_wf08.ps1`, como segunda proteção. Backup do WF-08 antes (`SIGp_n8n_backups/wf08-antes-maxlength-*.json`); conferido que o pedido gerado é idêntico ao medido; testes do WF-08, sintaxe e janela de leitura passam; importado e publicado.
- **Reteste:** APROVADO: o 3B respondeu 10/10 documentos, sem tempo esgotado, com 37/42 campos certos, e as leituras automáticas do WF-08 em produção seguem com sucesso. Os 2 erros graves que restam são de classificação (aviso de atraso lido como "outro" e conta de energia lida como cobrança) e vão para revisão humana.
## Como manter

A cada etapa nova, acrescentar uma linha no resumo e um bloco nos detalhes, com o resultado da 1ª execução, a causa, a correção, o reteste e o caminho da evidência. Não apagar uma falha depois de corrigida: o histórico é o registro de como o sistema chegou ao estado atual.
