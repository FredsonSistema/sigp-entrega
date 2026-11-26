"""O pacote de entrega roda a mesma IA que foi avaliada (prompt, modelo e busca).

A avaliação final (sqlserver/evidence/parte3/ia-avaliacao-final.json) registra o /health do serviço medido.
Este teste confere que o docker-compose.yml do pacote e o instalador sobem exatamente essa configuração, para não
avaliar um sistema e entregar outro.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# No sistema completo o pacote fica em entrega/; no repositório do pacote, na raiz.
PACOTE = ROOT / "entrega" if (ROOT / "entrega" / "docker-compose.yml").exists() else ROOT
AVALIACAO = ROOT / "docs" / "entrega-academica" / "sqlserver" / "evidence" / "parte3" / "ia-avaliacao-final.json"


def _ambiente_academic_ai(compose: Path) -> dict:
    texto = compose.read_text(encoding="utf-8-sig")
    bloco = re.search(r"\n  academic-ai:\n(.*?)(?=\n  [a-z][\w-]*:\n|\nvolumes:|\Z)", texto, re.S).group(1)
    env = re.search(r"\n    environment:\n((?:      .*\n|\s*#.*\n)+)", bloco + "\n").group(1)
    valores = {}
    for linha in env.splitlines():
        m = re.match(r"\s+([A-Z_]+):\s*(.*?)\s*$", linha)
        if m:
            valor = m.group(2)
            padrao = re.fullmatch(r"\$\{[A-Z_]+-(.*)\}", valor) or re.fullmatch(r"\$\{[A-Z_]+:-(.*)\}", valor)
            valores[m.group(1)] = padrao.group(1) if padrao else valor
    return valores


class PacoteRodaAIAvaliada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servico = json.loads(AVALIACAO.read_text(encoding="utf-8"))["servico"]

    def _confere(self, compose: Path):
        env = _ambiente_academic_ai(compose)
        self.assertEqual(env.get("EMBED_MODEL"), self.servico["embed_model"], compose)
        self.assertEqual(env.get("OLLAMA_MODEL"), self.servico["model"], compose)
        self.assertEqual(env.get("MODEL_PROFILE"), self.servico["model_profile"], compose)

    def test_pacote_usa_a_configuracao_avaliada(self):
        self._confere(PACOTE / "docker-compose.yml")

    def test_ambiente_academico_usa_a_configuracao_avaliada(self):
        self._confere(ROOT / "docs" / "entrega-academica" / "sqlserver" / "compose.academic.yml")

    def test_prompt_do_codigo_e_o_avaliado(self):
        app = (ROOT / "docs" / "entrega-academica" / "ia" / "app.py").read_text(encoding="utf-8")
        versao = re.search(r'^PROMPT_VERSION = "([^"]+)"', app, re.M).group(1)
        self.assertEqual(versao, self.servico["prompt_version"])

    def test_instalador_baixa_os_modelos_avaliados(self):
        instalador = (PACOTE / "instalar.ps1").read_text(encoding="utf-8-sig")
        linha = next(l for l in instalador.splitlines() if l.startswith("foreach ($m in @("))
        self.assertIn(f"'{self.servico['embed_model']}'", linha)
        self.assertIn(f"'{self.servico['model']}'", linha)


if __name__ == "__main__":
    unittest.main()
