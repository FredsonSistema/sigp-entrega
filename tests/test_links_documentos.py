"""Todo link relativo dos documentos (.md) do repositório da entrega aponta para um arquivo que existe.

Só roda no repositório da entrega (marcado por .sigp-entrega, criado por entrega/montar-entrega.ps1): os documentos
apontam para o caminho dos arquivos no pacote (por exemplo, abrir-sigp.ps1 na raiz), que no sistema completo fica em entrega/.
"""
import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)\s]+)\)")
BLOCO_DE_CODIGO = re.compile(r"```.*?```", re.S)


@unittest.skipUnless((ROOT / ".sigp-entrega").exists(), "só no repositório da entrega")
class LinksDosDocumentos(unittest.TestCase):
    def test_links_relativos_existem(self):
        quebrados, total = [], 0
        for md in ROOT.rglob("*.md"):
            if {".git", "node_modules"} & set(md.parts):
                continue
            texto = BLOCO_DE_CODIGO.sub("", md.read_text(encoding="utf-8-sig", errors="replace"))
            for alvo in LINK.findall(texto):
                if alvo.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                caminho = unquote(alvo.split("#")[0])
                if not caminho:
                    continue
                total += 1
                if not (md.parent / caminho).resolve().exists():
                    quebrados.append(f"{md.relative_to(ROOT)} -> {alvo}")
        self.assertGreater(total, 100, "poucos links: o teste não está lendo os documentos")
        self.assertEqual(quebrados, [], "links quebrados")


if __name__ == "__main__":
    unittest.main()
