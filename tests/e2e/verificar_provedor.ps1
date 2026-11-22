# P2-04 na API de TESTE (5011): associar uma nota recebida atualiza o provedor do local,
# e o alerta de vencimento passa a enxergá-lo.
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:5011'
$h = @{ 'X-API-Key' = 'chave-de-teste-e2e' }
$json = 'application/json'

$local = (Invoke-RestMethod "$base/api/locais?tipo=agencia").items | Where-Object { $_.provedores | Where-Object { $_.nome -match '^vox$' } } | Select-Object -First 1
"local: $($local.nome) | provedor antes: $(($local.provedores | ConvertTo-Json -Compress))"
$nota = (Invoke-RestMethod "$base/api/notas-recebidas").items | Where-Object { $_.status -ne 'ASSOCIADA' } | Select-Object -First 1
$venc = (Get-Date).AddDays(4).ToString('yyyy-MM-dd')
$body = @{ entidadeTipo = 'agencia'; entidadeId = $local.id; operador = 'teste';
  dados = @{ emissorNome = 'VOX TELECOM LTDA'; valorTotal = 199.9; dataVencimento = $venc; numero = ''; chave = '' } } | ConvertTo-Json -Depth 4
$r = Invoke-RestMethod -Method Patch "$base/api/notas-recebidas/$($nota.id)/associar" -Headers $h -ContentType $json -Body $body
"associar -> provedorAcao=$($r.provedorAcao) | provedor=$(($r.provedor | ConvertTo-Json -Compress))"
$depois = (Invoke-RestMethod "$base/api/locais/item/$($local.id)").item.provedores
"provedor no banco depois: $(($depois | ConvertTo-Json -Compress))"
$alertas = (Invoke-RestMethod "$base/api/alertas?dias=7&tipo=vencimento").items | Where-Object { $_.entidadeId -eq $local.id -and $_.origem -eq 'provedor' }
"alerta de vencimento do provedor: $(($alertas | Select-Object status, vencimento, provedor, valor | ConvertTo-Json -Compress))"
