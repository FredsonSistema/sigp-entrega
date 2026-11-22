"""Paridade B-01: n8n/lib/extrator.js x backend (POST /api/extracao/texto) sobre os mesmos textos.

Fontes: textos OCR da base de teste (tests/e2e/.data-test/ocr_textos) e variantes mecânicas de cada um
(linhas invertidas, maiúsculas, metades, CRLF, esperado preenchido), para exercitar mais caminhos.
Compara todos os campos da resposta, menos "extrator". Sai com código 1 se houver diferença.

Uso, na raiz:  .\\.venv-1\\Scripts\\python.exe tests/n8n/paridade_extrator.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from backend.app import app  # noqa: E402

PASTA = RAIZ / "tests" / "e2e" / ".data-test" / "ocr_textos"
EXTRAS = [
    "",
    "Prestador: ITS TELECOMUNICACOES LTDA\nNúmero da nota: 0000\nValor total: R$ 174,00\nVencimento: 31/02/2026",
    "Razão Social: OPIX INTERNET LTDA\nNº.: 302500\nData de emissão: 01/10/2026 10:00\nTotal a pagar: 119,90\nVencimento: 10/11/2026",
    "Beneficiário\nAgência/Código beneficiário\nVOX TELECOM S.A.   CNPJ 12.345.678/0001-90\nTomador CNPJ: 98.765.432/0001-10\nFatura nº 2026/10-55",
    "nº documento    Vencimento\n12.345.678/0001-90    05/11/2026\n(+) Serviço de internet R$ 89,90",
    "Chave de acesso: 1234 5678 9012 3456 7890 1234 5678 9012 3456 7890 1234\nSérie: 1\nValor do documento 1.234,56",
    "N° 123\nEmissão    07/10/2026\nDATA DE VENCIMENTO: 18/10/2026 - pagar\nProvedor de Internet Exemplo",
    "CHAVE DE ACESSO DA NFS-e\n29333071221098765000180260000001575226110027288988\n\nNÚMERO DA NFS-e\n2600000015752",
    "CHAVE DE ACESSO\n1234567890123456789012345678901234567890123",
    "41310-600 - SALVADOR   Nº documento: 2847941\nR$ 174,00",
    "Nº documento       Vencimento\n77001              05/11/2026",
    "EXPRESSO BRASILEIRO TRANSPORTES   NOTA FISCAL Nº 16210 - SÉRIE: 1\nCHAVE DE ACESSO:\n"
    "CÓD. DO CLIENTE: 31457   2926 1098 7654 3200 0110 6200 1000 0162 1010 6925 5993",
    "CHAVE DE ACESSO:\n2926 1098 7654 3200 0110 6200 1000 0162 1010 6925 5994",
    "Discriminação do serviço:\n\nDescrição   Contrato   Valor Unitário   Qtde.\nLINK FIBRA 400MB   204567   R$ 76,95",
    "(+) Mora / Multa\n(+) Prestação de serviço de internet - Plano: FIBRA 350 MEGAS - R$ 79.99   Autenticação mecânica",
    "(+) Outros acréscimos\nReferente ao Acesso a Internet via Fibra de 11/10/2026 a 10/11/2026\nRef. 10/10/2026 até 09/11/2026",
    "DESCRIÇÃO DOS SERVIÇOS\n\nDava DE curce-Ht: 01/11/2026",
]


def casos():
    vistos = set()
    for arquivo in sorted(PASTA.glob("*.json")):
        texto = str(json.loads(arquivo.read_text(encoding="utf-8")).get("text") or "")
        if texto in vistos:
            continue
        vistos.add(texto)
        linhas = texto.split("\n")
        meio = len(linhas) // 2
        yield arquivo.name, {"texto": texto, "ocrUsado": True}
        yield arquivo.name + "#invertido", {"texto": "\n".join(reversed(linhas))}
        yield arquivo.name + "#maiusculo", {"texto": texto.upper()}
        yield arquivo.name + "#metade1", {"texto": "\n".join(linhas[:meio])}
        yield arquivo.name + "#metade2", {"texto": "\n".join(linhas[meio:])}
        yield arquivo.name + "#crlf", {"texto": texto.replace("\n", "\r\n")}
        yield arquivo.name + "#esperado", {"texto": texto, "provedorEsperado": "Internet", "valorEsperado": "119.90",
                                           "vencimentoEsperado": "2026-11-10"}
    for i, texto in enumerate(EXTRAS):
        yield f"extra{i}", {"texto": texto}
        yield f"extra{i}#esperado", {"texto": texto, "provedorEsperado": "OPIX", "valorEsperado": 119.9}


def iguais(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) < 1e-9
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(iguais(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(iguais(x, y) for x, y in zip(a, b))
    return a == b


def main():
    lista = list(casos())
    cliente = app.test_client()
    python = {}
    for nome, payload in lista:
        resposta = cliente.post("/api/extracao/texto", json=payload).get_json()
        resposta.pop("extrator", None)
        python[nome] = resposta
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / "casos.json"
        entrada.write_text(json.dumps(dict(lista), ensure_ascii=False), encoding="utf-8")
        script = (
            "const X=require(process.argv[1]);const fs=require('fs');"
            "const c=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const o={};"
            "for(const [k,p] of Object.entries(c)){const r=X.extrairDoTexto(p);delete r.extrator;o[k]=r;}"
            "process.stdout.write(JSON.stringify(o));"
        )
        saida = subprocess.run(["node", "-e", script, str(RAIZ / "n8n" / "lib" / "extrator.js"), str(entrada)],
                               capture_output=True, check=True)
        js = json.loads(saida.stdout.decode("utf-8"))
    diferencas = 0
    for nome, _ in lista:
        a, b = python[nome], js[nome]
        if iguais(a, b):
            continue
        diferencas += 1
        for chave in sorted(set(a) | set(b)):
            if not iguais(a.get(chave), b.get(chave)):
                print(f"  {nome[:60]:<60} {chave:<20} python={str(a.get(chave))[:50]!r} js={str(b.get(chave))[:50]!r}")
    print(f"\nParidade: {len(lista) - diferencas}/{len(lista)} casos idênticos.")
    sys.exit(1 if diferencas else 0)


if __name__ == "__main__":
    main()
