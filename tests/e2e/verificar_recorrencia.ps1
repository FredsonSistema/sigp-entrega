# Regra de recorrência na API de TESTE (5011): duas notas recebidas do mesmo provedor/local no MESMO mês
# viram uma só nota (atualiza e substitui); no mês seguinte, nota nova e o provedor passa para a mais recente.
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:5011'
$h = @{ 'X-API-Key' = 'chave-de-teste-e2e' }
$json = 'application/json'
$local = (Invoke-RestMethod -Method Post "$base/api/locais/garagem/item" -Headers $h -ContentType $json -Body (@{ nome = "Garagem Recorrência $(Get-Random)"; cidade = 'Aracaju' } | ConvertTo-Json)).item
$fila = @((Invoke-RestMethod "$base/api/notas-recebidas").items | Where-Object { $_.status -ne 'ASSOCIADA' } | Select-Object -First 3)

function Associar($nota, $emissor, $numero, $venc, $valor) {
  $body = @{ entidadeTipo = 'garagem'; entidadeId = $local.id; operador = 'teste'
    dados = @{ emissorNome = $emissor; valorTotal = $valor; dataVencimento = $venc; numero = $numero; chave = ''; dataEmissao = '' } } | ConvertTo-Json -Depth 4
  try { return Invoke-RestMethod -Method Patch "$base/api/notas-recebidas/$($nota.id)/associar" -Headers $h -ContentType $json -Body $body }
  catch { $r = $_.ErrorDetails.Message | ConvertFrom-Json; return $r }
}
$a = Associar $fila[0] 'OPIX INTERNET' '1234567' '2026-11-10' 119.9
"nov/1 nota fiscal : criada=$($a.notaLancadaCriada) id=$($a.notaLancada.id)"
$b = Associar $fila[1] 'OPIX SERVICOS DE TECNOLOGIA EIRELI' '' '2026-11-10' 119.9
if ($b.requiresConfirmation -or $b.requiresComparison) {
  $cand = $b.comparacao.candidatas[0]
  "nov/2 boleto      : a API achou a nota do mesmo mês ($($cand.notaLancadaId)) e pede confirmação das diferenças: $(($cand.diferencas | ForEach-Object campo) -join ', ')"
  $body = @{ entidadeTipo = 'garagem'; entidadeId = $local.id; operador = 'teste'; notaLancadaId = $cand.notaLancadaId; confirmarAtualizacao = $true
    dados = @{ emissorNome = 'OPIX SERVICOS DE TECNOLOGIA EIRELI'; valorTotal = 119.9; dataVencimento = '2026-11-10'; numero = ''; chave = '' } } | ConvertTo-Json -Depth 4
  $b = Invoke-RestMethod -Method Patch "$base/api/notas-recebidas/$($fila[1].id)/associar" -Headers $h -ContentType $json -Body $body
}
"nov/2 boleto      : criada=$($b.notaLancadaCriada) mesma nota=$($b.notaLancada.id -eq $a.notaLancada.id) número mantido=$($b.notaLancada.numero)"
$c = Associar $fila[2] 'OPIX INTERNET' '' '2026-12-10' 129.9
if ($c.requiresConfirmation -or $c.requiresComparison) { "dez: pediu confirmação (inesperado): $($c.error)" }
"dez               : criada=$($c.notaLancadaCriada) nota nova=$($c.notaLancada.id -ne $a.notaLancada.id)"
$notas = (Invoke-RestMethod "$base/api/notas/lancadas").items | Where-Object { ($_.entidadeId + $_.entidade_id) -eq $local.id }
$prov = (Invoke-RestMethod "$base/api/locais/item/$($local.id)").item.provedores
"resultado: $($notas.Count) notas no local (esperado 2) | $($prov.Count) provedor | $($prov[0].nome) R$ $($prov[0].valor) venc $($prov[0].dataVencimento)"
