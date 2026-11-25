# Aplica as correções da avaliação de vulnerabilidades no SQL Server acadêmico e reinicia o container para valerem.
#   1. 19_correcoes_vulnerabilidades.sql (acesso remoto, BUILTIN\Administrators, auditoria de logins);
#   2. criptografia obrigatória em toda conexão (mssql-conf network.forceencryption = 1; o SQL Server usa o certificado
#      que gera para si; os clientes do SIGp já conectam com TLS e -C, que confia nesse certificado);
#   3. reinicia o SQL Server e espera ele voltar.
# Idempotente. Uso, na raiz do projeto:  pwsh -File docs/entrega-academica/sqlserver/corrigir-vulnerabilidades.ps1
# Para o teste num SQL Server descartável: -Container <nome> -SenhaSa (lida do .env.academic se não for informada).
param([string]$Container = 'sigp_sqlserver_academic', [string]$SenhaSa = '')
$ErrorActionPreference = 'Stop'
$sql = $PSScriptRoot
if (-not $SenhaSa) {
  $linha = Get-Content (Join-Path $sql '.env.academic') -Encoding utf8 | Where-Object { $_ -match '^MSSQL_SA_PASSWORD=' } | Select-Object -First 1
  if (-not $linha) { throw 'MSSQL_SA_PASSWORD não está no .env.academic.' }
  $SenhaSa = $linha.Substring('MSSQL_SA_PASSWORD='.Length)
}
function Dk([string[]]$a) {
  $antes = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { $s = & docker @a 2>&1; return @{ ok = ($LASTEXITCODE -eq 0); s = ($s | ForEach-Object { "$_" }) -join "`n" } } finally { $ErrorActionPreference = $antes }
}
function Pronto {
  for ($i = 0; $i -lt 60; $i++) {
    if ((Dk @('exec', '-e', 'SQLCMDPASSWORD', $Container, '/opt/mssql-tools18/bin/sqlcmd', '-S', 'localhost', '-U', 'sa', '-C', '-b', '-Q', 'SELECT 1')).ok) { return }
    Start-Sleep 3
  }
  throw 'O SQL Server não voltou em 3 minutos. Veja: docker logs ' + $Container
}
$env:SQLCMDPASSWORD = $SenhaSa
try {
  Dk @('cp', (Join-Path $sql '19_correcoes_vulnerabilidades.sql'), "${Container}:/tmp/sigp_19.sql") | Out-Null
  $r = Dk @('exec', '-e', 'SQLCMDPASSWORD', $Container, '/opt/mssql-tools18/bin/sqlcmd', '-S', 'localhost', '-U', 'sa', '-C', '-I', '-f', '65001', '-b', '-i', '/tmp/sigp_19.sql')
  Dk @('exec', '-u', 'root', $Container, 'rm', '-f', '/tmp/sigp_19.sql') | Out-Null
  if (-not $r.ok) { throw "19_correcoes_vulnerabilidades.sql falhou:`n$($r.s)" }
  ($r.s -split "`n" | Where-Object { $_ -match '^V\d\d' }) | ForEach-Object { Write-Host "    $_" }
  # TLS obrigatório: o mssql-conf grava em /var/opt/mssql/mssql.conf (no volume do banco: vale depois de recriar o container).
  $conf = Dk @('exec', $Container, '/opt/mssql/bin/mssql-conf', 'get', 'network', 'forceencryption')
  if ($conf.s -notmatch 'forceencryption\s*:\s*1') {
    $r = Dk @('exec', $Container, '/opt/mssql/bin/mssql-conf', 'set', 'network.forceencryption', '1')
    if (-not $r.ok) { throw "mssql-conf falhou:`n$($r.s)" }
    Write-Host '    V27: criptografia obrigatória em toda conexão (network.forceencryption = 1).'
  }
  Dk @('restart', $Container) | Out-Null
  Pronto
  Write-Host '    SQL Server reiniciado com as correções.'
} finally { Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue }
