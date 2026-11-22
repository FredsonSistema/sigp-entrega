# Troca as senhas dos usuários de banco da IA (sigp_ia_loc001 e sigp_ia_loc002) e atualiza o .env.academic.
# Nada é exibido na tela nem gravado em log. Depois, recria o container da IA para ler a senha nova.
# Uso, na raiz:  pwsh -File docs/entrega-academica/sqlserver/trocar-senhas-ia.ps1
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$arquivo = Join-Path $dir '.env.academic'
$linhas = Get-Content $arquivo
$envs = @{}
$linhas | ForEach-Object { if ($_ -match '^([A-Z0-9_]+)=(.*)$') { $envs[$matches[1]] = $matches[2] } }

function NovaSenha {
  # 32 caracteres (letras, dígitos e símbolos sem aspas), atende à política de complexidade do SQL Server.
  $alfabeto = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789@#%+=_-'.ToCharArray()
  $bytes = [byte[]]::new(32)
  [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $s = -join ($bytes | ForEach-Object { $alfabeto[$_ % $alfabeto.Length] })
  return 'Aa1@' + $s.Substring(4)
}
$novas = @{ 'SIGP_AI_DB_PASSWORD_LOC001' = (NovaSenha); 'SIGP_AI_DB_PASSWORD_LOC002' = (NovaSenha) }
$sql = @"
SET NOCOUNT ON;
USE SIGpAcademic;
ALTER USER sigp_ia_loc001 WITH PASSWORD = N'$($novas['SIGP_AI_DB_PASSWORD_LOC001'])';
ALTER USER sigp_ia_loc002 WITH PASSWORD = N'$($novas['SIGP_AI_DB_PASSWORD_LOC002'])';
"@
$env:SQLCMDPASSWORD = $envs['MSSQL_SA_PASSWORD']
try {
  $sql | sqlcmd -S 127.0.0.1,14333 -U sa -C -b | Out-Null
  if ($LASTEXITCODE) { throw 'sqlcmd falhou ao trocar as senhas (nada foi alterado no .env).' }
} finally { Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue }
Copy-Item $arquivo "$arquivo.bak" -Force
$saida = $linhas | ForEach-Object {
  if ($_ -match '^(SIGP_AI_DB_PASSWORD_LOC00[12])=') { "$($matches[1])=$($novas[$matches[1]])" } else { $_ }
}
Set-Content -Path $arquivo -Value $saida -Encoding utf8
Remove-Item "$arquivo.bak" -Force
'senhas trocadas'
