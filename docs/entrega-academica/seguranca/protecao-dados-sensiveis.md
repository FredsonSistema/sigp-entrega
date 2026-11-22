# Proteção de dado sensível: RLS e mascaramento, justificados pelo cenário

Matriz de quem vê o quê: [`matriz-permissoes.md`](matriz-permissoes.md) · Testes: [`../sqlserver/07_mascaramento_parte2.sql`](../sqlserver/07_mascaramento_parte2.sql), [`../sqlserver/08_ataque_escalonamento.sql`](../sqlserver/08_ataque_escalonamento.sql), [`../sqlserver/02_security_tests.sql`](../sqlserver/02_security_tests.sql), [`../sqlserver/testar_ia_perfis.py`](../sqlserver/testar_ia_perfis.py).

## O cenário

O SIGp audita as contas de internet de várias localidades de um grupo de empresas de transporte: agências, rodoviárias e
garagens. Cada localidade tem os seus provedores, as suas faturas e as suas notas fiscais. As pessoas que usam o sistema
têm papéis diferentes:

- **operador regional:** cuida das contas da sua regional. Não deve ver nem mexer nas contas de outra;
- **sistema (API) e financeiro:** lançam e conciliam as notas de todos os locais;
- **fiscal:** confere as notas na Receita, por isso precisa da chave fiscal completa;
- **auditor:** confere o que foi feito (a trilha) e não precisa dos dados de negócio;
- **IA local:** sugere uma classificação para cada fatura. Recebe texto que vem de fora (e-mails de provedores), que pode trazer prompt injection.

O que precisa de proteção:

| Dado | Classificação | Por quê |
|---|---|---|
| `app.Notas.chave_fiscal` (chave de acesso da NF-e) | **sensível** | Com ela, qualquer pessoa consulta a nota no portal da Receita e vê emitente, destinatário, CNPJs, itens e valores. É a chave da nota inteira. |
| `app.Pagamentos.referencia` | **sensível** | Identifica o pagamento no banco. Ajuda a fraudar ou a contestar um pagamento. |
| Notas, valores e pagamentos de cada local | **interno**, restrito ao local | O operador de uma regional não tem motivo para ver os contratos e gastos de outra. |
| Trilha de auditoria | **interno**, só o auditor | Quem é auditado não lê a própria trilha. |

## Técnica 1: Row-Level Security (RLS) por local

- **O que é:** `security.LocalScopePolicy` associa cada usuário do banco aos locais do seu escopo (`security.LocalScope`).
  - Um predicado **FILTER** esconde as notas e o resumo diário de outros locais em toda leitura.
  - Quatro predicados **BLOCK** impedem gravar uma nota fora do escopo ou mover uma nota para outro local.
- **Por que serve a este cenário:** o recorte de acesso é *por linha*, porque o mesmo tipo de dado (uma nota) é de um local ou de outro, e *por local*, porque é assim que a operação se organiza. Permissão por tabela não resolve isso: o operador precisa ler `app.Notas`, mas só as do seu local.
  - A RLS fica no banco. Vale para qualquer caminho de acesso: API, IA, ferramenta de consulta ou uma credencial vazada.
  - Não depende de cada consulta lembrar de filtrar o local.
- **Prova:**
  - O operador do LOC-001 lê só o LOC-001.
  - Ele não grava nem move nota para o LOC-002 (`08_ataque_escalonamento.sql`, erro 33504).
  - A IA de cada local recebe contexto só do próprio local (`testar_ia_perfis.py`, parte B).
  - O resumo da consulta 1 respeita a mesma regra (`12_resumo_testes.sql`).
- **Histórico:** a primeira versão só tinha o FILTER, e o teste de escalonamento mostrou que o operador gravava no local de outro (H-01 em [`../historico-evolucao.md`](../historico-evolucao.md)).

## Técnica 2: Mascaramento dinâmico (Dynamic Data Masking) com UNMASK granular

