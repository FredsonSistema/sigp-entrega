# Abre o SIGp numa janela própria do Windows: sem barra de endereço, sem abas, com ícone e lugar próprios na barra de
# tarefas. Usa o Microsoft Edge no modo aplicativo (--app), que já vem no Windows 10 e 11; a tela continua sendo a do
# SIGp servida localmente (http://127.0.0.1:8000), nada sai da máquina.
# Se os containers estiverem parados (computador reiniciado, Docker recém-aberto), sobe os containers e espera a API.
# Uso: atalho "SIGp" da área de trabalho (criado pelo instalar-sigp.ps1) ou  powershell -File abrir-sigp.ps1
param([string]$Url = 'http://127.0.0.1:8000/agencias.html', [int]$EsperaSegundos = 180)
# Continue: a saída de erro do docker (comum enquanto ele liga) não deve derrubar o atalho; cada passo confere o resultado.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$pasta = $PSScriptRoot
$saude = 'http://127.0.0.1:8000/health'   # o nginx da tela

function No-Ar {
  try { (Invoke-WebRequest -Uri $saude -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { $false }
}

function Aviso([string]$texto) {
  Add-Type -AssemblyName PresentationFramework
  [void][System.Windows.MessageBox]::Show($texto, 'SIGp', 'OK', 'Warning')
}

if (-not (No-Ar)) {
  $docker = Get-Command docker -ErrorAction SilentlyContinue
  if (-not $docker) { Aviso 'O Docker não foi encontrado. Abra o Docker Desktop e tente de novo.'; exit 1 }
  & docker info *> $null
  if ($LASTEXITCODE -ne 0) {
    foreach ($d in (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop'), (Join-Path $env:ProgramFiles 'Docker\Docker')) {
      $app = Join-Path $d 'Docker Desktop.exe'
      if (Test-Path $app) { Start-Process $app; break }
    }
  }
  $fim = (Get-Date).AddSeconds($EsperaSegundos)
  $subiu = $false
  while ((Get-Date) -lt $fim) {
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) {
      if (-not $subiu) { Push-Location $pasta; & docker compose up -d *> $null; Pop-Location; $subiu = $true }
      if (No-Ar) { break }
    }
    Start-Sleep -Seconds 3
  }
  if (-not (No-Ar)) { Aviso "O SIGp não respondeu em $EsperaSegundos s. Confira se o Docker Desktop está ligado e abra o atalho de novo."; exit 1 }
}

$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
  Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($edge) {
  # Perfil separado: a janela do SIGp não mistura abas, extensões nem cookies com o navegador do dia a dia.
  $perfil = Join-Path $env:LOCALAPPDATA 'SIGp\janela'
  New-Item -ItemType Directory -Force -Path $perfil | Out-Null
  Start-Process $edge -ArgumentList "--app=$Url", "--user-data-dir=`"$perfil`"", '--window-size=1366,860', '--no-first-run'
} else {
  Start-Process $Url   # sem o Edge: abre no navegador padrão
}
