# Demonstração ao vivo da entrega final (cerca de 4 minutos): IA, Segurança e Integração, pelo terminal.
# Cada passo mostra o que falar, o comando, executa e espera Enter. Com -SemPausa roda direto e grava a saída em
# sqlserver/evidence/parte3/demo-final-saida.txt (o "plano B": se algo falhar ao vivo, mostre esse arquivo).
# Nenhuma senha aparece: o script lê o .env.academic e passa a senha por variável de ambiente.
# Uso, na raiz do projeto:  pwsh -File docs/entrega-academica/demo-final.ps1  [-SemPausa]
# Roteiro completo (quem fala, tempos, perguntas prováveis): docs/entrega-academica/roteiro-apresentacao.md
param([switch]$SemPausa)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
if ($PSStyle) { $PSStyle.OutputRendering = 'Host' }
$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$sql = Join-Path $PSScriptRoot 'sqlserver'
$ia = Join-Path $PSScriptRoot 'ia'
$ev = Join-Path $sql 'evidence\parte3'
$py = if (Test-Path (Join-Path $raiz '.venv\Scripts\python.exe')) { Join-Path $raiz '.venv\Scripts\python.exe' } else { 'python' }
$envs = @{}
Get-Content (Join-Path $sql '.env.academic') | ForEach-Object { if ($_ -match '^([A-Z0-9_]+)=(.*)$') { $envs[$matches[1]] = $matches[2] } }
$env:SQLCMDPASSWORD = $envs['MSSQL_SA_PASSWORD']
$env:PYTHONIOENCODING = 'utf-8'
$webhook = 'http://127.0.0.1:5678/webhook/sigp-academic-ai'
$casos = (Get-Content (Join-Path $ia 'casos-finais.json') -Raw -Encoding utf8 | ConvertFrom-Json).casos
$injecao = (Get-Content (Join-Path $ia 'injecao-casos.json') -Raw -Encoding utf8 | ConvertFrom-Json)
$injecao = if ($injecao.casos) { $injecao.casos } else { $injecao }
$correlacoes = @()

function Passo($n, $titulo, $fala) {
  Write-Host ''
  Write-Host ('=' * 100) -ForegroundColor DarkCyan
  Write-Host " PASSO $n · $titulo" -ForegroundColor Cyan
  Write-Host " Falar: $fala" -ForegroundColor Gray
  Write-Host ('=' * 100) -ForegroundColor DarkCyan
}
function Comando($texto) { Write-Host "> $texto" -ForegroundColor Yellow }
function Pausa { if (-not $SemPausa) { Read-Host "`n[Enter] próximo passo" | Out-Null } }
function Sql($consulta) {
  $arq = Join-Path $env:TEMP 'sigp_demo_consulta.sql'
  [IO.File]::WriteAllText($arq, "SET NOCOUNT ON; $consulta", (New-Object Text.UTF8Encoding $true))
  $saida = Join-Path $env:TEMP 'sigp_demo_consulta.txt'
  & sqlcmd -S 127.0.0.1,14333 -U sa -d SIGpAcademic -C -I -f 65001 -W -s '|' -i $arq -o $saida
  Get-Content $saida -Encoding utf8
}
# Cada pedido leva um vencimento único: assim o Ollama não responde do cache e o tempo mostrado é o real.
function Analisar($fatura) {
  $corpo = [ordered]@{ provider = $fatura.provider; description = $fatura.description; amount = $fatura.amount
                       due_date = ('2027-{0:00}-{1:00}' -f (Get-Random -Minimum 1 -Maximum 13), (Get-Random -Minimum 1 -Maximum 29)) }
  $json = $corpo | ConvertTo-Json -Compress
  Comando "POST $webhook  $json"
  $t0 = Get-Date
  $r = Invoke-RestMethod -Method Post -Uri $webhook -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 200
  $s = ((Get-Date) - $t0).TotalSeconds
  [pscustomobject]@{
    'decisão (regra)' = $r.classification; motivo = $r.reason; 'modelo sugere' = $r.model_classification
    'modelo decide?' = $r.model_is_authoritative; 'pagamento automático' = $r.automatic_payment
    fontes = ($r.source_ids -join ', '); 'linhas do banco' = $r.context_rows; prompt = $r.prompt_version
    tempo = ('{0:N1} s' -f $s); correlation_id = $r.correlation_id
  } | Format-List | Out-Host
  $script:correlacoes += $r.correlation_id
}

