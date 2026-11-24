# Instala o SIGp do zero com um comando, num Windows sem nada instalado. Cole no PowerShell:
#
#   irm https://raw.githubusercontent.com/FredsonSistema/sigp-entrega/main/instalar-sigp.ps1 | iex
#
# (ou clique duas vezes em "Instalar SIGp.cmd"). O que ele faz, pulando o que a máquina já tem:
#   1. confere a máquina (64 bits, memória, disco e virtualização);
#   2. liga o WSL 2, se faltar: pede permissão de administrador uma vez e reinicia; depois do reinício continua sozinho;
#   3. instala o Docker Desktop no modo do usuário (sem administrador) e aceita a licença; liga o Docker e espera;
#   4. baixa o PowerShell 7 portátil (sem administrador) e o pacote do SIGp (sem Git);
#   5. roda o instalar.ps1 do pacote, que no fim pede o seu nome e a sua senha para criar o acesso;
#   6. cria o atalho "SIGp" na área de trabalho e abre a tela.
# Opções (variáveis de ambiente, antes do comando):
#   $env:SIGP_PASTA = 'D:\sigp'                 pasta da instalação (padrão: Documentos\sigp-entrega)
#   $env:SIGP_MODELO_TRIAGEM = 'qwen2.5:0.5b'    instalação leve (~1,5 GB a menos, triagem do Gmail mais fraca)
#   $env:SIGP_SO_BAIXAR = '1'                    só prepara a máquina e baixa o pacote, sem instalar
# Funciona no Windows PowerShell 5.1 (o que já vem no Windows). Nenhuma chave ou senha é mostrada ou gravada aqui.
& {
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$repo = 'FredsonSistema/sigp-entrega'
$urlScript = "https://raw.githubusercontent.com/$repo/main/instalar-sigp.ps1"
$urlPacote = "https://codeload.github.com/$repo/zip/refs/heads/main"
$urlDocker = 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'
$versaoPwsh = '7.4.6'
$urlPwsh = "https://github.com/PowerShell/PowerShell/releases/download/v$versaoPwsh/PowerShell-$versaoPwsh-win-x64.zip"
$pasta = if ($env:SIGP_PASTA) { $env:SIGP_PASTA } else { Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'sigp-entrega' }
$local = Join-Path $env:LOCALAPPDATA 'SIGp-instalador'  # downloads e o PowerShell portátil (não é a pasta de dados do SIGp)
$retomar = "powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -Command `"irm $urlScript | iex`""
$chaveRunOnce = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'

function Passo($n, $texto) { Write-Host "`n[$n/6] $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "    ok: $texto" -ForegroundColor Green }
function Info($texto) { Write-Host "    $texto" }
function Baixar($url, $destino) {
  Info "baixando $(Split-Path $destino -Leaf)..."
  Invoke-WebRequest $url -OutFile $destino -UseBasicParsing
}
function Docker-Exe {
  $c = Get-Command docker.exe -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  foreach ($d in (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop'), (Join-Path $env:ProgramFiles 'Docker\Docker')) {
    $e = Join-Path $d 'resources\bin\docker.exe'
    if (Test-Path $e) { return $e }
  }
  return $null
}
function Roda-Ok([string]$exe, [string[]]$argumentos) {
  # Roda um programa só para saber se deu certo. No Windows PowerShell 5.1, com ErrorActionPreference = Stop, a saída de
  # erro redirecionada de um programa vira erro do script; por isso o Continue só durante a chamada.
  $antes = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { & $exe @argumentos 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) } catch { return $false } finally { $ErrorActionPreference = $antes }
}
function Docker-Ligado($exe) { return (Roda-Ok $exe @('info', '--format', '{{.ServerVersion}}')) }

Write-Host 'Instalação do SIGp (pacote da entrega acadêmica)' -ForegroundColor Cyan
Write-Host "Pasta: $pasta"

# 1. A máquina
Passo 1 'Conferindo a máquina'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'O SIGp precisa do Windows de 64 bits.' }
$memGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if ($memGb -lt 8) { Write-Host "    atenção: $memGb GB de memória (o mínimo é 8 GB); a IA pode ficar lenta ou parar." -ForegroundColor Yellow }
New-Item -ItemType Directory -Force -Path $pasta, $local | Out-Null
$livreGb = [math]::Round((Get-PSDrive ((Resolve-Path $pasta).Path.Substring(0, 1))).Free / 1GB)
if ($livreGb -lt 15) { throw "Só $livreGb GB livres no disco de $pasta; são precisos 15 GB (imagens, modelos de IA e banco)." }
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
if (-not $cs.HypervisorPresent -and -not $cpu.VirtualizationFirmwareEnabled) {
  throw ('A virtualização está desligada na BIOS/UEFI. Ligue a opção "Intel VT-x", "Intel Virtualization Technology" ou ' +
         '"AMD-V/SVM" na BIOS do computador e rode o comando de novo.')
}
Ok "$memGb GB de memória, $livreGb GB livres, virtualização ligada"

# 2. WSL 2 (o Docker roda os serviços Linux nele). Ligar pela primeira vez exige administrador e reinício.
Passo 2 'WSL 2'
if (-not (Roda-Ok 'wsl.exe' @('--version'))) {
  Info 'o WSL 2 não está instalado. O Windows vai pedir permissão de administrador (uma vez só).'
  $p = Start-Process wsl.exe -ArgumentList '--install', '--no-distribution' -Verb RunAs -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "A instalação do WSL falhou (código $($p.ExitCode)). Rode 'wsl --install' como administrador e depois este comando de novo." }
  New-Item -Path $chaveRunOnce -Force | Out-Null
  Set-ItemProperty -Path $chaveRunOnce -Name 'SIGp-instalacao' -Value $retomar
  Write-Host "`n    O WSL foi instalado e o Windows precisa reiniciar. Depois de entrar de novo, a instalação continua sozinha." -ForegroundColor Yellow
  $r = Read-Host '    Reiniciar agora? (S/N)'
  if ($r -match '^[sS]') { Restart-Computer -Force } else { Info 'Reinicie quando puder; a instalação continua depois.' }
  return
}
Ok 'WSL 2 instalado'

