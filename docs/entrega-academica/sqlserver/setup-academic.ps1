$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$composeFile = "docs/entrega-academica/sqlserver/compose.academic.yml"
$secretFile = "docs/entrega-academica/sqlserver/.env.academic"
$rootEnvFile = ".env"
$provisionFile = "docs/entrega-academica/sqlserver/.provision-ai-users.sql"
$workflowFile = "docs/entrega-academica/ia/n8n_workflow_academic_ai.json"
$evidenceDir = "docs/entrega-academica/sqlserver/evidence"

Set-Location $repoRoot

function Read-EnvFile([string]$Path) {
    $values = @{}
    if (Test-Path $Path) {
        foreach ($line in Get-Content -LiteralPath $Path) {
            if ($line -match '^([A-Z0-9_]+)=(.*)$') {
                $values[$Matches[1]] = $Matches[2]
            }
        }
    }
    return $values
}

function Write-EnvFile([string]$Path, [hashtable]$Values) {
    $lines = @()
    if (Test-Path $Path) {
        $lines = @(Get-Content -LiteralPath $Path | Where-Object { $_ -notmatch '^[A-Z0-9_]+=' })
    }
    foreach ($key in ($Values.Keys | Sort-Object)) {
        $lines += "$key=$($Values[$key])"
    }
    [System.IO.File]::WriteAllLines(
        (Join-Path $repoRoot $Path),
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function New-RandomSecret([int]$Length) {
    $alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#%*-_"
    $chars = [char[]]::new($Length)
    $randomBytes = [byte[]]::new($Length)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($randomBytes)
    }
    finally {
        $generator.Dispose()
    }
    for ($i = 0; $i -lt $Length; $i++) {
        $chars[$i] = $alphabet[[int]$randomBytes[$i] % $alphabet.Length]
    }
    return -join $chars
}

function New-ApiKey {
    $randomBytes = [byte[]]::new(32)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($randomBytes)
    }
    finally {
        $generator.Dispose()
    }
    return -join ($randomBytes | ForEach-Object { $_.ToString("x2") })
}

function Invoke-DockerCompose([string[]]$Arguments) {
    & docker compose --env-file $secretFile -f $composeFile @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose falhou ao executar: $($Arguments -join ' ')"
    }
}

function Invoke-Sqlcmd([string[]]$Arguments) {
    & sqlcmd @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "sqlcmd falhou ao executar: $($Arguments -join ' ')"
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI não encontrado. Instale e inicie o Docker Desktop."
}
if (-not (Get-Command sqlcmd -ErrorAction SilentlyContinue)) {
    throw "sqlcmd não encontrado. Instale as ferramentas de linha de comando do SQL Server."
}

$academicEnv = Read-EnvFile $secretFile
if (-not $academicEnv["MSSQL_SA_PASSWORD"]) {
    $academicEnv["MSSQL_SA_PASSWORD"] = New-RandomSecret 36
}
if (-not $academicEnv["SIGP_AI_API_KEY"]) {
    $academicEnv["SIGP_AI_API_KEY"] = New-ApiKey
}
if (-not $academicEnv["SIGP_AI_DB_PASSWORD_LOC001"]) {
    $academicEnv["SIGP_AI_DB_PASSWORD_LOC001"] = New-RandomSecret 32
}
if (-not $academicEnv["SIGP_AI_DB_PASSWORD_LOC002"]) {
    $academicEnv["SIGP_AI_DB_PASSWORD_LOC002"] = New-RandomSecret 32
}
Write-EnvFile $secretFile $academicEnv

$rootEnv = Read-EnvFile $rootEnvFile
$rootEnv["SIGP_ACADEMIC_AI_KEY"] = $academicEnv["SIGP_AI_API_KEY"]
Write-EnvFile $rootEnvFile $rootEnv

# O compose acadêmico usa duas redes externas. A do n8n nasce com o projeto principal "sigp_n8n"
# (nome fixo, para funcionar em qualquer pasta clonada); a acadêmica é criada aqui se não existir.
& docker compose -p sigp_n8n up -d n8n
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível subir o serviço n8n da composição principal."
}
& docker network inspect sqlserver_default *> $null
if ($LASTEXITCODE -ne 0) {
    & docker network create sqlserver_default | Out-Null
}
Invoke-DockerCompose @("up", "-d", "sqlserver-academic")
$env:SQLCMDPASSWORD = $academicEnv["MSSQL_SA_PASSWORD"]
$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        & sqlcmd -S 127.0.0.1,14333 -U sa -d master -C -b -Q "SELECT 1" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
    }
    catch {
    }
    Start-Sleep -Seconds 3
}
if (-not $ready) {
    throw "SQL Server não ficou pronto dentro do prazo."
}

Invoke-Sqlcmd @(
    "-S", "127.0.0.1,14333", "-U", "sa", "-d", "master", "-C", "-I", "-f", "65001", "-b",
    "-i", "docs/entrega-academica/sqlserver/01_schema_seed.sql"
)

$sqlPassword001 = $academicEnv["SIGP_AI_DB_PASSWORD_LOC001"].Replace("'", "''")
$sqlPassword002 = $academicEnv["SIGP_AI_DB_PASSWORD_LOC002"].Replace("'", "''")
$provisionSql = @"
USE SIGpAcademic;
IF EXISTS (
    SELECT 1 FROM sys.security_policies
    WHERE object_id = OBJECT_ID(N'security.LocalScopePolicy')
)
    DROP SECURITY POLICY security.LocalScopePolicy;
