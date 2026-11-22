"""B-01: o extrator do n8n (n8n/lib/extrator.js) responde igual ao backend (POST /api/extracao/texto)."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node não instalado")
class ParidadeExtratorN8nTest(unittest.TestCase):
    def test_testes_da_lib(self):
        arquivos = [str(RAIZ / "tests" / "n8n" / nome) for nome in ("extrator.test.js", "xml_fiscal.test.js", "importar_csv.test.js")]
        r = subprocess.run(["node", "--test", *arquivos], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])

    def test_copia_do_leitor_de_xml_no_frontend_e_identica(self):
        # O navegador usa a mesma lib do n8n; se n8n/lib/xml_fiscal.js mudar, copie para frontend/modules/xml-fiscal.js.
        original = (RAIZ / "n8n" / "lib" / "xml_fiscal.js").read_bytes()
        copia = (RAIZ / "frontend" / "modules" / "xml-fiscal.js").read_bytes()
        self.assertEqual(original, copia, "frontend/modules/xml-fiscal.js desatualizado: copie de n8n/lib/xml_fiscal.js")

    @unittest.skipUnless((RAIZ / "tests" / "e2e" / ".data-test" / "ocr_textos").exists(), "sem textos OCR de teste")
    def test_paridade_com_backend(self):
        r = subprocess.run([sys.executable, "-W", "ignore", str(RAIZ / "tests" / "n8n" / "paridade_extrator.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])


if __name__ == "__main__":
    unittest.main()
