# Verificação rápida contra a API de TESTE (5011): extração com valor padrão/emissão,
# descarte e restauração. Não toca na API real (5001).
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:5011'
$h = @{ 'X-API-Key' = 'chave-de-teste-e2e' }

$r = Invoke-RestMethod "$base/api/notas-recebidas"
"fila (sem descartadas): $($r.items.Count)"
$alvo = $r.items | Where-Object { $_.status -eq 'REVISAO' } | Select-Object -First 1
"alvo: $($alvo.id) | $($alvo.nome_arquivo) | numero salvo='$($alvo.dados.numero)'"

$ex = Invoke-RestMethod -Method Post "$base/api/notas-recebidas/$($alvo.id)/extrair" -Headers $h -TimeoutSec 240
$d = $ex.dados
"extração: numero=$($d.numero) (padrão=$($d.numeroPadrao)) chave=$($d.chave) emissão=$($d.dataEmissao) origem=$($d.dataEmissaoOrigem)"
"          valor=$($d.valorTotal) venc=$($d.dataVencimento) emissor=$($d.emissorNome) | revisar=$($d.camposParaRevisar -join ',')"

$body = @{ motivo = 'nao_cobranca'; detalhe = 'teste automatizado'; operador = 'teste' } | ConvertTo-Json
$desc = Invoke-RestMethod -Method Patch "$base/api/notas-recebidas/$($alvo.id)/descartar" -Headers $h -ContentType 'application/json' -Body $body
"descartar -> status=$($desc.item.status) motivo=$($desc.item.dados.descarte.motivo)"
$fila = (Invoke-RestMethod "$base/api/notas-recebidas").items | Where-Object { $_.id -eq $alvo.id }
"saiu da fila padrão: $(-not $fila)"
$filtro = (Invoke-RestMethod "$base/api/notas-recebidas?status=DESCARTADA").items | Where-Object { $_.id -eq $alvo.id }
"aparece no filtro Descartada: $([bool]$filtro)"
$rest = Invoke-RestMethod -Method Patch "$base/api/notas-recebidas/$($alvo.id)/restaurar" -Headers $h -ContentType 'application/json' -Body '{"operador":"teste"}'
"restaurar -> status=$($rest.item.status) (esperado: $($alvo.status))"
try { Invoke-RestMethod -Method Patch "$base/api/notas-recebidas/$($alvo.id)/descartar" -Headers $h -ContentType 'application/json' -Body '{}' | Out-Null; 'motivo vazio: ACEITO (erro)' }
catch { "motivo vazio: recusado com HTTP $($_.Exception.Response.StatusCode.value__)" }
