# Prova de recuperação com TDE: o backup do SIGpAcademic levado para OUTRO SQL Server
#   1. sem o certificado do TDE: a restauração é recusada (o backup roubado não abre);
#   2. com o certificado (segredos-locais/tde, fora do Git) e a senha dele: a restauração funciona, o DBCC CHECKDB não acha
#      erro e as linhas batem com o banco de origem.
# O "outro servidor" é um SQL Server 2022 novo e descartável (container apagado no fim). Nada muda no banco de origem: o
# backup é COPY_ONLY. Senhas vêm do .env.academic por variável de ambiente; nenhuma é gravada.
# Saída: sqlserver/evidence/parte3/restauracao-tde.json
# Uso, na raiz do projeto:  pwsh -File docs/entrega-academica/sqlserver/testar-restauracao-tde.ps1 [-PastaCertificado <pasta>]
param([string]$PastaCertificado = '', [string]$Origem = 'sigp_sqlserver_academic')
$ErrorActionPreference = 'Stop'
$sql = $PSScriptRoot
$raiz = (Resolve-Path (Join-Path $sql '..\..\..')).Path
if (-not $PastaCertificado) {
  $PastaCertificado = @((Join-Path $raiz 'segredos-locais\tde'), (Join-Path (Split-Path $raiz) 'SIGp_n8n_backups\tde-certificado')) |
    Where-Object { Test-Path (Join-Path $_ 'SIGpTDE.pvk') } | Select-Object -First 1
}
if (-not $PastaCertificado) { throw 'Certificado do TDE não encontrado (SIGpTDE.cer e SIGpTDE.pvk). Informe -PastaCertificado.' }
$v = @{}; Get-Content (Join-Path $sql '.env.academic') -Encoding utf8 | ForEach-Object { if ($_ -match '^([A-Z0-9_]+)=(.*)$') { $v[$matches[1]] = $matches[2] } }
foreach ($k in 'MSSQL_SA_PASSWORD', 'MSSQL_TDE_CERT_BACKUP_PASSWORD') { if (-not $v[$k]) { throw "$k não está no .env.academic." } }
$destino = 'sigp_sql_restauracao'
$tsql = '/opt/mssql-tools18/bin/sqlcmd'
function Dk([string[]]$a) {
  $antes = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { $s = & docker @a 2>&1; return @{ ok = ($LASTEXITCODE -eq 0); s = (($s | ForEach-Object { "$_" }) -join "`n") } } finally { $ErrorActionPreference = $antes }
}
# A senha vai por variável de ambiente herdada (docker exec -e SQLCMDPASSWORD, sem valor na linha de comando).
function Q([string]$c, [string]$senhaVar, [string]$consulta, [string]$banco = 'master') {
  $env:SQLCMDPASSWORD = $senhaVar
  try { return Dk @('exec', '-e', 'SQLCMDPASSWORD', $c, $tsql, '-S', 'localhost', '-U', 'sa', '-d', $banco, '-C', '-b', '-h', '-1', '-W', '-s', '|', '-Q', "SET NOCOUNT ON; $consulta") }
  finally { Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue }
}
# Lote com senha dentro: vai por arquivo temporário (apagado no Windows e no container), nunca na linha de comando.
function QArquivo([string]$c, [string]$senhaVar, [string]$texto) {
  $tmp = Join-Path $env:TEMP "sigp_rest_$PID.sql"
  [IO.File]::WriteAllText($tmp, "SET NOCOUNT ON;`n$texto", (New-Object Text.UTF8Encoding $true))
  $env:SQLCMDPASSWORD = $senhaVar
  try {
    Dk @('cp', $tmp, "${c}:/tmp/sigp_rest.sql") | Out-Null
    return Dk @('exec', '-e', 'SQLCMDPASSWORD', $c, $tsql, '-S', 'localhost', '-U', 'sa', '-C', '-b', '-i', '/tmp/sigp_rest.sql')
  } finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    Dk @('exec', '-u', 'root', $c, 'rm', '-f', '/tmp/sigp_rest.sql') | Out-Null
    Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue
  }
}
function Segredo { $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Fill($b); 'Rs' + [Convert]::ToBase64String($b).TrimEnd('=').Replace('+', 'x').Replace('/', 'y') + '#4b' }
$contagem = "SELECT 'Locais', COUNT(*) FROM app.Locais UNION ALL SELECT 'Notas', COUNT(*) FROM app.Notas UNION ALL SELECT 'ItensNota', COUNT(*) FROM app.ItensNota " +
            "UNION ALL SELECT 'Pagamentos', COUNT(*) FROM app.Pagamentos UNION ALL SELECT 'Conciliacoes', COUNT(*) FROM app.Conciliacoes UNION ALL SELECT 'Eventos', COUNT(*) FROM audit.Eventos;"
