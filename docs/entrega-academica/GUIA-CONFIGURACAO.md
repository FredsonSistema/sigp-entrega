# Guia de configuração: endereços, chaves, Gmail, alertas e assistente

Para depois da instalação ([`GUIA-INSTALACAO.md`](GUIA-INSTALACAO.md)). Os comandos rodam no PowerShell, na pasta da
instalação (padrão `Documentos\sigp-entrega`). Em resumo:

| # | O quê | Quem faz | Obrigatório? |
|---|---|---|---|
| 1 | Endereços, chaves e senhas entre os serviços | O instalador | Já feito |
| 2 | Seu acesso à tela e ao n8n | O instalador (você digita a senha) | Já feito |
| 3 | Conta Google (Gmail) e os fluxos de e-mail | Você, uma vez (~15 min) | Para buscar faturas no e-mail |
| 4 | Remetentes das faturas e quem recebe os alertas | Você, na tela | Junto com o passo 3 |
| 5 | Outras pessoas e integrações | Você, na tela | Quando precisar |
| 6 | Assistente da IA (o treino da IA) | Você e a equipe, no dia a dia | Recomendado |
| 7 | Telegram, WhatsApp e PDFs com senha | Você | Opcional |

## 1. O que o instalador já configurou

### Endereços

| Serviço | Do seu navegador | Dentro da rede Docker (entre os serviços) |
|---|---|---|
| Tela do SIGp | http://127.0.0.1:8000/agencias.html | — |
| API do SIGp | http://127.0.0.1:5001 (`/api/health`) | `http://api:5001` (`SIGP_API_URL` no n8n) |
| n8n (fluxos) | http://127.0.0.1:5678 | — |
| IA acadêmica (RAG) | http://127.0.0.1:5010 (`/health`) | `http://academic-ai:5010` |
| IA local (Ollama) | não exposta | `http://ollama:11434` |
| Leitura de PDF (OCR) | não exposta | `http://ocr:5002` |
| SQL Server acadêmico | 127.0.0.1:14333 | `sqlserver-academic:1433` |

Tudo fica em `127.0.0.1`: nenhum serviço aceita conexão de outro computador. A tela já vem apontando para a API e para o
n8n; em **Configurações › Integração** dá para conferir (o ponto de interrogação de cada campo explica o que é, para que
serve, como configurar e onde achar). A **Entrada de notas** vem como "Direto na API", porque o pacote não tem os fluxos
WF-01/WF-02 do sistema completo.

### Webhooks publicados

| Webhook | Workflow | Autenticação |
|---|---|---|
| `POST http://127.0.0.1:5678/webhook/sigp-academic-ai` | SIGp Acadêmico - RAG e Análise | o n8n envia `X-API-Key` (= `SIGP_AI_API_KEY`) à IA |
| `POST http://127.0.0.1:5678/webhook/sigp-faturas-pdf` | Extrair fatura PDF (aba Faturas) | o n8n chama a API com `SIGP_API_KEY` |

### Chaves e senhas (geradas na sua máquina, nunca mostradas)

| Variável | Arquivo | Quem usa | Para quê |
|---|---|---|---|
| `SIGP_API_KEY` | `.env` | API do SIGp e os workflows do n8n | Os fluxos gravam na API com ela; cria o primeiro administrador |
| `SIGP_COFRE_CHAVE` | `.env` | API do SIGp | Chave mestra do cofre (AES-256-GCM) das chaves de integração |
| `SIGP_AI_API_KEY` | `.env.academic` (cópia no `.env`) | IA acadêmica e o n8n | Só quem tem a chave pede análise à IA |
| `MSSQL_SA_PASSWORD` | `.env.academic` | instalador e scripts de prova | Administração do SQL Server |
| `SIGP_AI_DB_PASSWORD_LOC001/002` | `.env.academic` | IA acadêmica | Usuários do banco presos ao próprio local (RLS) |
| `MSSQL_TDE_*` e `segredos-locais/tde/` | `.env.academic` e pasta | SQL Server | Criptografia do banco e dos backups (TDE) |

As credenciais criadas dentro do n8n (a do Gmail, por exemplo) ficam criptografadas no volume `n8n_data`, com uma chave
que o próprio n8n gerou. Nenhuma delas vai para o Git.

**Trocar uma chave** (se vazou, por exemplo): edite a linha no `.env` e rode `docker compose up -d api n8n`. Quem já
entrou na tela continua dentro, porque a sessão é por usuário e senha. As senhas dos usuários da IA no banco têm um script
próprio: `pwsh -File docs/entrega-academica/sqlserver/trocar-senhas-ia.ps1`. Trocar a `SIGP_COFRE_CHAVE` invalida o que
estava gravado no cofre de chaves da API (`/api/cofre`): é preciso gravar de novo.

