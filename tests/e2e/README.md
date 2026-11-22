# Testes de navegador (Playwright)

Rodam a interface real (porta 8000) contra uma **API de teste** (porta 5011) com cópia dos dados. Nunca usam a API real (5001).

## Preparar

1. Copiar um backup de `sigp.db`, `faturas/` e `notas_recebidas/` para `tests/e2e/.data-test/`.
2. Subir a API de teste (imagem `sigp_n8n-api`, rede `sigp_n8n_default`, porta 5011, chave `chave-de-teste-e2e`, volume `.data-test`).
3. `cd tests/e2e && npm install`

## Rodar

- `node c1_chave_api.js` — a chave da API é pedida uma vez só.
- `node c2_fatura_provedor.js` — fatura PDF no provedor da localidade (usa n8n e OCR locais para extrair).

Capturas de tela e PDFs sintéticos ficam em `out/` (ignorado pelo Git). Os dados dos PDFs de teste são fictícios.

## Segurança dos dados reais

No modo de entrada padrão, a interface envia notas pelo n8n (WF-01/02), e o n8n grava sempre na API **real**. Por isso `lib.js` força `sigp_modo_entrada = api` e bloqueia no navegador de teste qualquer chamada à porta 5001 e a webhooks do n8n que não sejam de extração (`sigp-faturas-pdf`). Não remova essa trava.

Outras verificações: `nfse_local_provedor_ui.js`, `associar_provedor_ui.js`, `notas_recebidas_ui.js` e os scripts `verificar_*.ps1` (só API de teste).
