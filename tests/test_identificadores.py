"""Situações 3 a 5 — leitura do código do cliente/contrato (mesmos casos do WF-08: tests/casos_identificadores.json)."""
import json
import unittest
from pathlib import Path

from backend import identificadores

CASOS = json.loads((Path(__file__).parent / "casos_identificadores.json").read_text(encoding="utf-8"))


class IdentificadoresTests(unittest.TestCase):
    def test_casos_reais(self):
        for caso in CASOS:
            obtido = [[i["tipo"], i["valor"]] for i in identificadores.ler(caso["texto"])]
            self.assertEqual(obtido, caso["esperado"], caso["nome"])

    def test_normalizacao(self):
        self.assertEqual(identificadores.normalizar("00077120"), "77120")
        self.assertEqual(identificadores.normalizar("CT-778/2"), "CT7782")
        self.assertEqual(identificadores.codigos_do_provedor({"codigosCliente": "5174, 00077120; X"}), ["5174", "77120", "X"])


if __name__ == "__main__":
    unittest.main()
