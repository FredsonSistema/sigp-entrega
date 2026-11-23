# Primeiro acesso: cria o administrador da tela do SIGp e o dono do n8n, com a senha que VOCÊ digita aqui.
# A senha não aparece na tela, não vai para a área de transferência e não é gravada em arquivo: fica só na memória deste
# processo, vai para os dois serviços locais (127.0.0.1) e é apagada da memória no fim. O SIGp guarda só o hash (scrypt).
# O instalador chama este script no fim; se você pulou essa etapa, rode de novo:  pwsh -File primeiro-acesso.ps1
# A chave do servidor (SIGP_API_KEY do .env), que prova que é o dono da instalação, é lida do arquivo e também não aparece.
# Funciona no PowerShell 7 e no Windows PowerShell 5.1.
param(
  [string]$Nome = '', [string]$Usuario = '', [string]$Email = '',
  [Security.SecureString]$Senha = $null,  # para automação; sem ela, a senha é pedida no teclado
  [string]$SigpUrl = 'http://127.0.0.1:5001', [string]$N8nUrl = 'http://127.0.0.1:5678'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$raiz = $PSScriptRoot

function Ok($texto) { Write-Host "    ok: $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "    $texto" -ForegroundColor Yellow }
# A vírgula mantém o byte[] inteiro: sem ela, o PowerShell devolve os bytes um a um e o corpo chega estragado.
function Json($obj) { return , [Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Compress)) }
function Erro-Http($erro) {
  # Mensagem que o próprio serviço devolveu (ex.: "A senha precisa ter pelo menos 8 caracteres."), nunca o corpo enviado.
  try { $m = ($erro.ErrorDetails.Message | ConvertFrom-Json); if ($m.error) { return $m.error }; if ($m.message) { return $m.message } } catch { }
  return $erro.Exception.Message
}
function Texto-Simples([Security.SecureString]$s) {
  $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}
function Sem-Acento([string]$t) {
  $n = $t.Normalize([Text.NormalizationForm]::FormD)
  return (-join ($n.ToCharArray() | Where-Object { [Globalization.CharUnicodeInfo]::GetUnicodeCategory($_) -ne 'NonSpacingMark' }))
}
# Regras das duas pontas juntas: as do SIGp (8+ caracteres, sem o usuário, não trivial) e as do n8n (até 64, com
# maiúscula e número). Conferidas aqui antes de enviar, para pedir de novo sem criar nada pela metade.
function Problema-Senha([string]$s, [string]$u) {
  if ($s.Length -lt 8) { return 'tem menos de 8 caracteres' }
  if ($s.Length -gt 64) { return 'tem mais de 64 caracteres' }
  if ($s -cnotmatch '[A-Z]') { return 'não tem letra maiúscula' }
  if ($s -notmatch '[0-9]') { return 'não tem número' }
  if ($u -and $s.ToLower().Contains($u.ToLower())) { return 'contém o nome de usuário' }
  if (($s.ToCharArray() | Select-Object -Unique).Count -lt 4) { return 'é fácil demais' }
  return $null
}

# O que falta criar.
$estado = Invoke-RestMethod "$SigpUrl/api/auth/estado" -TimeoutSec 15
$precisaSigp = [bool]$estado.precisaPrimeiroAdmin
$precisaN8n = [bool](Invoke-RestMethod "$N8nUrl/rest/settings" -TimeoutSec 15).data.userManagement.showSetupOnFirstLoad
if (-not $precisaSigp -and -not $precisaN8n) { Ok 'os acessos já existem (entre com seu usuário e senha)'; return }

$chave = $null
if ($precisaSigp) {
  $envRaiz = Join-Path $raiz '.env'
  $linha = Get-Content $envRaiz -Encoding utf8 | Where-Object { $_ -match '^SIGP_API_KEY=' } | Select-Object -First 1
  if (-not $linha) { throw "SIGP_API_KEY não encontrada em $envRaiz. Rode o instalador primeiro." }
  $chave = $linha.Substring('SIGP_API_KEY='.Length)
}
$interativo = -not $Senha
if ($interativo -and ([Console]::IsInputRedirected -or -not [Environment]::UserInteractive)) {
  Aviso 'Sem teclado disponível para criar o acesso. Depois rode:  pwsh -File primeiro-acesso.ps1'
  return
}

Write-Host ''
Write-Host '    Crie o seu acesso. A senha é digitada aqui, não aparece na tela e não é gravada em nenhum arquivo.'
$alvos = @(); if ($precisaSigp) { $alvos += 'a tela do SIGp' }; if ($precisaN8n) { $alvos += 'o n8n' }
Write-Host "    A mesma senha vale para $($alvos -join ' e ')."
while (-not $Nome.Trim()) { $Nome = Read-Host '    Seu nome' }
$Nome = $Nome.Trim()
if (-not $Usuario -and $precisaSigp) {
  $sugestao = ((Sem-Acento $Nome).ToLower() -replace '[^a-z0-9]+', '.').Trim('.')
  if ($sugestao.Length -lt 3) { $sugestao = 'admin' }
  $Usuario = Read-Host "    Usuário para entrar no SIGp [$sugestao]"
  if (-not $Usuario.Trim()) { $Usuario = $sugestao }
}
$Usuario = $Usuario.Trim().ToLower()
if ($precisaN8n) {
  while ($Email -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
    if ($Email) { Aviso 'E-mail inválido.' }
    $Email = Read-Host '    Seu e-mail (login do n8n; fica só nesta máquina)'
  }
}

$texto = $null
try {
  while ($true) {
    if ($interativo) {
      Write-Host '    Senha: 8 a 64 caracteres, com letra maiúscula e número.'
      $s1 = Read-Host '    Senha' -AsSecureString
      $s2 = Read-Host '    Repita a senha' -AsSecureString
      $texto = Texto-Simples $s1
      $repetida = Texto-Simples $s2
      $s1.Dispose(); $s2.Dispose()
      if ($texto -cne $repetida) { $repetida = $null; Aviso 'As duas senhas não são iguais. Tente de novo.'; continue }
      $repetida = $null
    } else {
      $texto = Texto-Simples $Senha
    }
    $problema = Problema-Senha $texto $Usuario
    if ($problema) {
      if (-not $interativo) { throw "Senha recusada: $problema." }
      Aviso "A senha $problema. Tente de novo."; continue
    }
    if ($precisaSigp) {
      try {
        Invoke-RestMethod -Method Post "$SigpUrl/api/auth/primeiro-admin" -ContentType 'application/json; charset=utf-8' -TimeoutSec 30 `
          -Body (Json @{ chave = $chave; nome = $Nome; usuario = $Usuario; senha = $texto }) | Out-Null
        $precisaSigp = $false
        Ok "administrador do SIGp criado (usuário: $Usuario)"
      } catch {
        $m = Erro-Http $_
        if (-not $interativo -or $m -notmatch '(?i)senha|usu') { throw "SIGp recusou: $m" }
        Aviso "O SIGp recusou: $m"
        if ($m -match '(?i)usu') { $Usuario = (Read-Host '    Outro usuário').Trim().ToLower() }
        continue
      }
    }
    if ($precisaN8n) {
      $partes = $Nome -split '\s+', 2
      $sobrenome = if ($partes.Count -gt 1) { $partes[1] } else { $partes[0] }
      try {
        Invoke-RestMethod -Method Post "$N8nUrl/rest/owner/setup" -ContentType 'application/json; charset=utf-8' -TimeoutSec 30 `
          -Body (Json @{ email = $Email; firstName = $partes[0]; lastName = $sobrenome; password = $texto }) | Out-Null
        $precisaN8n = $false
        Ok "conta do n8n criada (login: $Email)"
      } catch {
        throw "O n8n recusou: $(Erro-Http $_). O SIGp já tem o administrador; para o n8n, abra $N8nUrl e crie a conta lá."
      }
    }
    break
  }
} finally {
  $texto = $null; $chave = $null
  [GC]::Collect()
}
