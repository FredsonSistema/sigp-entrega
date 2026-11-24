# Instala o pacote da entrega do SIGp com um comando:  pwsh -File instalar.ps1
# Numa máquina sem nada instalado, use o instalar-sigp.ps1 (instala o WSL, o Docker e o PowerShell 7 e chama este).
# Aqui, precisa só do Docker Desktop ligado. Pode rodar de novo: o que já existe é mantido (chaves, banco, modelos).
#   -ModeloTriagem qwen2.5:3b   escolhe o modelo da triagem do Gmail (padrão: o do .env, ou o escolhido na medição)
#   -SemBaseFicticia            não grava a base de demonstração (locais, provedores e faturas inventados)
#   -ComVolume                  carrega as 100.020 notas sintéticas do benchmark (demora alguns minutos)
# Nenhuma chave vem no pacote: todas são geradas aqui, ficam no .env (ignorado pelo Git) e não são mostradas.
param([string]$ModeloTriagem = '', [switch]$SemBaseFicticia, [switch]$ComVolume)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$raiz = $PSScriptRoot
Set-Location $raiz
$envRaiz = Join-Path $raiz '.env'
$envAcademico = Join-Path $raiz 'docs\entrega-academica\sqlserver\.env.academic'
$modeloPadrao = 'qwen2.5:3b'  # escolha medida: docs/entrega-academica/ia/escolha-modelo-triagem.md (instalação leve: -ModeloTriagem qwen2.5:0.5b)

