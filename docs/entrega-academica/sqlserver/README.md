# SQL Server acadêmico local

Este banco é separado do SQLite operacional do SIGp. Use somente dados sintéticos e não exponha a porta além de `127.0.0.1`.

## Instalação local da demonstração

Com Docker Desktop iniciado e `sqlcmd` instalado, execute na raiz do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File docs/entrega-academica/sqlserver/setup-academic.ps1
```

O script cria segredos locais ignorados pelo Git, inicializa a base sintética, provisiona usuários SQL contidos com escopo mínimo, sobe a API RAG e Ollama CPU, baixa o modelo Qwen 0.5B, importa o workflow no n8n e reinicia apenas esse serviço para receber a chave da API. Não use dados reais. O primeiro download do modelo pode levar alguns minutos.

A classificação e as fontes são calculadas por regras determinísticas sobre afirmações estruturadas dos documentos recuperados; o LLM retorna apenas uma classificação experimental, cuja concordância é medida e que não pode alterar o resultado. A recuperação é por embeddings (`embeddinggemma` no Ollama, `EMBED_MODEL`), sempre dentro do escopo do local e do provedor, com volta para a busca lexical se o Ollama falhar; a escolha e a medição estão em `../ia/rag-embeddings.md`. O prompt do endpoint é o v3.1 (`../ia/prompts/CHANGELOG.md`, tabela "Qual prompt cada fluxo usa hoje"). A avaliação final desse serviço está em `../ia/casos-de-teste-final.md`. Foi executado um experimento LoRA separado com Qwen2.5-0.5B-Instruct em CPU; o adaptador só entra na API pelo perfil experimental (`integrate-lora.ps1`), que não é o perfil entregue. Resultados, limitações, dataset sintético e instruções estão em `../ia/finetuning/README.md`; não confundir esse piloto com o modelo do endpoint.

O endpoint aceita tanto a fatura normalizada (`provider`, `description`, `amount`) quanto o JSON convertido de NF-e (`invoice.nfeProc.NFe.infNFe` ou `invoice.nfeproc.nfe.infnfe`). Para NF-e, extrai o provedor de `emit.xNome`/`emit.xFant`, as descrições de `det[].prod.xProd` e o total de `total.ICMSTot.vNF`. Um provedor sem correspondência contratual permitida é encaminhado para `REVISAR`; esse parser não interpreta PDF/XML bruto nem substitui validação fiscal.

Depois, ative o workflow **SIGp Acadêmico - RAG e Análise** na interface `http://127.0.0.1:5678`. Para executar os 16 casos de avaliação e os testes de injeção diretamente contra o serviço real (a chave vem do `.env.academic`):
```powershell
.\.venv\Scripts\python.exe docs\entrega-academica\ia\avaliar_ia.py atual
```
O avaliador grava os resultados em `evidence/parte3/ia-avaliacao-atual.json`, com acerto da decisão, F1 por classe, concordância do LLM, fontes citadas, latência e confirmação de que nenhum pagamento automático foi acionado (detalhes em [`../ia/casos-de-teste-final.md`](../ia/casos-de-teste-final.md)). A execução mede o modelo real; testes com stub não devem ser apresentados como resultado do LLM.

## Subir somente o SQL Server manualmente

1. Crie `docs/entrega-academica/sqlserver/.env.academic` (arquivo ignorado pelo Git) contendo `MSSQL_SA_PASSWORD=<senha-forte>`. Use uma senha forte que satisfaça os requisitos do SQL Server; nunca a copie para scripts, workflow, prompt ou relatório.
2. Na raiz do projeto, execute:

   ```powershell
   docker compose --env-file docs/entrega-academica/sqlserver/.env.academic -f docs/entrega-academica/sqlserver/compose.academic.yml up -d
   ```

3. Aguarde o container ficar pronto. A conexão de laboratório é `127.0.0.1,14333`, banco inicial `master`. `sqlcmd` do SQL Server Tools ou Azure Data Studio podem ser usados.
4. No PowerShell, carregue `.env` local sem imprimir a senha e execute:

   ```powershell
   $env:SQLCMDPASSWORD = '<senha configurada no arquivo local .env.academic>'
   sqlcmd -S 127.0.0.1,14333 -U sa -d master -C -b -i docs/entrega-academica/sqlserver/01_schema_seed.sql
   sqlcmd -S 127.0.0.1,14333 -U sa -d SIGpAcademic -C -b -i docs/entrega-academica/sqlserver/02_security_tests.sql
   ```

   Não substitua o placeholder por uma senha em comandos salvos, captura de tela ou terminal compartilhado.

O schema cria três locais fictícios, uma carga inicial idempotente de 20 notas, roles e usuários de teste `WITHOUT LOGIN`. As identidades de teste existem somente dentro do banco e são ativadas por `EXECUTE AS USER` no script de validação; não são credenciais de produção.

## Controle de escopo e auditoria

- `security.LocalScope` associa cada principal de teste a um ou mais locais.
- Row-Level Security filtra `app.Notas` por `USER_NAME()` e pelo escopo cadastrado.
- A mesma política tem predicados **BLOCK** (inserir, alterar e apagar): ninguém grava nota em local fora do próprio escopo nem move uma nota para outro local. O ataque de escalonamento que motivou a correção, com o antes e o depois, está em `08_ataque_escalonamento.sql` e em `../seguranca/ataque-escalonamento.md`.
- A identidade `sigp_ia` não lê tabelas/view diretamente; só executa `ai.usp_get_context`.
- O procedimento rejeita local não autorizado e registra ator, ação, objeto, correlation ID, local solicitado e total de linhas. Não registra XML, chave fiscal, nem payload integral.
- `ai.vw_contexto_minimo` não contém a chave fiscal. O acesso da IA à view e às tabelas permanece explicitamente negado.
- Usuários de integração reais só devem ser criados após integrar autenticação individual e validar o fluxo de segredos.

`13_sql_server_audit.sql` liga a auditoria nativa do SQL Server (tentativas negadas, mudanças de papel e de permissão); o gatilho `app.trg_Notas_Auditoria` (no `01`) registra em `audit.Eventos` quem inseriu, alterou ou apagou cada nota. `14_auditoria_testes.sql` prova a trilha e deve terminar com `APROVADO`. Todos os scripts `.sql` têm a marca UTF-8; ao rodar manualmente, use também `-f 65001`.

`08_ataque_escalonamento.sql` reproduz a falha antiga (só FILTER) e roda 8 ataques de escalonamento vertical e horizontal contra a política corrigida, mais um controle positivo; deve terminar com `APROVADO`. Rode sempre com `-I` (os índices filtrados da otimização exigem `QUOTED_IDENTIFIER`).

`02_security_tests.sql` verifica leitura autorizada, negação de tabela/view direta, bloqueio de escopo cruzado, `DENY DELETE` da API, negação de principal sem role e visibilidade de auditoria. Execução com `sqlcmd -b` deve terminar com `resultado = PASS`; qualquer falha emite erro e retorna código de saída não zero.

## Base de benchmark e planos

`03_load_benchmark.sql` carrega até 100.000 notas e itens sintéticos, aproximadamente 50.000 pagamentos e até 100.000 conciliações. O carregamento é idempotente para registros de origem `carga_sintetica`. A tabela de saída mostra os volumes reais.

As duas consultas medidas (resumo mensal por provedor/local e pendências vencidas sem conciliação concluída) estão em `10_benchmark_final.sql` e `11_planos_final.sql`; `benchmark-final.ps1` roda as 30 medidas por configuração e grava tempos, leituras lógicas e planos `.sqlplan` em `evidence/parte3/otimizacao/`. Resultado e análise: [`../seguranca/otimizacao-consultas.md`](../seguranca/otimizacao-consultas.md).

## Parar

Na raiz do projeto:

```powershell
docker compose --env-file docs/entrega-academica/sqlserver/.env.academic -f docs/entrega-academica/sqlserver/compose.academic.yml down
```

Isso mantém o volume persistente. Não use `down -v` se precisar preservar a base de testes.
