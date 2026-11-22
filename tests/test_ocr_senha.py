"""Regras de senha de PDF do serviço OCR (ocr/app.py): candidatas a partir das raízes de CNPJ do grupo."""
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ocr_app", RAIZ / "ocr" / "app.py")
ocr_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocr_app)


def _proc(rc, err=b""):
    return subprocess.CompletedProcess([], rc, b"", err)


class CandidatasSenhaTest(unittest.TestCase):
    def test_prefixos_de_cada_raiz_sem_repetir(self):
        self.assertEqual(
            ocr_app.candidatas_senha("76.543.210, 65432109"),
            ["7654", "76543", "765432", "76543210", "6543", "65432", "654321", "65432109"],
        )

    def test_cnpj_completo_entra_tambem(self):
        self.assertEqual(ocr_app.candidatas_senha("76543210000130")[-1], "76543210000130")

    def test_sem_configuracao_sem_candidatas(self):
        self.assertEqual(ocr_app.candidatas_senha(""), [])


class SenhaDoPdfTest(unittest.TestCase):
    def test_pdf_sem_senha(self):
        with mock.patch.object(ocr_app, "_abre", return_value=_proc(0)):
            self.assertEqual(ocr_app.senha_do_pdf(Path("x.pdf")), (False, None))

    def test_pdf_com_senha_aberto_pela_regra(self):
        def abre(_path, senha):
            return _proc(0) if senha == "65432" else _proc(1, b"Command Line Error: Incorrect password")
        with mock.patch.object(ocr_app, "_abre", side_effect=abre), \
                mock.patch.dict("os.environ", {"SIGP_PDF_SENHA_CNPJS": "76543210,65432109"}):
            self.assertEqual(ocr_app.senha_do_pdf(Path("x.pdf")), (True, "65432"))

    def test_pdf_com_senha_desconhecida(self):
        with mock.patch.object(ocr_app, "_abre", return_value=_proc(1, b"Incorrect password")), \
                mock.patch.dict("os.environ", {"SIGP_PDF_SENHA_CNPJS": "76543210"}):
            with self.assertRaises(ocr_app.PdfProcessingError) as ctx:
                ocr_app.senha_do_pdf(Path("x.pdf"))
        self.assertTrue(ctx.exception.extra["pdfProtegido"])
        self.assertNotIn("7654", str(ctx.exception))

    def test_pdf_corrompido_nao_e_tratado_como_senha(self):
        with mock.patch.object(ocr_app, "_abre", return_value=_proc(1, b"Syntax Error: Couldn't find trailer")):
            self.assertEqual(ocr_app.senha_do_pdf(Path("x.pdf")), (False, None))


if __name__ == "__main__":
    unittest.main()
