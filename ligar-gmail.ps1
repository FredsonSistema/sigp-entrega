# Liga os fluxos que usam o Gmail, depois de conectar a conta Google no n8n (GUIA-CONFIGURACAO.md, passo 3).
#   pwsh -File ligar-gmail.ps1            confere a conexão e publica os workflows do Gmail
#   pwsh -File ligar-gmail.ps1 -Desligar  tira do ar (para trocar de conta, por exemplo)
# Os workflows usam a credencial "Gmail account" que o instalador criou vazia; você só preenche e conecta.
# Funciona no PowerShell 7 e no Windows PowerShell 5.1. Nenhum token ou segredo é mostrado.
param([switch]$Desligar, [string]$Container = 'sigp_n8n', [string]$N8nUrl = 'http://127.0.0.1:5678')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$credencial = '6w8cHAuUwpPVa6tb'  # "Gmail account": o mesmo id nos workflows e na credencial criada pelo instalador
$workflows = [ordered]@{
  '5sQcHD7eYRgHxqgK'    = 'WF-08 Receber notas fiscais do Gmail (a cada 5 min)'
  'ZKHVZUPuZzkkVqao'    = 'WF-09 Aplicar etiquetas Gmail às notas associadas'
  'sigpWF08Reetiquetar' = 'WF-08 utilitário: reaplicar a etiqueta SIGp/Importado'
  'sigpWF06Vencimen'    = 'WF-06 Vencimentos e alertas diários por e-mail'
  'sigpWF99Erros000'    = 'WF-99 Aviso de erro dos workflows'
}
function Ok($t) { Write-Host "    ok: $t" -ForegroundColor Green }
function Roda([string[]]$argumentos) {
  # Saída de erro de programa vira erro do script no PowerShell 5.1; o Continue vale só durante a chamada.
  $antes = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try { & docker @argumentos 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) } finally { $ErrorActionPreference = $antes }
}

if (-not $Desligar) {
  # A credencial está conectada quando o Google já devolveu o token. A conferência roda dentro do container do n8n
  # (o arquivo temporário com a credencial decifrada é apagado na mesma chamada) e só devolve sim ou não.
  $conferir = "n8n export:credentials --id=$credencial --decrypted --output=/tmp/sigp_c.json >/dev/null 2>&1; " +
              "grep -q access_token /tmp/sigp_c.json; r=`$?; rm -f /tmp/sigp_c.json; exit `$r"
  if (-not (Roda @('exec', $Container, 'sh', '-c', $conferir))) {
    throw ('A conta Google ainda não está conectada. No n8n (http://127.0.0.1:5678) abra Overview > Credentials > ' +
           '"Gmail account", cole o Client ID e o Client Secret, clique em "Sign in with Google" e autorize. Depois rode de novo.')
  }
  Ok 'conta Google conectada no n8n'
}
$acao = if ($Desligar) { 'unpublish:workflow' } else { 'publish:workflow' }
foreach ($id in $workflows.Keys) {
  if (-not (Roda @('exec', $Container, 'n8n', $acao, "--id=$id"))) { throw "Não foi possível $(if ($Desligar) { 'desligar' } else { 'ligar' }) $($workflows[$id])." }
  Ok "$(if ($Desligar) { 'desligado' } else { 'ligado' }): $($workflows[$id])"
}
docker restart $Container | Out-Null
$fim = (Get-Date).AddSeconds(120)
while ($true) {
  try { if ((Invoke-WebRequest "$N8nUrl/healthz/readiness" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) { break } } catch { }
  if ((Get-Date) -gt $fim) { throw "O n8n não voltou em 2 minutos. Veja: docker logs $Container" }
  Start-Sleep 3
}
if ($Desligar) { Ok 'fluxos do Gmail fora do ar' }
else { Ok 'pronto: em até 5 minutos as faturas dos remetentes cadastrados aparecem em Notas recebidas' }
