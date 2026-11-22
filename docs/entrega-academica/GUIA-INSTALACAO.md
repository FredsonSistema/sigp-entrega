# Guia de instalação para quem nunca usou o SIGp (Windows)

Este guia leva uma máquina sem nada instalado até o SIGp funcionando com a base fictícia, a IA local e o banco seguro.
Tempo: cerca de 30 minutos na primeira vez, quase todo de download. A versão da Entrega 2 deste guia está no histórico do Git.

## 1. O que você precisa

| Item | Mínimo | Para quê |
|---|---|---|
| Windows 10 ou 11 (64 bits), com virtualização ligada na BIOS | — | O Docker roda os serviços em Linux |
| Memória | 8 GB (16 GB recomendado) | SQL Server, IA local, n8n e a tela ao mesmo tempo |
| Disco livre | 15 GB | Imagens, modelos de IA e banco |
| Internet | só na instalação | Depois, tudo roda local; nenhum dado sai da máquina |

## 2. Instalar as ferramentas

Abra o **PowerShell** e rode, uma linha de cada vez (o `winget` já vem no Windows 10/11 atualizado):

```powershell
winget install -e --id Docker.DockerDesktop
winget install -e --id Microsoft.PowerShell
winget install -e --id Git.Git
```

Reinicie o computador. Abra o **Docker Desktop**, aceite os termos e espere aparecer "Engine running" (na primeira vez ele
pode pedir para instalar o WSL 2: aceite e reinicie de novo).

Só para a demonstração e os testes de avaliação (não precisa para usar o sistema):

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Microsoft.Sqlcmd
```

## 3. Baixar e instalar o SIGp

Abra o **PowerShell 7** (procure "pwsh" no menu Iniciar) e rode:

```powershell
cd $HOME\Documents
git clone https://github.com/FredsonSistema/sigp-entrega.git
cd sigp-entrega
pwsh -File instalar.ps1
```

O instalador mostra 7 etapas: Docker, chaves, containers, banco, modelos de IA, workflows e base fictícia. No fim aparece
"Pronto." com os endereços. Pode rodar de novo a qualquer momento: o que já existe é mantido.

O que ele cria na sua pasta, e que **nunca** deve ir para o Git nem ser mostrado na tela:

| Arquivo ou pasta | Conteúdo |
|---|---|
| `.env` | Chave da API do SIGp, chave mestra do cofre e chaves da IA |
| `docs/entrega-academica/sqlserver/.env.academic` | Senha do `sa` do SQL Server, senhas dos usuários da IA e do TDE |
| `segredos-locais/tde/` | Certificado do TDE: sem ele, nenhum backup do banco pode ser restaurado em outro computador |

Guarde esses três juntos num lugar seguro (um gerenciador de senhas, por exemplo), separados dos backups do banco.

## 4. Primeiro acesso

1. **Tela do SIGp:** abra http://127.0.0.1:8000/agencias.html. Na primeira vez, ela pede para criar o administrador. Informe
   a `SIGP_API_KEY`, que prova que você é o dono da instalação. Para copiá-la sem mostrar o arquivo inteiro:
   ```powershell
   (Select-String -Path .env -Pattern '^SIGP_API_KEY=(.*)$').Matches[0].Groups[1].Value | Set-Clipboard
   ```
   Cole no campo, escolha seu usuário e senha e entre.
2. **n8n:** abra http://127.0.0.1:5678 e crie a conta local do n8n (fica só na sua máquina).

## 5. Conferir que está funcionando

| O que conferir | Como | Esperado |
|---|---|---|
| Serviços | `docker ps --format "{{.Names}} {{.Status}}"` | 7 containers `sigp_*` com "Up" |
| API do SIGp | http://127.0.0.1:5001/api/health | `"status": "ok"` |
| IA acadêmica | http://127.0.0.1:5010/health | `"status": "ok"` e `"prompt_version": "3.1"` |
| Base fictícia | Tela › Cadastros › Agências | 3 agências "Fictícia" (e rodoviárias e garagem) |
| Faturas para associar | Tela › Notas recebidas | 3 faturas "Aguardando associação" |

Teste da IA pelo n8n (a primeira resposta leva cerca de 12 s, porque o modelo é carregado; as seguintes, poucos segundos):

```powershell
$f = '{"provider":"Conecta Alfa Fictícia","description":"IP adicional mensal","amount":"35.00"}'
Invoke-RestMethod -Method Post http://127.0.0.1:5678/webhook/sigp-academic-ai -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($f))
```

Esperado: `classification: DIVERGENTE` (o contrato não inclui IP adicional), as fontes do contrato em `source_ids` e
`automatic_payment: False`.

## 6. Demonstração e testes (opcional)

Com o Python e o sqlcmd instalados (passo 2):

```powershell
pwsh -File docs/entrega-academica/demo-final.ps1                # demonstração passo a passo (Enter entre os passos)
python docs/entrega-academica/ia/avaliar_ia.py depois           # 16 casos, injeção e validação cega
python docs/entrega-academica/sqlserver/testar_ia_perfis.py     # a IA não vaza o que o banco protege
python docs/entrega-academica/seguranca/verificar_ledger.py     # trilha à prova de adulteração
python -m pip install -r requirements.txt; python -m unittest discover -s tests   # testes unitários
```

O roteiro completo da apresentação está em [`roteiro-apresentacao.md`](roteiro-apresentacao.md).

## 7. Parar, religar e remover

```powershell
docker compose stop          # para tudo (os dados ficam)
docker compose start         # liga de novo
docker compose down          # remove os containers (os dados ficam nos volumes)
docker compose down -v       # remove TUDO, inclusive o banco e os modelos baixados (não tem volta)
```

## 8. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "O Docker não está respondendo" | Docker Desktop fechado | Abra o Docker Desktop, espere "Engine running" e rode o instalador de novo |
| "port is already allocated" | Outro programa usa 5001, 5010, 5678, 8000 ou 14333 | `Get-NetTCPConnection -LocalPort 5678` mostra qual; feche o programa ou pare o outro container |
| Container reinicia sozinho ou sai com código 137 | Pouca memória | Feche programas pesados; no Docker Desktop › Settings › Resources, deixe pelo menos 6 GB |
| "não pode ser carregado porque a execução de scripts foi desabilitada" | Política do PowerShell | `pwsh -ExecutionPolicy Bypass -File instalar.ps1` |
| Webhook da IA responde 404 | Workflow não publicado | Rode o instalador de novo (ele publica o workflow da IA acadêmica) |
| A primeira análise demora uns 12 s | O modelo é carregado depois de 30 min parado | Normal; as seguintes levam poucos segundos |
| A tela pede a chave de novo | Sessão expirada | Entre com o usuário e a senha criados no primeiro acesso |

## 9. Ligar o Gmail (opcional)

A busca de faturas no Gmail exige uma conta Google conectada ao n8n, com login no Google (não dá para automatizar). Sem ela,
todo o resto funciona com a base fictícia. Passo a passo: seção "Conectar o Gmail" do [`README`](../../README.md).
