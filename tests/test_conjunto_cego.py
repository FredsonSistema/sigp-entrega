"""O conjunto cego da IA não pode mudar depois de congelado (docs/entrega-academica/ia/conjuntos-congelados.json)."""
import hashlib
import json
import unittest
from pathlib import Path

IA = Path(__file__).resolve().parents[1] / "docs" / "entrega-academica" / "ia"


class ConjuntoCegoTests(unittest.TestCase):
    def test_conjunto_cego_continua_igual_ao_congelado(self):
        trava = json.loads((IA / "conjuntos-congelados.json").read_text(encoding="utf-8"))
        for nome, info in trava["congelados"].items():
            # Quebras de linha normalizadas: um clone no Windows (core.autocrlf) troca LF por CRLF sem mudar o conteúdo.
            atual = hashlib.sha256((IA / nome).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            self.assertEqual(atual, info["sha256"], f"{nome} mudou depois de congelado: crie um conjunto novo em vez de editar este.")


if __name__ == "__main__":
    unittest.main()