function Linhas([string]$s) { $o = [ordered]@{}; foreach ($l in $s -split "`n") { if ($l -match '^(\w+)\|(\d+)$') { $o[$matches[1]] = [int64]$matches[2] } }; return $o }

$res = [ordered]@{ executado_em_utc = (Get-Date).ToUniversalTime().ToString('s') + 'Z'; origem = $Origem }
$bak = Join-Path $env:TEMP "sigp_restauracao_$PID.bak"
$senhaNova = Segredo
try {
  # 1. backup da origem (TDE ligado: o arquivo sai criptografado)
  $r = Q $Origem $v['MSSQL_SA_PASSWORD'] "BACKUP DATABASE SIGpAcademic TO DISK = N'/var/opt/mssql/data/sigp_restauracao.bak' WITH COPY_ONLY, INIT, CHECKSUM;"
  if (-not $r.ok) { throw "backup falhou: $($r.s)" }
  Dk @('cp', "${Origem}:/var/opt/mssql/data/sigp_restauracao.bak", $bak) | Out-Null
  Dk @('exec', '-u', 'root', $Origem, 'rm', '-f', '/var/opt/mssql/data/sigp_restauracao.bak') | Out-Null
  $res.backup = [ordered]@{ tamanho_mb = [math]::Round((Get-Item $bak).Length / 1MB, 1); sha256 = (Get-FileHash $bak -Algorithm SHA256).Hash.Substring(0, 16) + '…'
                            tde_na_origem = ((Q $Origem $v['MSSQL_SA_PASSWORD'] "SELECT encryption_state FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID('SIGpAcademic');").s.Trim() -eq '3') }
  $res.linhas_origem = Linhas (Q $Origem $v['MSSQL_SA_PASSWORD'] $contagem 'SIGpAcademic').s
  # 2. "outro servidor": SQL Server 2022 novo, sem nada da origem
  Dk @('rm', '-f', $destino) | Out-Null
  $env:MSSQL_SA_PASSWORD = $senhaNova
  Dk @('create', '--name', $destino, '-e', 'ACCEPT_EULA=Y', '-e', 'MSSQL_PID=Developer', '-e', 'MSSQL_SA_PASSWORD', '-e', 'MSSQL_MEMORY_LIMIT_MB=2048', 'mcr.microsoft.com/mssql/server:2022-latest') | Out-Null
  Remove-Item Env:MSSQL_SA_PASSWORD
  Dk @('start', $destino) | Out-Null
  for ($i = 0; $i -lt 60 -and -not (Q $destino $senhaNova 'SELECT 1;').ok; $i++) { Start-Sleep 3 }
  Q $destino $senhaNova "EXEC sp_configure 'contained database authentication', 1; RECONFIGURE;" | Out-Null  # o SIGpAcademic é contido
  Dk @('cp', $bak, "${destino}:/var/opt/mssql/data/sigp_restauracao.bak") | Out-Null
  $restaurar = "RESTORE DATABASE SIGpAcademic FROM DISK = N'/var/opt/mssql/data/sigp_restauracao.bak' WITH CHECKSUM, RECOVERY;"
  # 3. sem o certificado: tem de falhar
  $r = Q $destino $senhaNova $restaurar
  $msg = ($r.s -split "`n" | Where-Object { $_ -match 'Msg \d+|certificate|thumbprint' } | Select-Object -First 3) -join ' '
  $res.sem_certificado = [ordered]@{ restaurou = $r.ok; erro = ([regex]::Match($r.s, 'Msg (\d+)').Groups[1].Value); mensagem = $msg.Substring(0, [Math]::Min(300, $msg.Length)) }
  # 4. com o certificado e a senha da chave privada (só aqui saem da pasta segura; apagados do container em seguida)
  foreach ($f in 'SIGpTDE.cer', 'SIGpTDE.pvk') { Dk @('cp', (Join-Path $PastaCertificado $f), "${destino}:/tmp/$f") | Out-Null }
  $chaveMestra = Segredo
  $cert = "CREATE MASTER KEY ENCRYPTION BY PASSWORD = N'$chaveMestra'; " +
          "CREATE CERTIFICATE SIGpTDE FROM FILE = N'/tmp/SIGpTDE.cer' WITH PRIVATE KEY (FILE = N'/tmp/SIGpTDE.pvk', DECRYPTION BY PASSWORD = N'$($v['MSSQL_TDE_CERT_BACKUP_PASSWORD'].Replace("'", "''"))');"
  $r = QArquivo $destino $senhaNova $cert
  Dk @('exec', '-u', 'root', $destino, 'rm', '-f', '/tmp/SIGpTDE.cer', '/tmp/SIGpTDE.pvk') | Out-Null
  if (-not $r.ok) { throw "não foi possível importar o certificado: $($r.s)" }
  $r = Q $destino $senhaNova $restaurar
  $res.com_certificado = [ordered]@{ restaurou = $r.ok }
  if ($r.ok) {
    $chk = Q $destino $senhaNova 'DBCC CHECKDB (SIGpAcademic) WITH NO_INFOMSGS, ALL_ERRORMSGS;'
    $res.com_certificado.checkdb_sem_erros = ($chk.ok -and -not ($chk.s -match 'Msg \d+'))
    $res.com_certificado.tde_no_destino = ((Q $destino $senhaNova "SELECT encryption_state FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID('SIGpAcademic');").s.Trim() -eq '3')
    $res.linhas_destino = Linhas (Q $destino $senhaNova $contagem 'SIGpAcademic').s
    $res.com_certificado.linhas_iguais = (($res.linhas_origem | ConvertTo-Json -Compress) -eq ($res.linhas_destino | ConvertTo-Json -Compress))
  }
} finally {
  Dk @('rm', '-f', $destino) | Out-Null
  Remove-Item $bak -Force -ErrorAction SilentlyContinue
}
$ok = (-not $res.sem_certificado.restaurou) -and $res.com_certificado.restaurou -and $res.com_certificado.checkdb_sem_erros -and $res.com_certificado.linhas_iguais -and $res.com_certificado.tde_no_destino
$res.resultado = if ($ok) { 'APROVADO' } else { 'REPROVADO' }
$saida = Join-Path $sql 'evidence\parte3\restauracao-tde.json'
[IO.File]::WriteAllText($saida, ($res | ConvertTo-Json -Depth 5) + "`n", (New-Object Text.UTF8Encoding $false))
Write-Host "  backup: $($res.backup.tamanho_mb) MB, TDE na origem: $($res.backup.tde_na_origem)"
Write-Host "  sem o certificado: restaurou = $($res.sem_certificado.restaurou) (erro $($res.sem_certificado.erro))"
Write-Host "  com o certificado: restaurou = $($res.com_certificado.restaurou), CHECKDB sem erros = $($res.com_certificado.checkdb_sem_erros), linhas iguais = $($res.com_certificado.linhas_iguais), TDE no destino = $($res.com_certificado.tde_no_destino)"
Write-Host "  linhas: $(($res.linhas_origem.GetEnumerator() | ForEach-Object { "$($_.Key) $($_.Value)" }) -join ', ')"
Write-Host "Resultado: $($res.resultado) · $saida"
# Documento para o relatório, a partir do que acabou de ser medido (nada digitado à mão).
$sim = { param($v) if ($v) { 'sim' } else { 'não' } }
$md = @(
  '# Recuperação com TDE: o backup em outro servidor, sem e com o certificado', '',
  "Gerado por ``sqlserver/testar-restauracao-tde.ps1`` em $($res.executado_em_utc) (evidência: ``sqlserver/evidence/parte3/restauracao-tde.json``).", '',
  'O backup do SIGpAcademic (COPY_ONLY, com CHECKSUM; o banco de origem não muda) foi levado para um SQL Server 2022 novo e',
  'descartável, como faria quem roubasse o arquivo. O certificado do TDE fica fora do banco e do Git (`segredos-locais/tde`),',
  'protegido por senha no `.env.academic`.', '',
  '| Verificação | Resultado |', '|---|---|',
  "| Tamanho do backup | $($res.backup.tamanho_mb) MB (SHA-256 $($res.backup.sha256)) |",
  "| TDE ligado na origem | $(& $sim $res.backup.tde_na_origem) |",
  "| **Sem o certificado:** restaurou? | **$(& $sim $res.sem_certificado.restaurou)** (erro $($res.sem_certificado.erro): o servidor não tem o certificado que protege a chave do banco) |",
  "| **Com o certificado e a senha dele:** restaurou? | **$(& $sim $res.com_certificado.restaurou)** |",
  "| DBCC CHECKDB sem erros | $(& $sim $res.com_certificado.checkdb_sem_erros) |",
  "| Linhas iguais às da origem | $(& $sim $res.com_certificado.linhas_iguais) ($(($res.linhas_origem.GetEnumerator() | ForEach-Object { "$($_.Key) $($_.Value)" }) -join ', ')) |",
  "| TDE continua ligado no destino | $(& $sim $res.com_certificado.tde_no_destino) |",
  "| **Resultado** | **$($res.resultado)** |", '',
  'Conclusão: um backup roubado não serve para nada sem o certificado; com o certificado, a empresa recupera o banco íntegro.',
  'Por isso o certificado e a senha dele ficam guardados juntos, num lugar seguro e separado dos backups.', ''
)
[IO.File]::WriteAllText((Join-Path (Split-Path $sql) 'seguranca\restauracao-tde.md'), ($md -join "`n"), (New-Object Text.UTF8Encoding $false))
if (-not $ok) { exit 1 }