DROP FUNCTION security.fn_local_scope;
IF OBJECT_ID(N'security.fn_local_scope_escrita') IS NOT NULL DROP FUNCTION security.fn_local_scope_escrita;
GO
EXEC sp_configure 'contained database authentication', 1;
RECONFIGURE;
ALTER DATABASE SIGpAcademic SET CONTAINMENT = PARTIAL;
GO
USE SIGpAcademic;
GO
IF DATABASE_PRINCIPAL_ID(N'sigp_ia_loc001') IS NOT NULL DROP USER sigp_ia_loc001;
IF DATABASE_PRINCIPAL_ID(N'sigp_ia_loc002') IS NOT NULL DROP USER sigp_ia_loc002;
CREATE USER sigp_ia_loc001 WITH PASSWORD = N'$sqlPassword001', DEFAULT_SCHEMA = ai;
CREATE USER sigp_ia_loc002 WITH PASSWORD = N'$sqlPassword002', DEFAULT_SCHEMA = ai;
ALTER ROLE sigp_ia ADD MEMBER sigp_ia_loc001;
ALTER ROLE sigp_ia ADD MEMBER sigp_ia_loc002;
GO
"@
[System.IO.File]::WriteAllText(
    (Join-Path $repoRoot $provisionFile),
    $provisionSql,
    [System.Text.UTF8Encoding]::new($false)
)
try {
    Invoke-Sqlcmd @(
        "-S", "127.0.0.1,14333", "-U", "sa", "-d", "master", "-C", "-I", "-f", "65001", "-b",
        "-i", $provisionFile
    )
}
finally {
    Remove-Item -LiteralPath $provisionFile -Force -ErrorAction SilentlyContinue
}

Invoke-Sqlcmd @(
    "-S", "127.0.0.1,14333", "-U", "sa", "-d", "master", "-C", "-I", "-f", "65001", "-b",
    "-i", "docs/entrega-academica/sqlserver/01_schema_seed.sql"
)

# Auditoria nativa do SQL Server: registra também as tentativas negadas (o gatilho só vê o que foi gravado).
Invoke-Sqlcmd @(
    "-S", "127.0.0.1,14333", "-U", "sa", "-d", "master", "-C", "-I", "-f", "65001", "-b",
    "-i", "docs/entrega-academica/sqlserver/13_sql_server_audit.sql"
)

# Mascaramento dinâmico (chave fiscal e referência do pagamento). Antes era rodado à mão; a avaliação de vulnerabilidades
# (V23) mostrou que uma instalação nova ficava sem ele.
Invoke-Sqlcmd @(
    "-S", "127.0.0.1,14333", "-U", "sa", "-d", "master", "-C", "-I", "-f", "65001", "-b",
    "-i", "docs/entrega-academica/sqlserver/07_mascaramento_parte2.sql"
)

Invoke-Sqlcmd @(
    "-S", "127.0.0.1,14333", "-U", "sa", "-d", "SIGpAcademic", "-C", "-I", "-f", "65001", "-b",
    "-i", "docs/entrega-academica/sqlserver/02_security_tests.sql"
)

# TDE (arquivo e backups criptografados). O certificado vai para segredos-locais/tde, fora do Git: guarde junto com o .env.academic.
& pwsh -NoProfile -File "docs/entrega-academica/sqlserver/ativar-tde.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível ligar o TDE."
}

# Correções da avaliação de vulnerabilidades (18 e 19): acesso remoto, BUILTIN\Administrators, auditoria de logins e TLS
# obrigatório em toda conexão. Reinicia o SQL Server.
& pwsh -NoProfile -File "docs/entrega-academica/sqlserver/corrigir-vulnerabilidades.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível aplicar as correções de segurança do banco."
}

Invoke-DockerCompose @("up", "-d", "--build", "ollama-academic", "academic-ai")
$ollamaReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        & docker exec sigp_ollama_academic ollama list 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ollamaReady = $true
            break
        }
    }
    catch {
    }
    Start-Sleep -Seconds 3
}
if (-not $ollamaReady) {
    throw "Ollama não ficou pronto dentro do prazo."
}

& docker exec sigp_ollama_academic ollama pull qwen2.5:0.5b
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível baixar o modelo local qwen2.5:0.5b."
}
# Modelo de embedding da busca (ia/rag-embeddings.md). Sem ele a IA usa a busca lexical.
& docker exec sigp_ollama_academic ollama pull embeddinggemma
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível baixar o modelo de embedding embeddinggemma."
}

$aiReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:5010/health" -TimeoutSec 5
        if ($health.status -eq "ok") {
            $aiReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 3
    }
}
if (-not $aiReady) {
    throw "O serviço acadêmico de IA não ficou pronto."
}

& docker compose -p sigp_n8n up -d n8n
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível reiniciar o serviço n8n da composição principal."
}
$containerWorkflow = "/tmp/sigp-academic-ai-workflow.json"
& docker cp $workflowFile "sigp_n8n:$containerWorkflow"
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível copiar o workflow para o n8n."
}
& docker exec sigp_n8n n8n import:workflow --input=$containerWorkflow
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível importar o workflow acadêmico no n8n."
}

# Publica (ativa) o workflow pelo id fixo do JSON e reinicia o n8n para registrar o webhook.
& docker exec sigp_n8n n8n publish:workflow --id=R7lKILedIMV89Jay
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível publicar o workflow acadêmico no n8n."
}
& docker restart sigp_n8n | Out-Null
Write-Host "SQL Server, serviço IA, modelo local e workflow importado e publicado."
Write-Host "Teste: POST http://127.0.0.1:5678/webhook/sigp-academic-ai (ver docs/entrega-academica/ENDPOINTS.md). Casos de avaliação:"
Write-Host "  python docs\\entrega-academica\\ia\\avaliar_ia.py  (a chave vem do .env.academic)"