function Etapa($n, $texto) { Write-Host "`n[$n] $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "    ok: $texto" -ForegroundColor Green }
function Ler-Env([string]$caminho) {
  $v = [ordered]@{}
  if (Test-Path $caminho) { Get-Content $caminho -Encoding utf8 | ForEach-Object { if ($_ -match '^([A-Z0-9_]+)=(.*)$') { $v[$matches[1]] = $matches[2] } } }
  return $v
}
function Gravar-Env([string]$caminho, $valores, [string]$titulo) {
  $linhas = @("# $titulo", '# Gerado por instalar.ps1. Não envie este arquivo para o Git nem mostre na tela.')
  foreach ($k in $valores.Keys) { $linhas += "$k=$($valores[$k])" }
  New-Item -ItemType Directory -Force -Path (Split-Path $caminho) | Out-Null
  [IO.File]::WriteAllLines($caminho, [string[]]$linhas, (New-Object Text.UTF8Encoding $false))
}
function Segredo([int]$bytes = 32) {
  $b = New-Object byte[] $bytes
  [Security.Cryptography.RandomNumberGenerator]::Fill($b)
  return [Convert]::ToBase64String($b).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
# Senha do SQL Server: precisa de maiúscula, minúscula, número e símbolo.
function SenhaSql { return 'Sg' + (Segredo 24).Replace('-', 'x').Replace('_', 'y') + '#9a' }
function Esperar([string]$o, [scriptblock]$teste, [int]$segundos = 180) {
  $fim = (Get-Date).AddSeconds($segundos)
  while ((Get-Date) -lt $fim) { try { if (& $teste) { return } } catch { }; Start-Sleep 3 }
  throw "$o não ficou pronto em $segundos s. Veja: docker compose logs"
}
# Downloads grandes (imagens de ~3 GB, modelos de IA) caem em rede instável ou atrás de proxy/firewall. Tenta de novo:
# o Docker e o Ollama guardam o que já baixou, então cada tentativa continua de onde parou.
$mensagemRede = ('A conexão caiu várias vezes durante o download. O que já baixou fica guardado: rode o mesmo comando de novo. ' +
  'Se cair sempre no mesmo ponto, a rede (Wi-Fi instável, rede corporativa, proxy ou firewall) está cortando downloads longos: ' +
  'tente outra rede (por exemplo, o roteador do celular) ou, com proxy, configure-o em Docker Desktop > Settings > Resources > Proxies.')
function Repetir([string]$oque, [scriptblock]$comando, [int]$tentativas = 5, [int]$espera = 20) {
  for ($i = 1; $i -le $tentativas; $i++) {
    & $comando
    if ($LASTEXITCODE -eq 0) { return }
    if ($i -lt $tentativas) {
      Write-Host "    $oque falhou (tentativa $i de $tentativas), provavelmente a conexão caiu. Tentando de novo em $espera s; o que já baixou não é baixado outra vez." -ForegroundColor Yellow
      Start-Sleep $espera
    }
  }
  throw "$oque falhou $tentativas vezes. $mensagemRede"
}
function Sql([string]$arquivo, [string]$banco = 'master') {
  # Roda um script .sql com o sqlcmd de dentro do container (não precisa instalar nada no Windows).
  # A senha vai por variável de ambiente (docker exec -e SQLCMDPASSWORD, sem valor na linha de comando).
  docker cp $arquivo "sigp_sqlserver_academic:/tmp/sigp_script.sql" | Out-Null
  docker exec -e SQLCMDPASSWORD sigp_sqlserver_academic /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -d $banco -C -I -f 65001 -b -i /tmp/sigp_script.sql | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Falhou: $(Split-Path $arquivo -Leaf)" }
}

Etapa 1 'Docker'
docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) { throw 'O Docker não está respondendo. Abra o Docker Desktop e rode de novo.' }
Ok 'Docker ligado'

Etapa 2 'Chaves e senhas (geradas nesta máquina)'
$e = Ler-Env $envRaiz
$a = Ler-Env $envAcademico
if (-not $e['SIGP_API_KEY']) { $e['SIGP_API_KEY'] = 'sigp_' + (Segredo 24) }
if (-not $e['SIGP_COFRE_CHAVE']) { $e['SIGP_COFRE_CHAVE'] = Segredo 32 }  # 32 bytes do gerador criptográfico, base64 url-safe
if (-not $a['MSSQL_SA_PASSWORD']) { $a['MSSQL_SA_PASSWORD'] = SenhaSql }
if (-not $a['SIGP_AI_API_KEY']) { $a['SIGP_AI_API_KEY'] = 'ia_' + (Segredo 24) }
if (-not $a['SIGP_AI_DB_PASSWORD_LOC001']) { $a['SIGP_AI_DB_PASSWORD_LOC001'] = SenhaSql }
if (-not $a['SIGP_AI_DB_PASSWORD_LOC002']) { $a['SIGP_AI_DB_PASSWORD_LOC002'] = SenhaSql }
foreach ($k in 'MSSQL_SA_PASSWORD', 'SIGP_AI_API_KEY', 'SIGP_AI_DB_PASSWORD_LOC001') { $e[$k] = $a[$k] }
$e['SIGP_ACADEMIC_AI_KEY'] = $a['SIGP_AI_API_KEY']
if ($ModeloTriagem) { $e['SIGP_OLLAMA_MODEL'] = $ModeloTriagem } elseif (-not $e['SIGP_OLLAMA_MODEL']) { $e['SIGP_OLLAMA_MODEL'] = $modeloPadrao }
Gravar-Env $envRaiz $e 'SIGp (pacote da entrega): chaves da API, do cofre e do ambiente acadêmico'
Gravar-Env $envAcademico $a 'SIGp acadêmico: senha do sa, chave da IA e senhas dos usuários da IA'
Ok ".env e .env.academic prontos (valores não mostrados) · modelo da triagem: $($e['SIGP_OLLAMA_MODEL'])"

Etapa 3 'Containers (a primeira vez baixa as imagens e compila: alguns minutos)'
New-Item -ItemType Directory -Force -Path (Join-Path $raiz 'backend\data') | Out-Null
# Baixa e compila antes de subir, cada parte com novas tentativas (a falha de rede no meio não perde o que já veio).
Repetir 'Baixar as imagens' { docker compose pull --ignore-buildable }
Repetir 'Compilar a API, o OCR e a IA acadêmica' { docker compose build }
Repetir 'Subir os containers' { docker compose up -d } 3 10
Ok 'containers no ar'

Etapa 4 'SQL Server acadêmico: schema, RLS, mascaramento, ledger, usuários da IA e auditoria'
$env:SQLCMDPASSWORD = $a['MSSQL_SA_PASSWORD']
try {
  Esperar 'SQL Server' { docker exec -e SQLCMDPASSWORD sigp_sqlserver_academic /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -Q 'SELECT 1' *> $null; $LASTEXITCODE -eq 0 }
  $sql = Join-Path $raiz 'docs\entrega-academica\sqlserver'
  Sql (Join-Path $sql '01_schema_seed.sql')
  $p1 = $a['SIGP_AI_DB_PASSWORD_LOC001'].Replace("'", "''"); $p2 = $a['SIGP_AI_DB_PASSWORD_LOC002'].Replace("'", "''")
  $prov = Join-Path $env:TEMP "sigp_provisao_$PID.sql"
  @"
USE SIGpAcademic;
IF EXISTS (SELECT 1 FROM sys.security_policies WHERE object_id = OBJECT_ID(N'security.LocalScopePolicy')) DROP SECURITY POLICY security.LocalScopePolicy;
IF OBJECT_ID(N'security.fn_local_scope') IS NOT NULL DROP FUNCTION security.fn_local_scope;
GO
EXEC sp_configure 'contained database authentication', 1;
RECONFIGURE;
ALTER DATABASE SIGpAcademic SET CONTAINMENT = PARTIAL;
GO
USE SIGpAcademic;
GO
IF DATABASE_PRINCIPAL_ID(N'sigp_ia_loc001') IS NOT NULL DROP USER sigp_ia_loc001;
IF DATABASE_PRINCIPAL_ID(N'sigp_ia_loc002') IS NOT NULL DROP USER sigp_ia_loc002;
CREATE USER sigp_ia_loc001 WITH PASSWORD = N'$p1', DEFAULT_SCHEMA = ai;
CREATE USER sigp_ia_loc002 WITH PASSWORD = N'$p2', DEFAULT_SCHEMA = ai;
ALTER ROLE sigp_ia ADD MEMBER sigp_ia_loc001;
ALTER ROLE sigp_ia ADD MEMBER sigp_ia_loc002;
GO
"@ | Set-Content -Path $prov -Encoding utf8
  try { Sql $prov } finally { Remove-Item $prov -Force -ErrorAction SilentlyContinue; docker exec -u root sigp_sqlserver_academic rm -f /tmp/sigp_script.sql 2>$null }
  Sql (Join-Path $sql '01_schema_seed.sql')
  Sql (Join-Path $sql '13_sql_server_audit.sql')
  if ($ComVolume) { Write-Host '    carregando 100.020 notas sintéticas...'; Sql (Join-Path $sql '03_load_benchmark.sql') 'SIGpAcademic' }
  # TDE: arquivo e backups criptografados. O certificado vai para segredos-locais/tde (fora do Git): sem ele, nenhum backup
  # pode ser restaurado em outro servidor. Guarde essa pasta junto com o .env.
  & ([Diagnostics.Process]::GetCurrentProcess().MainModule.FileName) -NoProfile -ExecutionPolicy Bypass -File (Join-Path $sql 'ativar-tde.ps1') | Out-Host
  if ($LASTEXITCODE -ne 0) { throw 'Não foi possível ligar o TDE.' }
  docker exec -u root sigp_sqlserver_academic rm -f /tmp/sigp_script.sql 2>$null
} finally { Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue }
Ok 'banco acadêmico pronto (TDE ligado; certificado em segredos-locais/tde)'

Etapa 5 'Modelos de IA locais (Ollama)'
Esperar 'Ollama' { docker exec sigp_ollama ollama list *> $null; $LASTEXITCODE -eq 0 }
foreach ($m in @('qwen2.5:0.5b', $e['SIGP_OLLAMA_MODEL']) | Select-Object -Unique) {
  Write-Host "    baixando $m (só na primeira vez)..."
  Repetir "Baixar o modelo $m" { docker exec sigp_ollama ollama pull $m | Out-Null }
}
Ok 'modelos prontos'

Etapa 6 'Workflows do n8n'
Esperar 'n8n' { (Invoke-WebRequest 'http://127.0.0.1:5678/healthz/readiness' -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 }
# Credencial "Gmail account" vazia, com o mesmo id que os workflows do Gmail usam: depois é só colar o Client ID e o
# Client Secret nela e conectar (GUIA-CONFIGURACAO.md), sem escolher a credencial em cada nó. Se já existe, fica como
# está (reimportar apagaria a conexão com o Google).
$idGmail = '6w8cHAuUwpPVa6tb'
docker exec sigp_n8n sh -c "n8n export:credentials --id=$idGmail --output=/tmp/sigp_c.json >/dev/null 2>&1; r=`$?; rm -f /tmp/sigp_c.json; exit `$r" *> $null
if ($LASTEXITCODE -ne 0) {
  $vazia = Join-Path $env:TEMP "sigp_gmail_$PID.json"
  [IO.File]::WriteAllText($vazia, "[{`"id`":`"$idGmail`",`"name`":`"Gmail account`",`"type`":`"gmailOAuth2`",`"data`":{`"clientId`":`"`",`"clientSecret`":`"`"}}]")
  try {
    docker cp $vazia sigp_n8n:/tmp/sigp_gmail.json | Out-Null
    docker exec sigp_n8n n8n import:credentials --input=/tmp/sigp_gmail.json *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar a credencial do Gmail no n8n.' }
  } finally { Remove-Item $vazia -Force -ErrorAction SilentlyContinue; docker exec sigp_n8n rm -f /tmp/sigp_gmail.json *> $null }
}
$wfs = Get-ChildItem (Join-Path $raiz 'n8n\workflows') -Filter '*.json'
foreach ($w in $wfs) {
  docker cp $w.FullName "sigp_n8n:/tmp/$($w.Name)" | Out-Null
  docker exec sigp_n8n n8n import:workflow --input="/tmp/$($w.Name)" *> $null
  if ($LASTEXITCODE -ne 0) { throw "Não foi possível importar $($w.Name)." }
}
# Agora: a IA acadêmica, a leitura de fatura PDF da aba Faturas e a entrada manual de notas (WF-10) (não usam o Gmail). Os do Gmail (WF-08, WF-09, WF-06,
# WF-99) precisam da conta Google conectada: depois de conectar, ligar-gmail.ps1 (GUIA-CONFIGURACAO.md). Publicar sem a
# credencial faria o n8n registrar erro a cada leitura.
foreach ($id in 'R7lKILedIMV89Jay', 'LNCrxFxvHfdDkqL2', 'sigpWF10EntradaMan') {
  docker exec sigp_n8n n8n publish:workflow --id=$id *> $null
  if ($LASTEXITCODE -ne 0) { throw "Não foi possível publicar o workflow $id." }
}
docker restart sigp_n8n | Out-Null
Esperar 'n8n' { (Invoke-WebRequest 'http://127.0.0.1:5678/healthz/readiness' -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 }
Ok "$($wfs.Count) workflows importados; IA acadêmica, leitura de fatura PDF e entrada manual publicadas; credencial do Gmail pronta para conectar"

Etapa 7 'API do SIGp e base fictícia'
Esperar 'API do SIGp' { (Invoke-RestMethod 'http://127.0.0.1:5001/api/health' -TimeoutSec 5).status -eq 'ok' }
Esperar 'IA acadêmica' { (Invoke-RestMethod 'http://127.0.0.1:5010/health' -TimeoutSec 5).status -eq 'ok' }
if (-not $SemBaseFicticia) {
  docker exec sigp_api python /app/entrega/base_ficticia.py
  if ($LASTEXITCODE -ne 0) { Write-Host '    a base fictícia não foi gravada (veja a mensagem acima); o resto da instalação está pronto.' -ForegroundColor Yellow }
}

Etapa 8 'Seu acesso (tela do SIGp e n8n)'
# A senha é digitada pela pessoa e não aparece, não vai para a área de transferência nem para arquivo (primeiro-acesso.ps1).
try { & (Join-Path $raiz 'primeiro-acesso.ps1') }
catch { Write-Host "    $($_.Exception.Message)" -ForegroundColor Yellow; Write-Host '    Para criar o acesso depois: pwsh -File primeiro-acesso.ps1' -ForegroundColor Yellow }

Write-Host "`nPronto." -ForegroundColor Green
Write-Host '  Tela do SIGp:       http://127.0.0.1:8000/agencias.html  (entre com o usuário e a senha que você criou)'
Write-Host '  n8n:                http://127.0.0.1:5678                 (entre com o seu e-mail e a mesma senha)'
Write-Host '  IA acadêmica:       http://127.0.0.1:5010/health'
Write-Host '  Demonstração:       pwsh -File docs/entrega-academica/demo-final.ps1'
Write-Host '  Roteiro:            docs/entrega-academica/roteiro-apresentacao.md'
Write-Host '  Configurar Gmail, alertas e notificações: docs/entrega-academica/GUIA-CONFIGURACAO.md'
