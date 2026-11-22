# SIGp — Auditoria de faturas de provedores

**Grupo e integrantes:** ver [`identificacao.json`](identificacao.json) (a mesma identificação de todos os PDFs).  
**Disciplinas:** Projeto de Inteligência Artificial; Segurança e Otimização de Banco de Dados.  
**Repositórios:** sistema completo em <https://github.com/FredsonSistema/sigp>; pacote de instalação com base fictícia em <https://github.com/FredsonSistema/sigp-entrega>.

## Entrega final (01/12/2026)
- **Instalação:** [`GUIA-INSTALACAO.md`](GUIA-INSTALACAO.md) (máquina sem nada instalado até o sistema funcionando) e [`ENDPOINTS.md`](ENDPOINTS.md) (o que testar e o resultado esperado).
- **Apresentação (10 min):** roteiro com quem fala, tempos, falas, lista de conferência, plano B e perguntas prováveis em [`roteiro-apresentacao.md`](roteiro-apresentacao.md); demonstração ao vivo passo a passo em [`demo-final.ps1`](demo-final.ps1) (`pwsh -File docs/entrega-academica/demo-final.ps1`; com `-SemPausa` grava `sqlserver/evidence/parte3/demo-final-saida.txt`); página interativa dos resultados em [`apresentacao.html`](apresentacao.html) (abre sem internet).
- **Relatórios:** [`relatorio-apresentacao.pdf`](relatorio-apresentacao.pdf) e [`relatorio-limitacoes.pdf`](relatorio-limitacoes.pdf). Histórico de cada falha, correção e reteste: [`historico-evolucao.md`](historico-evolucao.md).
- **IA:** [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) (16 casos, injeção, validação cega congelada e intervalos de 95%), [`ia/escolha-modelo-triagem.md`](ia/escolha-modelo-triagem.md) (critério, medição e escolha do modelo), [`ia/finetuning/comparacao-final.md`](ia/finetuning/comparacao-final.md) (4 configurações, custo e latência), [`ia/segredos-n8n.md`](ia/segredos-n8n.md) e [`ia/prompts/CHANGELOG.md`](ia/prompts/CHANGELOG.md).
- **Segurança e otimização:** [`seguranca/matriz-permissoes.md`](seguranca/matriz-permissoes.md), [`seguranca/protecao-dados-sensiveis.md`](seguranca/protecao-dados-sensiveis.md), [`seguranca/otimizacao-consultas.md`](seguranca/otimizacao-consultas.md), [`seguranca/ataque-escalonamento.md`](seguranca/ataque-escalonamento.md), [`seguranca/trilha-auditoria.md`](seguranca/trilha-auditoria.md) e [`seguranca/auditoria-e-ia-por-perfil.md`](seguranca/auditoria-e-ia-por-perfil.md). Banco, papéis e RLS: [`sqlserver/README.md`](sqlserver/README.md).
- **Evidências:** [`sqlserver/evidence/parte3/`](sqlserver/evidence/parte3/). Nenhum número dos documentos foi digitado à mão: os geradores leem esses arquivos. Em [`sqlserver/evidence/parte2/`](sqlserver/evidence/parte2/) ficaram só os cinco arquivos da Entrega 2 que os documentos finais usam como comparação (casos da API, tempos do benchmark, demonstração de perfis, memória de exemplos e teste inverso).

## Problema e objetivo

Quem acompanha as contas de internet de agências, rodoviárias e garagens precisa identificar faturas vencidas, diferenças de valor e serviços cobrados que não constam no contrato. Os dados chegam em arquivos separados e em momentos diferentes. O SIGp organiza esses documentos e destaca casos para conferência humana, sem autorizar pagamentos.

## Usuário, entradas e saídas

- **Usuário:** responsável por conferir contas e auditor.
- **Entradas:** faturas PDF e notas/pagamentos em XML ou JSON, importados manualmente ou pelo fluxo n8n (e-mail).
- **Saídas:** conciliação, divergências justificadas, itens pendentes de revisão e trilha de auditoria.

## Maior risco

Sugestão errada ou instrução maliciosa em um documento influenciar a análise. Mitigação: contexto delimitado, citações, testes de prompt injection, permissões sem escrita para a IA e aprovação humana. Os testes e resultados estão em [`ia/casos-de-teste-final.md`](ia/casos-de-teste-final.md) e [`seguranca/ataque-escalonamento.md`](seguranca/ataque-escalonamento.md).

## Entregas anteriores

Os documentos e PDFs das Entregas 1 (02/11/2026) e 2 (16/11/2026) saíram do repositório na limpeza da entrega final e continuam no histórico do Git (último commit com eles: `52e65ae`). O que mudou desde então, com cada falha, correção e reteste, está em [`historico-evolucao.md`](historico-evolucao.md).
