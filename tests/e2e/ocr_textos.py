"""Gera o texto OCR dos PDFs da base de TESTE (roda dentro do container sigp_api_test, que alcança o OCR).

Saída: /app/backend/data/ocr_textos/<arquivo>.json  (= tests/e2e/.data-test/ocr_textos no host)
"""
import json
import sys
import urllib.request
from pathlib import Path

base = Path("/app/backend/data")
saida = base / "ocr_textos"
saida.mkdir(exist_ok=True)
pdfs = sorted(list((base / "notas_recebidas").glob("*.pdf")) + list((base / "faturas").glob("*.pdf")))
for i, pdf in enumerate(pdfs, 1):
    destino = saida / f"{pdf.parent.name}__{pdf.stem}.json"
    if destino.exists():
        continue
    req = urllib.request.Request("http://ocr:5002/extract", data=pdf.read_bytes(), headers={"Content-Type": "application/pdf"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # PDF protegido/corrompido: registra e segue
        dados = {"ok": False, "erro": str(exc)[:200], "text": ""}
    destino.write_text(json.dumps({"arquivo": pdf.name, "pasta": pdf.parent.name, **dados}, ensure_ascii=False), encoding="utf-8")
    print(f"{i}/{len(pdfs)} {pdf.parent.name}/{pdf.name}: {len(str(dados.get('text') or ''))} caracteres, ocr={dados.get('ocrUsado')}", flush=True)
print("ok", file=sys.stderr)
