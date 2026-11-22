# Liga o TDE no SIGpAcademic (17_tde.sql), guarda o certificado fora do banco e do Git, e prova com um backup sem compressão
# que a chave fiscal não aparece mais em texto puro. Só precisa do Docker (usa o sqlcmd de dentro do container).
# Uso, na raiz do projeto:  pwsh -File docs/entrega-academica/sqlserver/ativar-tde.ps1 [-PastaCertificado <pasta fora do Git>]
# Sem -PastaCertificado: <raiz>/segredos-locais/tde (ignorada pelo Git). SEM ESSE CERTIFICADO, NENHUM BACKUP CRIPTOGRAFADO
# PODE SER RESTAURADO EM OUTRO SERVIDOR: guarde a pasta junto com o .env.academic, longe dos backups do banco.
param([string]$PastaCertificado = '', [string]$BackupAntes = '')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$sql = $PSScriptRoot
$raiz = (Resolve-Path (Join-Path $sql '..\..\..')).Path
if (-not $PastaCertificado) { $PastaCertificado = Join-Path $raiz 'segredos-locais\tde' }
$envArq = Join-Path $sql '.env.academic'
$ev = Join-Path $sql 'evidence\parte3'
$c = 'sigp_sqlserver_academic'

function Segredo { $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Fill($b); 'Tde' + [Convert]::ToBase64String($b).TrimEnd('=').Replace('+', 'x').Replace('/', 'y') + '#7a' }
function Contar([string]$arquivo) {
  # A chave sintética é NVARCHAR (UTF-16): procura os bytes nos dois alinhamentos.
  $b = [IO.File]::ReadAllBytes($arquivo)
  $t = [Text.Encoding]::Unicode.GetString($b)
  $u = [Text.Encoding]::Unicode.GetString($b, 1, $b.Length - 1)
  return ([regex]::Matches($t, 'SINTETICA-CHAVE-')).Count + ([regex]::Matches($u, 'SINTETICA-CHAVE-')).Count
}

# 1. senhas do TDE no .env.academic (geradas uma vez, nunca mostradas)
$linhas = [Collections.Generic.List[string]](Get-Content $envArq -Encoding utf8)
$v = @{}; foreach ($l in $linhas) { if ($l -match '^([A-Z0-9_]+)=(.*)$') { $v[$matches[1]] = $matches[2] } }
foreach ($k in 'MSSQL_TDE_MASTER_KEY_PASSWORD', 'MSSQL_TDE_CERT_BACKUP_PASSWORD') { if (-not $v[$k]) { $v[$k] = Segredo; $linhas.Add("$k=$($v[$k])") } }
[IO.File]::WriteAllLines($envArq, [string[]]$linhas, (New-Object Text.UTF8Encoding $false))

# 2. roda o 17_tde.sql com as senhas num arquivo temporário (apagado em seguida, no Windows e no container)
$tmp = Join-Path $env:TEMP "sigp_tde_$PID.sql"
$conteudo = ":setvar TDE_MASTER_KEY_PASSWORD `"$($v['MSSQL_TDE_MASTER_KEY_PASSWORD'])`"`r`n:setvar TDE_CERT_BACKUP_PASSWORD `"$($v['MSSQL_TDE_CERT_BACKUP_PASSWORD'])`"`r`n" +
            [IO.File]::ReadAllText((Join-Path $sql '17_tde.sql')).TrimStart([char]0xFEFF)
$env:SQLCMDPASSWORD = $v['MSSQL_SA_PASSWORD']
try {
  [IO.File]::WriteAllText($tmp, $conteudo, (New-Object Text.UTF8Encoding $true))
  docker cp $tmp "${c}:/tmp/sigp_tde.sql" | Out-Null
  $saida = docker exec -e SQLCMDPASSWORD $c /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -d master -C -I -f 65001 -b -W -s '|' -i /tmp/sigp_tde.sql
  if ($LASTEXITCODE -ne 0) { throw "17_tde.sql falhou: $($saida | Select-Object -Last 3)" }
} finally {
  Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  docker exec -u root $c rm -f /tmp/sigp_tde.sql 2>$null
}
$estado = ($saida | Where-Object { $_ -match '^SIGpAcademic\|' } | Select-Object -Last 1)
Write-Host "  estado: $estado"

# 3. certificado exportado: para fora do volume do banco (e do Git)
docker exec $c test -f /var/opt/mssql/data/SIGpTDE.pvk 2>$null
if ($LASTEXITCODE -eq 0) {
  New-Item -ItemType Directory -Force -Path $PastaCertificado | Out-Null
  foreach ($f in 'SIGpTDE.cer', 'SIGpTDE.pvk') { docker cp "${c}:/var/opt/mssql/data/$f" (Join-Path $PastaCertificado $f) | Out-Null }
  docker exec -u root $c rm -f /var/opt/mssql/data/SIGpTDE.cer /var/opt/mssql/data/SIGpTDE.pvk
  Write-Host "  certificado guardado em $PastaCertificado (fora do Git) e retirado do volume do banco"
} else { Write-Host '  certificado já existia: nada exportado de novo' }

# 4. prova: backup sem compressão, procurando a chave fiscal sintética em texto puro
$bk = "verificacao-tde-$PID.bak"
$tmpBak = Join-Path $env:TEMP $bk
try {
  docker exec -e SQLCMDPASSWORD $c /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -d master -C -b -Q "BACKUP DATABASE SIGpAcademic TO DISK = N'/var/opt/mssql/data/$bk' WITH COPY_ONLY, INIT, NO_COMPRESSION" | Out-Null
  docker cp "${c}:/var/opt/mssql/data/$bk" $tmpBak | Out-Null
  $depois = Contar $tmpBak
} finally {
  docker exec -u root $c rm -f "/var/opt/mssql/data/$bk" 2>$null
  Remove-Item $tmpBak -Force -ErrorAction SilentlyContinue
  Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue
}
$antes = if ($BackupAntes -and (Test-Path $BackupAntes)) { Contar $BackupAntes } else { $null }
$res = [ordered]@{
  executado_em_utc = (Get-Date).ToUniversalTime().ToString('s')
  estado = $estado
  chave_fiscal_em_texto_no_backup_antes = $antes
  chave_fiscal_em_texto_no_backup_depois = $depois
  certificado_fora_do_banco = (Test-Path (Join-Path $PastaCertificado 'SIGpTDE.pvk'))
  resultado = if ($estado -match '\|3\|' -and $depois -eq 0) { 'APROVADO' } else { 'REPROVADO' }
}
$res | ConvertTo-Json | Set-Content (Join-Path $ev 'tde-verificacao.json') -Encoding utf8
Write-Host "  chave fiscal em texto puro no backup: antes $(if ($null -eq $antes) { '(não medido)' } else { $antes }) · depois $depois"
Write-Host "Resultado: $($res.resultado)"
if ($res.resultado -ne 'APROVADO') { exit 1 }
