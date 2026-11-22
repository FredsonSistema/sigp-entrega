# Roda avaliar_alertas.js dentro do container do n8n (rede do Ollama e da API) e grava a evidência.
# Uso, na raiz do projeto:  pwsh -File n8n/wf06/avaliar_alertas.ps1
$ErrorActionPreference = 'Stop'
$pasta = $PSScriptRoot
$saida = Join-Path $pasta 'evidence'
New-Item -ItemType Directory -Force $saida | Out-Null
docker exec sigp_n8n sh -c 'rm -rf /tmp/wf06 && mkdir -p /tmp/wf06' | Out-Null
foreach ($f in 'alertas_lib.js', 'avaliar_alertas.js', 'prompt_alerta.md', 'schema_alerta.json') {
  docker cp (Join-Path $pasta $f) "sigp_n8n:/tmp/wf06/$f" | Out-Null
}
$json = docker exec sigp_n8n node /tmp/wf06/avaliar_alertas.js
if ($LASTEXITCODE -ne 0) { throw 'A avaliação falhou.' }
$arquivo = Join-Path $saida 'avaliacao-alertas.json'
[IO.File]::WriteAllText($arquivo, ($json -join "`n"), (New-Object Text.UTF8Encoding $false))
$r = ($json -join "`n") | ConvertFrom-Json
"Modelo $($r.modelo): $($r.aberturas_da_llm_aceitas)/$($r.cenarios) aberturas da LLM aceitas; mediana $($r.latencia_mediana_ms) ms. Evidência: $arquivo"
$r.resultados | ForEach-Object { "- $($_.cenario): $($_.origem)$(if ($_.motivo) { " ($($_.motivo))" })" }
