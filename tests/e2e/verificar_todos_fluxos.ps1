# Regra única na API de TESTE (5011): nota lançada (NFS-e/n8n) e fatura PDF (aba Faturas) associadas a um local
# também preenchem o provedor (nome, valor, data/dia de vencimento).
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:5011'
$h = @{ 'X-API-Key' = 'chave-de-teste-e2e' }
$json = 'application/json'
$local = (Invoke-RestMethod -Method Post "$base/api/locais/rodoviaria/item" -Headers $h -ContentType $json -Body (@{ nome = "Rodoviária Fluxos $(Get-Random)"; cidade = 'Jequié' } | ConvertTo-Json)).item
"local: $($local.nome) | provedores antes: $($local.provedores.Count)"

# 1) Nota lançada (mesmo caminho do modal NFS-e da localidade e do WF-01 do n8n)
$nota = @{ id = "nl-$(Get-Random)"; entidadeTipo = 'rodoviaria'; entidadeId = $local.id; origem = 'manual'
  dados = @{ numero = "$(Get-Random)"; provedorNome = 'ALGAR TELECOM S/A'; valor = 121.69; dataEmissao = '2026-11-01'; dataVencimento = '2026-11-20' } } | ConvertTo-Json -Depth 4
$r1 = Invoke-RestMethod -Method Post "$base/api/notas/lancadas" -Headers $h -ContentType $json -Body $nota
"1) nota lançada -> provedorAcao=$($r1.provedorAcao) | $($r1.provedor.nome) | R$ $($r1.provedor.valor) | venc $($r1.provedor.dataVencimento) (dia $($r1.provedor.diaVencimento))"

# 2) Fatura PDF pela aba Faturas (sem linha de provedor), mais recente: atualiza o mesmo provedor
$pdf = Join-Path $PSScriptRoot 'out\fatura-sintetica-c2.pdf'
$dados = @{ emissorNome = 'ALGAR TELECOM S/A'; dataVencimento = '2026-12-20'; valorTotal = 125.5; emissorConfirmado = $true } | ConvertTo-Json -Compress
$form = @{ arquivo = Get-Item $pdf; dadosExtracao = $dados; entidadeTipo = 'rodoviaria'; entidadeId = $local.id; provedorEsperado = 'ALGAR TELECOM S/A' }
$r2 = Invoke-RestMethod -Method Post "$base/api/faturas" -Headers $h -Form $form
"2) fatura PDF -> provedorAcao=$($r2.provedorAcao) | R$ $($r2.provedor.valor) | venc $($r2.provedor.dataVencimento) | faturaAtual=$($r2.provedor.faturaAtualId -eq $r2.item.id)"

# 3) Nota antiga depois: não pode voltar o vencimento
$antiga = @{ id = "nl-$(Get-Random)"; entidadeTipo = 'rodoviaria'; entidadeId = $local.id
  dados = @{ numero = "$(Get-Random)"; provedorNome = 'Algar Telecom'; valor = 110; dataEmissao = '2026-10-01'; dataVencimento = '2026-10-20' } } | ConvertTo-Json -Depth 4
$r3 = Invoke-RestMethod -Method Post "$base/api/notas/lancadas" -Headers $h -ContentType $json -Body $antiga
"3) nota mais antiga -> provedorAcao=$($r3.provedorAcao)"
$final = (Invoke-RestMethod "$base/api/locais/item/$($local.id)").item.provedores
"final: $($final.Count) provedor(es) | $(($final | Select-Object nome, valor, dataVencimento, diaVencimento | ConvertTo-Json -Compress))"
