# Associação na API de TESTE (5011): nota sem número/chave/emissão não pode mais ser bloqueada,
# e duas notas sem número do mesmo provedor (meses diferentes) não podem se fundir.
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:5011'
$h = @{ 'X-API-Key' = 'chave-de-teste-e2e' }
$json = 'application/json'

$local = (Invoke-RestMethod -Method Post "$base/api/locais/agencia/item" -Headers $h -ContentType $json -Body '{"nome":"Agência Teste Associação","cidade":"Itabuna"}').item
"local de teste: $($local.id)"
$fila = (Invoke-RestMethod "$base/api/notas-recebidas").items | Where-Object { $_.status -ne 'ASSOCIADA' }
$a, $b = $fila | Select-Object -First 2

function Associar($nota, $venc) {
  $dados = @{ emissorNome = 'PROVEDOR SEM NUMERO LTDA'; valorTotal = 150.5; dataVencimento = $venc; numero = ''; chave = ''; dataEmissao = '' }
  $body = @{ entidadeTipo = 'agencia'; entidadeId = $local.id; operador = 'teste'; dados = $dados } | ConvertTo-Json -Depth 4
  Invoke-RestMethod -Method Patch "$base/api/notas-recebidas/$($nota.id)/associar" -Headers $h -ContentType $json -Body $body
}

$r1 = Associar $a '2026-11-10'
"1ª: criada=$($r1.notaLancadaCriada) numero=$($r1.notaLancada.numero) chave=$($r1.notaLancada.chave) emissão=$($r1.notaLancada.data_emissao)"
$r2 = Associar $b '2026-12-10'
"2ª: criada=$($r2.notaLancadaCriada) numero=$($r2.notaLancada.numero)"
"as duas são notas diferentes (não fundiu): $($r1.notaLancada.id -ne $r2.notaLancada.id)"
$det = Invoke-RestMethod "$base/api/notas-recebidas?status=ASSOCIADA"
$item = $det.items | Where-Object { $_.id -eq $a.id }
"origem da emissão registrada: $($item.dados.dataEmissaoOrigem)"
try {
  $body = @{ entidadeTipo = 'agencia'; entidadeId = $local.id; dados = @{ emissorNome = 'X'; valorTotal = 10; dataVencimento = '' } } | ConvertTo-Json -Depth 4
  $c = (Invoke-RestMethod "$base/api/notas-recebidas").items | Where-Object { $_.status -ne 'ASSOCIADA' } | Select-Object -First 1
  Invoke-RestMethod -Method Patch "$base/api/notas-recebidas/$($c.id)/associar" -Headers $h -ContentType $json -Body $body | Out-Null
  'sem vencimento: ACEITO (erro)'
} catch { "sem vencimento: recusado com HTTP $($_.Exception.Response.StatusCode.value__) (obrigatório)" }
