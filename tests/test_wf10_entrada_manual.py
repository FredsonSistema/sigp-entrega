"""WF-10 (entrada manual): roda o teste em node (etapas iguais às do WF-08, sem Gmail, chave conferida, documento montado
no formato do anexo de e-mail). O WF-10 é gerado do WF-08: rode n8n/wf10/build_wf10.py depois de mudar o WF-08."""
import shutil
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
WF10 = RAIZ / "n8n_workflow_wf10_entrada_manual.json"
if not WF10.exists():
    WF10 = RAIZ / "n8n" / "workflows" / "n8n_workflow_wf10_entrada_manual.json"  # pacote da entrega
WF08 = RAIZ / "n8n_workflow_wf08_gmail_inbox.json"
if not WF08.exists():
    WF08 = RAIZ / "n8n" / "workflows" / "n8n_workflow_wf08_gmail_inbox.json"


@unittest.skipUnless(shutil.which("node"), "node não instalado")
@unittest.skipUnless((RAIZ / "docs" / "XML para testes").exists(), "sem os XML de teste (ficam fora do pacote)")
class Wf10Test(unittest.TestCase):
    def test_wf10(self):
        r = subprocess.run(["node", str(RAIZ / "tests" / "n8n" / "wf10_entrada_manual.test.js"), str(WF10), str(WF08)],
                           cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])

    def test_wf10_gerado_do_wf08_atual(self):
        """Mudou o WF-08 e esqueceu de gerar o WF-10: as etapas divergem e o teste em node acusa; aqui, o arquivo existe."""
        self.assertTrue(WF10.exists() and WF08.exists())


if __name__ == "__main__":
    unittest.main()