# 3. Docker Desktop no modo do usuário (não precisa de administrador; licença aceita na instalação)
Passo 3 'Docker Desktop'
$docker = Docker-Exe
if (-not $docker) {
  $inst = Join-Path $local 'DockerDesktopInstaller.exe'
  Baixar $urlDocker $inst
  Info 'instalando (alguns minutos)...'
  $p = Start-Process $inst -ArgumentList 'install', '--user', '--quiet', '--accept-license' -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "A instalação do Docker Desktop falhou (código $($p.ExitCode))." }
  Remove-Item $inst -Force -ErrorAction SilentlyContinue
  $docker = Docker-Exe
  if (-not $docker) { throw 'O Docker Desktop foi instalado, mas o docker.exe não foi encontrado. Reinicie o computador e rode o comando de novo.' }
}
$binDocker = Split-Path $docker
if (($env:Path -split ';') -notcontains $binDocker) { $env:Path = "$binDocker;$env:Path" }
if (-not (Docker-Ligado $docker)) {
  $app = Join-Path (Split-Path (Split-Path $binDocker)) 'Docker Desktop.exe'
  Info 'ligando o Docker (a primeira vez leva alguns minutos)...'
  if (Test-Path $app) { Start-Process $app }
  $fim = (Get-Date).AddMinutes(10)
  while (-not (Docker-Ligado $docker)) {
    if ((Get-Date) -gt $fim) { throw 'O Docker não ligou em 10 minutos. Abra o Docker Desktop, espere "Engine running" e rode o comando de novo.' }
    Start-Sleep 5
  }
}
Ok 'Docker ligado'

# 4. PowerShell 7 portátil e o pacote do SIGp
Passo 4 'PowerShell 7 e o pacote do SIGp'
$pwsh = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $pwsh) {
  $dirPwsh = Join-Path $local "pwsh-$versaoPwsh"
  $pwsh = Join-Path $dirPwsh 'pwsh.exe'
  if (-not (Test-Path $pwsh)) {
    $zip = Join-Path $local 'pwsh.zip'
    Baixar $urlPwsh $zip
    Expand-Archive $zip -DestinationPath $dirPwsh -Force
    Remove-Item $zip -Force
  }
  # No PATH do usuário, para os outros comandos do guia (demonstração, testes) acharem o "pwsh".
  $pathUsuario = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (($pathUsuario -split ';') -notcontains $dirPwsh) { [Environment]::SetEnvironmentVariable('Path', ($pathUsuario.TrimEnd(';') + ";$dirPwsh").TrimStart(';'), 'User') }
}
if (Test-Path (Join-Path $pasta '.git')) {
  Info 'pasta clonada com o Git: atualizando com git pull'
  git -C $pasta pull --ff-only
} else {
  $zip = Join-Path $local 'sigp-entrega.zip'
  $tmp = Join-Path $local 'pacote'
  Baixar $urlPacote $zip
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  Expand-Archive $zip -DestinationPath $tmp -Force
  $raizZip = Get-ChildItem $tmp -Directory | Select-Object -First 1
  # Copia por cima: o que é só desta máquina (.env, .env.academic, segredos-locais, dados) não vem no pacote e fica.
  Copy-Item (Join-Path $raizZip.FullName '*') $pasta -Recurse -Force
  Remove-Item $zip, $tmp -Recurse -Force
}
Get-ChildItem $pasta -Recurse -File -Include *.ps1, *.cmd | Unblock-File
Ok "pacote em $pasta"
if ($env:SIGP_SO_BAIXAR -eq '1') { Info 'SIGP_SO_BAIXAR=1: parei antes de instalar.'; return }

# 5. O instalador do pacote (chaves, containers, banco, modelos, workflows, base fictícia e o seu acesso)
Passo 5 'Instalando o SIGp (a primeira vez baixa uns 7 GB: de 15 a 40 minutos; se a rede cair, ele tenta de novo)'
$args5 = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $pasta 'instalar.ps1'))
if ($env:SIGP_MODELO_TRIAGEM) { $args5 += @('-ModeloTriagem', $env:SIGP_MODELO_TRIAGEM) }
& $pwsh @args5
if ($LASTEXITCODE -ne 0) { throw "O instalador parou com erro (veja a mensagem acima). Corrija e rode o mesmo comando de novo: o que já foi feito é mantido." }

# 6. Atalho e tela
Passo 6 'Atalho e tela'
$url = 'http://127.0.0.1:8000/agencias.html'
$atalho = Join-Path ([Environment]::GetFolderPath('Desktop')) 'SIGp.url'
Set-Content -Path $atalho -Value @('[InternetShortcut]', "URL=$url") -Encoding ASCII
Remove-ItemProperty -Path $chaveRunOnce -Name 'SIGp-instalacao' -ErrorAction SilentlyContinue
Ok 'atalho "SIGp" na área de trabalho'
Start-Process $url
Write-Host "`nPronto. Entre com o usuário e a senha que você criou." -ForegroundColor Green
Write-Host '  Tela do SIGp: http://127.0.0.1:8000/agencias.html   ·   n8n: http://127.0.0.1:5678'
Write-Host "  Guarde num lugar seguro (são só desta máquina): $pasta\.env, docs\entrega-academica\sqlserver\.env.academic e segredos-locais\tde"
}
