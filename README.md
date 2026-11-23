# SIGp: gestão de contas de internet de provedores (entrega acadêmica)

Projeto de Inteligência Artificial · Segurança e Otimização de Banco de Dados. Integrantes e matrículas:
[`docs/entrega-academica/identificacao.json`](docs/entrega-academica/identificacao.json).

Este repositório é o **pacote da entrega**: só o fluxo de gestão de contas de provedores, separado do sistema completo da
empresa por um script (`entrega/montar-entrega.ps1` no sistema completo). Todos os dados são fictícios.

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
área de trabalho e abre a tela. Detalhes e problemas comuns: [`docs/entrega-academica/GUIA-INSTALACAO.md`](docs/entrega-academica/GUIA-INSTALACAO.md).

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

1. **Tela:** clique no atalho **SIGp** (ou abra http://127.0.0.1:8000/agencias.html) e entre com o usuário e a senha que
   você criou. Em **Notas recebidas** estão as 3 faturas fictícias: associe cada uma ao local e ao provedor e veja a
   comparação com o contrato.
2. **IA acadêmica:** `POST http://127.0.0.1:5678/webhook/sigp-academic-ai` com a fatura no corpo, por exemplo
   `{"provider":"Conecta Alfa Fictícia","description":"IP adicional mensal","amount":"35.00"}`. Resposta: decisão da regra,
   fontes do contrato, sugestão do modelo e `automatic_payment: false`.
3. **Demonstração completa** (IA, ataques, trilha, perfis, consultas): `pwsh -File docs/entrega-academica/demo-final.ps1`.
   Para ela e para os testes de avaliação: **Python 3.12** e **sqlcmd** (`winget install sqlcmd`).

### Conectar o Gmail (opcional)

A busca de faturas no Gmail precisa de uma conta Google conectada ao n8n, e isso exige login no Google: não dá para
automatizar. Sem o Gmail, todo o resto funciona com a base fictícia.

1. No Google Cloud, crie um projeto, ative a Gmail API e crie um "ID do cliente OAuth" do tipo aplicativo da Web, com o
   endereço de retorno `http://127.0.0.1:5678/rest/oauth2-credential/callback`. Publique o app ("Em produção"): em teste,
   o Google derruba a conexão a cada 7 dias.
2. No n8n, crie a credencial **Gmail account** (Gmail OAuth2) com o Client ID e o Client Secret e clique em "Conectar".
3. No SIGp, em **Configurações > E-mail das faturas**, confira os remetentes procurados.
4. No n8n, ative o WF-08 (e o WF-09, o WF-06 e o WF-99, que também usam o Gmail).

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `instalar-sigp.ps1`, `Instalar SIGp.cmd` | Instalação numa máquina sem nada (WSL, Docker, PowerShell 7 e o pacote) |
| `instalar.ps1`, `primeiro-acesso.ps1`, `docker-compose.yml` | Instalação do pacote, criação do seu acesso e os serviços |
| `backend/` | API do SIGp (Flask): locais, notas recebidas, associação, faturas, perfis, cofre de chaves, métricas da IA |
| `agencias.html`, `frontend/`, `web/` | Tela do SIGp |
| `ocr/` | Serviço de OCR do PDF |
| `n8n/workflows/` | Workflows importados pelo instalador; `n8n/wf08`, `n8n/wf06` e `n8n/lib` são as fontes deles |
| `docs/entrega-academica/` | Tudo da entrega: relatórios, IA (`ia/`), segurança (`seguranca/`), SQL Server (`sqlserver/`), evidências e a apresentação |
| `entrega/base_ficticia.py` | Base de demonstração (locais, provedores e faturas inventados) |
| `tests/` | Testes unitários (`python -m unittest discover -s tests`) e dos workflows |

## Documentos da entrega

- Roteiro da apresentação de 10 minutos: [`docs/entrega-academica/roteiro-apresentacao.md`](docs/entrega-academica/roteiro-apresentacao.md)
- Resultados interativos (abre sem internet): [`docs/entrega-academica/apresentacao.html`](docs/entrega-academica/apresentacao.html)
- Relatório de limitações: [`docs/entrega-academica/relatorio-limitacoes.pdf`](docs/entrega-academica/relatorio-limitacoes.pdf)
- Índice de todos os documentos e evidências: [`docs/entrega-academica/README.md`](docs/entrega-academica/README.md)
- Histórico de cada falha, correção e reteste: [`docs/entrega-academica/historico-evolucao.md`](docs/entrega-academica/historico-evolucao.md)
