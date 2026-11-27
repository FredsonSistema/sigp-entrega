# Guia de instalação para quem nunca usou o SIGp (Windows)

Este guia leva uma máquina sem nada instalado até o SIGp funcionando com a base fictícia, a IA local e o banco seguro.
A versão anterior deste guia (passo a passo manual) está no histórico do Git.

## 1. O que você precisa

| Item | Mínimo | Para quê |
|---|---|---|
| Windows 10 22H2 ou Windows 11 (64 bits), com virtualização ligada na BIOS | — | O Docker roda os serviços em Linux (WSL 2) |
| Memória | 8 GB (16 GB recomendado) | SQL Server, IA local, n8n e a tela ao mesmo tempo |
| Disco livre | 15 GB | Imagens, modelos de IA e banco |
| Internet | só na instalação | Depois, tudo roda local; nenhum dado sai da máquina |

## 2. Instalar (um comando)

Abra o **PowerShell** (menu Iniciar › "PowerShell"), cole esta linha e aperte Enter:

```powershell
irm https://raw.githubusercontent.com/FredsonSistema/sigp-entrega/main/instalar-sigp.ps1 | iex
```

Ou baixe e clique duas vezes em [`Instalar SIGp.cmd`](https://github.com/FredsonSistema/sigp-entrega/blob/main/Instalar%20SIGp.cmd), que faz o mesmo.

O instalador pula o que a máquina já tem:

1. confere memória, disco e virtualização;
2. liga o **WSL 2**, se faltar. É o único momento em que o Windows pede **permissão de administrador**. Depois ele pede
   para **reiniciar**; ao entrar de novo, a instalação continua sozinha;
3. instala o **Docker Desktop** no modo do usuário (sem administrador), já com a licença aceita, liga o Docker e espera;
4. baixa o PowerShell 7 portátil e o pacote do SIGp (não precisa de Git);
5. instala o SIGp: chaves, containers, banco, modelos de IA, workflows e base fictícia (de 15 a 40 minutos na primeira
   vez, quase tudo download);
6. **cria o seu acesso**: pede seu nome, um usuário, seu e-mail e uma senha (8 a 64 caracteres, com maiúscula e número),
   que vale para a tela do SIGp e para o n8n. A senha é digitada por você, não aparece na tela, não vai para a área de
   transferência e não é gravada em arquivo. O SIGp guarda só o hash;
7. cria o atalho **SIGp** na área de trabalho e abre a tela: o SIGp abre numa **janela própria do Windows** (sem barra de endereço nem abas, com ícone na barra de tarefas; é o Edge em modo aplicativo, que já vem no Windows). Se o computador foi reiniciado, o atalho liga os containers e espera a tela responder.

Para você sobram: colar a linha, aceitar a janela de administrador e reiniciar (só se o WSL faltava) e digitar seu acesso.

Opções, antes do comando: `$env:SIGP_PASTA = 'D:\sigp'` (pasta da instalação; padrão `Documentos\sigp-entrega`) e
`$env:SIGP_MODELO_TRIAGEM = 'qwen2.5:0.5b'` (instalação leve: ~1,5 GB a menos, triagem do Gmail mais fraca).

### O que fica só nesta máquina

O instalador gera estes arquivos na pasta da instalação. Eles **nunca** devem ir para o Git nem ser mostrados na tela:

| Arquivo ou pasta | Conteúdo |
|---|---|
| `.env` | Chave da API do SIGp, chave mestra do cofre e chaves da IA |
| `docs/entrega-academica/sqlserver/.env.academic` | Senha do `sa` do SQL Server, senhas dos usuários da IA e do TDE |
| `segredos-locais/tde/` | Certificado do TDE: sem ele, nenhum backup do banco pode ser restaurado em outro computador |

Guarde os três juntos num lugar seguro (um gerenciador de senhas, por exemplo), separados dos backups do banco.

## 3. Usar

Clique no atalho **SIGp** (janela própria; sem o atalho, rode `powershell -File abrir-sigp.ps1` na pasta do pacote ou abra http://127.0.0.1:8000/agencias.html no navegador) e entre com o usuário e a senha que você criou.
O n8n fica em http://127.0.0.1:5678 (login: seu e-mail e a mesma senha).

| O que conferir | Onde | Esperado |
|---|---|---|
| Base fictícia | Tela › Cadastros › Agências | 3 agências "Fictícia" (e rodoviárias e garagem) |
| Faturas para associar | Tela › Notas recebidas | 3 faturas "Aguardando associação" |
| Serviços | `docker ps --format "{{.Names}} {{.Status}}"` | 7 containers `sigp_*` com "Up" |

## 4. Demonstração e testes (opcional)

Precisam do Python 3.12 e do sqlcmd: `winget install -e --id Python.Python.3.12` e `winget install -e --id Microsoft.Sqlcmd`.
Na pasta da instalação:

```powershell
pwsh -File docs/entrega-academica/demo-final.ps1                # demonstração passo a passo (Enter entre os passos)
python docs/entrega-academica/ia/avaliar_ia.py depois           # 16 casos, injeção e validação cega
python docs/entrega-academica/sqlserver/testar_ia_perfis.py     # a IA não vaza o que o banco protege
python docs/entrega-academica/seguranca/verificar_ledger.py     # trilha à prova de adulteração
python -m pip install -r requirements.txt; python -m unittest discover -s tests   # testes unitários
```

Teste da IA pelo n8n (a primeira resposta leva cerca de 12 s, porque o modelo é carregado):

```powershell
$f = '{"provider":"Conecta Alfa Fictícia","description":"IP adicional mensal","amount":"35.00"}'
Invoke-RestMethod -Method Post http://127.0.0.1:5678/webhook/sigp-academic-ai -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($f))
```

Esperado: `classification: DIVERGENTE` (o contrato não inclui IP adicional), as fontes do contrato em `source_ids` e
`automatic_payment: False`. Onde está cada requisito e o resultado de cada um: [`README.md`](README.md).

## 5. Parar, religar e remover

Depois de reiniciar o computador, abra o Docker Desktop se ele não ligar sozinho: os containers do SIGp voltam junto.
Na pasta da instalação:

```powershell
docker compose stop          # para tudo (os dados ficam)
docker compose start         # liga de novo
docker compose down          # remove os containers (os dados ficam nos volumes)
docker compose down -v       # remove TUDO, inclusive o banco e os modelos baixados (não tem volta)
```

## 6. Problemas comuns

Rodar o mesmo comando de novo é seguro: o que já foi feito é mantido.

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "A virtualização está desligada na BIOS/UEFI" | Opção desligada no computador | Ligue "Intel VT-x"/"Virtualization Technology" ou "AMD-V/SVM" na BIOS e rode de novo |
| A instalação não continuou depois de reiniciar | Entrou com outro usuário do Windows | Entre com o mesmo usuário e rode o comando de novo |
| "O Docker não ligou em 10 minutos" | Primeira partida lenta ou WSL desatualizado | Abra o Docker Desktop, espere "Engine running" e rode de novo; se não ligar, `wsl --update` |
| "failed to copy", "connection reset by peer" ou "i/o timeout" durante o download (às vezes com `...:3128`, o proxy interno do Docker) | A rede caiu no meio de um download grande (a imagem do Ollama tem 3,4 GB) | O instalador já tenta 5 vezes, continuando de onde parou. Se mesmo assim parar, rode o mesmo comando de novo. Se cair sempre, a rede (Wi-Fi instável, rede corporativa, proxy ou firewall) corta downloads longos: use outra rede (o roteador do celular serve) ou configure o proxy em Docker Desktop › Settings › Resources › Proxies |
| "port is already allocated" | Outro programa usa 5001, 5010, 5678, 8000 ou 14333 | `Get-NetTCPConnection -LocalPort 5678` mostra qual; feche o programa ou pare o outro container |
| Container reinicia sozinho ou sai com código 137 | Pouca memória | Feche programas pesados; no Docker Desktop › Settings › Resources, deixe pelo menos 6 GB |
| Pulou a criação do acesso (ou fechou a janela) | — | Na pasta da instalação: `pwsh -File primeiro-acesso.ps1` |
| Webhook da IA responde 404 | Workflow não publicado | Rode o instalador de novo (ele publica o workflow da IA acadêmica) |
| A primeira análise demora uns 12 s | O modelo é carregado depois de 30 min parado | Normal; as seguintes levam poucos segundos |

## 7. Configurar o fluxo

Gmail, remetentes, alertas, chaves, outras pessoas, Telegram/WhatsApp e o assistente da IA:
[`GUIA-CONFIGURACAO.md`](GUIA-CONFIGURACAO.md). Sem o Gmail, todo o resto funciona com a base fictícia.
