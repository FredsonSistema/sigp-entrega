# Entrega final — otimização das duas consultas lentas.
# Gera em evidence/parte3/otimizacao/:
#   resumo-testes.txt      12_resumo_testes.sql (consistência, segurança e custo de gravação do resumo diário)
#   tempos.txt             10_benchmark_final.sql (mediana, p95 e média; configurações A, B, C e D)
#   leituras-logicas.txt   11_planos_final.sql (STATISTICS IO por configuração)
#   <cfg>-consulta<n>.sqlplan  planos reais (abrem no SSMS ou no Azure Data Studio)
# Termina na configuração C (índices ajustados mantidos). Uso, na raiz: pwsh -File docs/entrega-academica/sqlserver/benchmark-final.ps1
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$out = Join-Path $dir 'evidence/parte3/otimizacao'
New-Item -ItemType Directory -Force $out | Out-Null
$envs = @{}
Get-Content (Join-Path $dir '.env.academic') | ForEach-Object { if ($_ -match '^([A-Z0-9_]+)=(.*)$') { $envs[$matches[1]] = $matches[2] } }
$env:SQLCMDPASSWORD = $envs['MSSQL_SA_PASSWORD']
try {
  $base = @('-S', '127.0.0.1,14333', '-U', 'sa', '-d', 'SIGpAcademic', '-C', '-f', '65001', '-b', '-I')
  Write-Host '1/3 Testes do resumo diário...'
  & sqlcmd @base -W -s '|' -i (Join-Path $dir '12_resumo_testes.sql') | Set-Content -Encoding utf8 (Join-Path $out 'resumo-testes.txt')
  if ($LASTEXITCODE -ne 0) { throw '12_resumo_testes.sql falhou' }
  Write-Host '2/3 Tempos (A, B, C, D)...'
  & sqlcmd @base -W -s '|' -i (Join-Path $dir '10_benchmark_final.sql') | Set-Content -Encoding utf8 (Join-Path $out 'tempos.txt')
  if ($LASTEXITCODE -ne 0) { throw '10_benchmark_final.sql falhou' }
  Write-Host '3/3 Leituras lógicas e planos...'
  $leituras = @()
  foreach ($cfg in 'A', 'B', 'C', 'D') {
    $texto = (& sqlcmd @base -y 0 -v "CFG=$cfg" -i (Join-Path $dir '11_planos_final.sql')) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "11_planos_final.sql falhou em $cfg" }
    $planos = [regex]::Matches($texto, '<ShowPlanXML[\s\S]*?</ShowPlanXML>')
    for ($n = 0; $n -lt $planos.Count; $n++) {
      $planos[$n].Value | Set-Content -Encoding utf8 (Join-Path $out "$cfg-consulta$($n + 1).sqlplan")
    }
    $leituras += "### Configuração $cfg"
    $leituras += ($texto -split "`n" | Where-Object { $_ -match '^### CONSULTA|^Table ' })
  }
  $leituras | Set-Content -Encoding utf8 (Join-Path $out 'leituras-logicas.txt')
} finally {
  Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue
}
Get-Content (Join-Path $out 'resumo-testes.txt') | Select-String 'APROVADO|REPROVADO' | ForEach-Object { "Testes do resumo: $($_.Line.Trim())" }
'concluído'