- **O que é:** a chave fiscal e a referência de pagamento ficam gravadas por inteiro, mas o banco devolve um valor mascarado a quem não tem `UNMASK` naquela coluna.
  - A chave aparece como `SINT****************-001`, com 4 caracteres de cada lado.
  - O papel `sigp_fiscal` tem `UNMASK` só nessas duas colunas.
- **Por que serve a este cenário:**
  - A API e o operador **precisam da linha**: valor, vencimento, status e provedor, para conciliar e cobrar. Mas **não precisam da chave fiscal completa**. Os 4 primeiros e 4 últimos caracteres bastam para conferir com o papel.
  - Só o fiscal consulta a nota na Receita.
  - O mascaramento entrega exatamente isso, sem duplicar tabelas e sem mudar a aplicação: a mesma consulta devolve a chave inteira ao fiscal e mascarada aos demais.
- **Prova** (`07_mascaramento_parte2.sql`):
  - a API vê `SINT****************-001`;
  - o fiscal vê `SINTETICA-CHAVE-001`, e só no LOC-001, porque a RLS continua valendo;
  - o auditor não lê as notas;
  - a view da IA não tem a coluna (0 colunas de chave em `ai.vw_contexto_minimo`).

## Como as duas se combinam

A RLS decide **quais linhas** cada um vê. O mascaramento decide **o que aparece numa coluna** dessas linhas. As duas valem
juntas: o fiscal vê a chave real, mas só do seu local. A IA fica com a menor visão de todas:
- não lê nenhuma tabela;
- recebe, por um procedimento que confere o local, uma view sem a chave fiscal;
- a resposta da API não devolve as linhas do banco, só a contagem.

## Por que não criptografia

| Opção | Por que não foi a escolhida aqui |
|---|---|
| Always Encrypted na chave fiscal | O banco não consegue comparar nem buscar pela chave sem a chave criptográfica na aplicação, e a conciliação procura nota por chave. Exigiria mudar a API e gerenciar chaves, sem proteger contra quem já usa a aplicação. |
| TDE (criptografia do banco em repouso) | Protege o arquivo e o backup roubados, mas não muda quem vê o quê numa consulta: o operador continuaria vendo a chave e as notas de outros locais. É complementar, não substitui as duas técnicas. |

**Atualização (entrega final): o TDE foi ligado** como terceira camada, complementar às duas técnicas acima ([`../sqlserver/17_tde.sql`](../sqlserver/17_tde.sql), [`../sqlserver/ativar-tde.ps1`](../sqlserver/ativar-tde.ps1)). Num backup sem compressão, a chave fiscal sintética aparecia 48 vezes em texto puro antes e 0 depois; o banco está `ENCRYPTED` com AES-256 ([`tde-verificacao.json`](../sqlserver/evidence/parte3/tde-verificacao.json)). O certificado exportado fica fora do volume do banco e do Git: sem ele, nenhum backup pode ser restaurado em outro servidor. O TDE não muda quem vê o quê numa consulta; isso continua com o RLS, o DENY e o mascaramento.

## Limites

- **Mascaramento não é criptografia.** Quem tem SELECT pode tentar adivinhar o valor por filtro, por exemplo `WHERE chave_fiscal LIKE 'SINTETICA-CHAVE-00%'`. Por isso a IA e quem não precisa da linha não têm SELECT na tabela. Hoje a auditoria nativa registra só as gravações; auditar também as leituras dessa coluna mostraria quem tenta adivinhar o valor, ao custo de um arquivo de auditoria bem maior.
- **O dono do banco (`db_owner`) e o `sa` não passam pela RLS nem pelo mascaramento.** A defesa é operacional: a senha do `sa` fica só no `.env.academic`, ignorado pelo Git, e a IA e a API usam usuários próprios, sem esses papéis.
- **Os dados são sintéticos.** O desenho foi pensado para os dados reais do SIGp, mas só foi testado com dados de laboratório.