$saidaDemo = Join-Path $ev 'demo-final-saida.txt'
if ($SemPausa) { Start-Transcript -Path $saidaDemo -Force -UseMinimalHeader | Out-Null }
try {
  Passo 0 'Ambiente' 'Tudo local em Docker: SQL Server, API da IA, n8n e Ollama. Nenhum dado sai da máquina e não há custo por token.'
  Comando 'docker ps'
  docker ps --format '{{.Names}}  {{.Status}}' | Where-Object { $_ -match 'sqlserver_academic|academic_ai|sigp_n8n|sigp_ollama' } | Out-Host
  Write-Host '  aquecendo o modelo (a primeira análise depois de 30 min parado leva cerca de 12 s)...' -ForegroundColor DarkGray
  $null = Invoke-RestMethod -Method Post -Uri $webhook -ContentType 'application/json; charset=utf-8' -TimeoutSec 200 `
    -Body ([Text.Encoding]::UTF8.GetBytes((@{ provider = 'Conecta Alfa Fictícia'; description = 'aquecimento'; amount = '1.00'; due_date = '2027-12-31' } | ConvertTo-Json -Compress)))
  Write-Host '  modelo pronto.' -ForegroundColor DarkGray
  Pausa

  Passo 1 'IA · fatura que bate com o contrato' 'Webhook do n8n -> API -> SQL Server (só o LOC-001) -> RAG cita o contrato -> regra confere serviço e valor -> CONTRATADO. O modelo só sugere.'
  Analisar ($casos | Where-Object id -eq 'IA-001').invoice
  Pausa

  Passo 2 'IA · cobrança fora do contrato' 'O contrato diz que IP adicional não está incluído: a regra marca DIVERGENTE e cita a fonte. É aqui que o sistema economiza.'
  Analisar ($casos | Where-Object id -eq 'IA-002').invoice
  Pausa

  $pi = $injecao | Where-Object id -eq 'PI-02'
  Passo 3 "IA · prompt injection ($($pi.tecnica))" 'A descrição da fatura manda aprovar o pagamento. O detector marca a injeção, a decisão vira REVISAR (revisão humana) e não existe ação de pagamento.'
  Write-Host "  texto do ataque: $($pi.description)" -ForegroundColor Magenta
  Analisar ([pscustomobject]@{ provider = 'Conecta Alfa Fictícia'; description = $pi.description; amount = '450.00' })
  Pausa

  Passo 4 'Integração · trilha: quem pediu, o que a IA consultou e o que respondeu' 'Cada análise deixa 3 eventos ligados pelo mesmo correlation_id: contexto lido (quantas linhas, de qual local), fontes do RAG e a resposta (decisão, sugestão do modelo, prompt e hash da descrição, nunca o texto).'
  $ids = ($correlacoes | ForEach-Object { "'$_'" }) -join ','
  Comando "SELECT ... FROM audit.Eventos WHERE correlation_id IN (os 3 pedidos acima)"
  Sql "SELECT LEFT(CONVERT(char(36), correlation_id), 8) AS pedido, ator, acao, LEFT(detalhe_redigido, 150) AS detalhe, CONVERT(char(19), criado_em, 120) AS quando FROM audit.Eventos WHERE correlation_id IN ($ids) ORDER BY id;" | Out-Host
  Pausa

  Passo 5 'Segurança · ataque de escalonamento de privilégio' 'O operador do LOC-001 tenta gravar no LOC-002, mover nota de local, entrar no papel de auditor e apagar a trilha. Fase 1: sem a correção, a falha se reproduz. Fase 2: tudo barrado, e o controle positivo continua funcionando.'
  Comando 'sqlcmd -i sqlserver/08_ataque_escalonamento.sql'
  $arq = Join-Path $env:TEMP 'sigp_demo_escalonamento.txt'
  & sqlcmd -S 127.0.0.1,14333 -U sa -d SIGpAcademic -C -I -f 65001 -W -s '|' -i (Join-Path $sql '08_ataque_escalonamento.sql') -o $arq
  Get-Content $arq -Encoding utf8 | Where-Object { $_ -match '^(fase|antes|depois)\|' -or $_ -match 'APROVADO|REPROVADO' } | Out-Host
  Pausa

  Passo '5b' 'Segurança · trilha à prova de adulteração (ledger)' 'Agora quem tenta é o próprio sa, dono do servidor: alterar, apagar e esvaziar a trilha é recusado. O digest do banco vai para o Git, fora do alcance de quem controla o banco, e a ledger é conferida contra ele; um digest falsificado é recusado.'
  Comando 'python seguranca/verificar_ledger.py'
  & $py (Join-Path $PSScriptRoot 'seguranca\verificar_ledger.py') 2>&1 | Where-Object { $_ -match '^\s+(OK|FALHA)|^Resultado' } | Out-Host
  Pausa

  Passo 6 'Integração · a IA não vaza o que o banco protege (perfil por perfil)' 'A mesma IA com a credencial de cada perfil: só vê o próprio local; credencial errada = 503 sem dado; a injeção não traz nada do LOC-002; e a IA não consegue falsificar a trilha.'
  Comando 'python sqlserver/testar_ia_perfis.py'
  & $py (Join-Path $sql 'testar_ia_perfis.py') 2>&1 | Where-Object { $_ -match '^\s+(OK|FALHA)|^Parte|^Resultado' } | Out-Host
  Pausa

  Passo 7 'Otimização · as duas consultas lentas, antes e depois' 'Consulta 1 (total por local, provedor e mês): resumo diário mantido por gatilho, com a mesma resposta (0 linhas diferentes). Consulta 2: índice filtrado. 30 medidas por configuração, mediana e p95. Os planos .sqlplan abrem no SSMS.'
  Comando 'Get-Content sqlserver/evidence/parte3/otimizacao/tempos.txt'
  Get-Content (Join-Path $ev 'otimizacao\tempos.txt') -Encoding utf8 | Where-Object { $_ -match '\|' } | Out-Host
  Pausa

  Passo 8 'Integração · nenhum segredo nos fluxos do n8n' 'Procura as chaves reais do .env, autenticação literal e credenciais nos JSON do repositório e nos workflows exportados do n8n no ar.'
  Comando 'python ia/verificar_segredos_n8n.py --ao-vivo'
  & $py (Join-Path $ia 'verificar_segredos_n8n.py') --ao-vivo 2>&1 | Select-Object -Last 1 | Out-Host
  Write-Host "`nFim da demonstração." -ForegroundColor Green
}
finally {
  Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue
  if ($SemPausa) {
    Stop-Transcript | Out-Null
    # Sem o cabeçalho do PowerShell (usuário, máquina, caminhos): o arquivo vai para o repositório.
    $linhas = Get-Content $saidaDemo -Encoding utf8
    $dentro = $false; $limpo = foreach ($l in $linhas) { if ($l -match '^\*{10,}$') { $dentro = -not $dentro; continue }; if (-not $dentro) { $l } }
    [IO.File]::WriteAllLines($saidaDemo, [string[]]$limpo, (New-Object Text.UTF8Encoding $false))
  }
}