## 2. Seu acesso

O instalador criou, com a senha que você digitou, o **administrador da tela do SIGp** (usuário e senha) e o **dono do n8n**
(seu e-mail e a mesma senha). Se você pulou essa etapa: `pwsh -File primeiro-acesso.ps1`.

## 3. Conectar o Gmail

O sistema lê as faturas que chegam na caixa de um Gmail. Você vai criar no Google um "cliente OAuth" (a permissão para o
n8n ler e etiquetar esse Gmail) e colar os dois códigos na credencial que o instalador já deixou pronta no n8n.

**No Google Cloud** (https://console.cloud.google.com, com a conta do Gmail que vai receber as faturas):

1. **Criar o projeto:** no seletor de projetos, **Novo projeto**, nome `SIGp`, **Criar**.
2. **Ativar a Gmail API:** **APIs e serviços › Biblioteca**, procure **Gmail API** e clique em **Ativar**.
3. **Tela de consentimento:** **APIs e serviços › Tela de consentimento OAuth** (ou **Google Auth Platform › Branding**):
   tipo **Externo**, nome do app `SIGp`, seu e-mail como suporte e contato. Em **Público-alvo**, clique em
   **Publicar app** (fica "Em produção"). Em modo de teste, o Google desconecta a cada 7 dias.
4. **Criar o cliente:** **APIs e serviços › Credenciais › Criar credenciais › ID do cliente OAuth**, tipo
   **Aplicativo da Web**. Em **URIs de redirecionamento autorizados**, adicione exatamente:
   `http://127.0.0.1:5678/rest/oauth2-credential/callback`
   (é o mesmo endereço que o n8n mostra como "OAuth Redirect URL" na credencial). **Criar**. Deixe a janela com o
   **ID do cliente** e a **Chave secreta do cliente** aberta.

**No n8n** (http://127.0.0.1:5678, entre com seu e-mail e senha):

5. **Overview › Credentials › Gmail account** (criada vazia pelo instalador; os workflows já apontam para ela).
6. Cole o **Client ID** e o **Client Secret**, clique em **Sign in with Google**, escolha a conta e autorize. Como o app
   não passou pela verificação do Google, aparece "O Google não verificou este app": clique em **Avançado › Acessar SIGp
   (não seguro)**. O app é seu e só roda na sua máquina. A credencial deve mostrar "Account connected". **Save**.

**No SIGp** (passo 4 abaixo): confira os remetentes. Depois, no PowerShell:

7. `pwsh -File ligar-gmail.ps1`. Ele confere que a conta está conectada (sem mostrar nenhum token) e liga:
   WF-08 (lê o Gmail a cada 5 min), WF-09 (etiquetas nas notas associadas), o utilitário de etiquetas, WF-06 (alertas
   diários de vencimento por e-mail) e WF-99 (recebe os erros dos fluxos; o aviso por e-mail, Telegram ou WhatsApp é opcional, passo 7). Para tirar do ar:
   `pwsh -File ligar-gmail.ps1 -Desligar`.

**Conferir:** mande para esse Gmail um e-mail com uma fatura PDF de um remetente cadastrado. Em até 5 minutos ela aparece
em **Financeiro › Notas recebidas**, e no Gmail a mensagem ganha a etiqueta `SIGp/Importado`. No n8n, **Executions**
mostra cada leitura.

Guarde o Client Secret como uma senha: ele fica só na credencial do n8n, criptografado. Para trocar de conta Google: `ligar-gmail.ps1 -Desligar`, conecte a credencial com a outra conta e
rode `ligar-gmail.ps1` de novo.

## 4. Remetentes e alertas (na tela, Configurações)

- **E-mail das faturas:** os domínios ou e-mails dos provedores que mandam as faturas (por exemplo `provedor.com.br` ou
  `faturas@provedor.com.br`). O WF-08 só importa mensagens desses remetentes. A lista vem com exemplos: troque pelos seus
  provedores. Vale na leitura seguinte, sem abrir o n8n.
- **Alertas por e-mail:** quem recebe o resumo diário das contas que vencem, vencidas e não recebidas (WF-06, enviado pelo
  mesmo Gmail). Um ou mais e-mails.

## 5. Outras pessoas e integrações (na tela, Configurações)

- **Usuários e integrações:** **pessoas** entram com usuário e senha. Quem cria a pessoa recebe uma senha temporária
  para entregar a ela, e a pessoa é obrigada a trocá-la no primeiro acesso. **Integrações** (outro sistema que vai chamar a
  API) recebem uma chave de API própria, que pode ser desativada sem mexer nas outras.
- **Grupos de permissão:** o que cada grupo pode ver e fazer (por exemplo, quem associa notas e quem ensina o
  assistente). O administrador pode tudo.
- **Auditoria de acesso:** quem entrou, o que foi recusado e de onde.

## 6. Assistente da IA: é aqui que a IA aprende

**Análise › Assistente** responde perguntas sobre as contas e os locais ("Quantas agências estão em atraso?", "Qual o
provedor da Agência Centro Fictícia?") com a IA local, e gera relatórios em PDF e CSV. Cada avaliação vira material de
treino da IA:

| Na tela | O que acontece |
|---|---|
| 👍 **Resposta certa (ensina o assistente)** | A pergunta vira exemplo: o assistente passa a reconhecer as parecidas |
| 👎 **Resposta errada** + comentário | Vai para a lista de revisão, com o que estava errado |
| **Ensinar um termo** | Um jeito de falar da equipe (ex.: "atrasada" = vencida) passa a ser entendido |
| **🎓 Treinar o assistente** | Mostra quantas foram aprovadas, reprovadas e aprendidas, e a lista de reprovadas para revisar |
| **⬇ Exportar dataset (JSONL)** | Baixa os exemplos aprovados no formato de ajuste fino do modelo ([`ia/finetuning/`](ia/finetuning/README.md)) |

Quanto mais a equipe usa e avalia, melhor fica o reconhecimento das perguntas e maior o dataset para treinar o modelo. As
respostas continuam saindo das regras e dos dados do SIGp: a IA escolhe a ferramenta e os filtros, não inventa números.
Precisa das permissões "Conversar com o assistente" e "Ensinar o assistente" (o administrador tem as duas). O modelo é o
mesmo da triagem do Gmail (`SIGP_OLLAMA_MODEL`, padrão `qwen2.5:3b`).

## 7. Opcionais

Depois de mudar o `.env`, rode `docker compose up -d n8n` (ou `ocr`) para o serviço ler os valores novos.

- **PDFs com senha** (provedores que protegem a fatura com o CNPJ do cliente): no `.env`,
  `SIGP_PDF_SENHA_CNPJS=12345678,87654321` (os 8 primeiros dígitos do CNPJ de cada empresa cliente) e
  `docker compose up -d ocr`. A senha nunca é gravada.
- **Aviso de erro dos fluxos por e-mail (WF-99):** `SIGP_RELATORIO_EMAIL=voce@exemplo.com` no `.env` e, no n8n, ative o
  nó **Gmail - relatório** do WF-99 (vem desligado) e salve.
- **Telegram:** crie um bot com o @BotFather e guarde o token. No n8n, crie a credencial **Telegram API** com o token.
  No `.env`, `SIGP_TELEGRAM_CHAT_ID=<id do chat>`. No n8n, abra o WF-06, ative o nó **Telegram - alerta** (vem
  desligado), escolha a credencial e salve.
- **WhatsApp (Evolution API):** no `.env`, `SIGP_WHATSAPP_URL`, `SIGP_WHATSAPP_NUMERO` e `SIGP_WHATSAPP_APIKEY`. No n8n,
  ative o nó **WhatsApp - alerta** do WF-06 (e do WF-99, se quiser aviso de erro).

## 8. Conferência final

| O que | Como | Esperado |
|---|---|---|
| API | http://127.0.0.1:5001/api/health | `"status": "ok"` |
| IA acadêmica | http://127.0.0.1:5010/health | `"status": "ok"` |
| Login | tela do SIGp | entra com seu usuário e senha |
| Gmail | n8n › Credentials › Gmail account | "Account connected" |
| Fluxos | `docker exec sigp_n8n n8n list:workflow --active=true` | WF-08, WF-09, WF-06, WF-99, IA acadêmica e Extrair fatura PDF |
| Faturas | e-mail de teste de um remetente cadastrado | aparece em Notas recebidas em até 5 min |
| Assistente | Análise › Assistente: "Quantas agências estão em atraso?" | resposta com os números da base |

| Problema | O que fazer |
|---|---|
| "redirect_uri_mismatch" ao conectar o Google | O URI do passo 4 tem que ser idêntico ao "OAuth Redirect URL" do n8n (sem barra no fim) |
| "access_denied" ou "app em teste" | Publique o app (passo 3) ou adicione o seu e-mail em "Usuários de teste" |
| Desconecta depois de 7 dias | O app ficou em modo de teste: publique e conecte de novo |
| `ligar-gmail.ps1` diz que não está conectada | Volte ao passo 6 e confira "Account connected" |
| Nada chega em Notas recebidas | Confira o remetente em E-mail das faturas e a execução do WF-08 em Executions |
