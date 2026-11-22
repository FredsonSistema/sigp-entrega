import json
import logging
import os
import re
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore


MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PAGES = 10
PORT = int(os.environ.get("PORT", "5002"))
PROCESS_LOCK = BoundedSemaphore(1)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sigp-ocr")


class PdfProcessingError(Exception):
    def __init__(self, message: str, **extra: object) -> None:
        super().__init__(message)
        self.extra = extra


# PDFs com senha (Brisanet, Claro, Domínio...): a senha é o começo do CNPJ do tomador (empresa do grupo).
# Só as regras ficam na configuração (SIGP_PDF_SENHA_CNPJS: raízes/CNPJs separados por vírgula); a senha
# que abriu o arquivo nunca é registrada nem devolvida.
PREFIXOS_SENHA = (4, 5, 6, 8)


def candidatas_senha(config: str | None = None) -> list[str]:
    config = os.environ.get("SIGP_PDF_SENHA_CNPJS", "") if config is None else config
    vistas: list[str] = []
    for item in config.split(","):
        digitos = re.sub(r"\D", "", item)
        tamanhos = [n for n in PREFIXOS_SENHA if n <= len(digitos)] + ([len(digitos)] if len(digitos) > 8 else [])
        for n in tamanhos:
            if digitos[:n] not in vistas:
                vistas.append(digitos[:n])
    return vistas


def _abre(pdf_path: Path, senha: str | None) -> subprocess.CompletedProcess:
    cmd = ["pdfinfo"] + (["-upw", senha] if senha else []) + [str(pdf_path)]
    return subprocess.run(cmd, capture_output=True, timeout=15, check=False)


def senha_do_pdf(pdf_path: Path) -> tuple[bool, str | None]:
    """(protegido, senha). Sem senha de usuário: (False, None). Protegido e aberto: (True, senha)."""
    inicial = _abre(pdf_path, None)
    if inicial.returncode == 0 or b"password" not in inicial.stderr.lower():
        return False, None
    for senha in candidatas_senha():
        if _abre(pdf_path, senha).returncode == 0:
            return True, senha
    raise PdfProcessingError(
        "PDF protegido por senha: nenhuma regra cadastrada abriu o arquivo.", pdfProtegido=True, desbloqueado=False,
    )


MONTH_NUMBER = {
    "jan": "01", "janeiro": "01",
    "fev": "02", "fevereiro": "02",
    "mar": "03", "marco": "03", "março": "03",
    "abr": "04", "abril": "04",
    "mai": "05", "maio": "05",
    "jun": "06", "junho": "06",
    "jul": "07", "julho": "07",
    "ago": "08", "agosto": "08",
    "set": "09", "setembro": "09",
    "out": "10", "outubro": "10",
    "nov": "11", "novembro": "11",
    "dez": "12", "dezembro": "12",
}
MONTH_DATE = re.compile(
    r"\b(\d{1,2})\s*[/.-]\s*("
    + "|".join(sorted(MONTH_NUMBER, key=len, reverse=True))
    + r")\s*[/.-]\s*(\d{4})\b",
    re.IGNORECASE,
)


def normalize_ocr_text(text: str) -> str:
    def normalize_month_date(match: re.Match[str]) -> str:
        day, month, year = match.groups()
        return f"{int(day):02d}/{MONTH_NUMBER[month.lower()]}/{year}"

    text = MONTH_DATE.sub(normalize_month_date, text)
    return re.sub(
        r"\b(emiss[aã]o)\s+desta\s+conta\b",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )


def extract_text(pdf_data: bytes) -> dict[str, object]:
    if b"%PDF-" not in pdf_data[:1024]:
        raise PdfProcessingError("O arquivo recebido não parece ser um PDF válido.")

    with tempfile.TemporaryDirectory(prefix="sigp-ocr-") as temp_dir:
        work_dir = Path(temp_dir)
        pdf_path = work_dir / "documento.pdf"
        pdf_path.write_bytes(pdf_data)
        protegido, senha = senha_do_pdf(pdf_path)
        senha_args = ["-upw", senha] if senha else []

        text_result = subprocess.run(
            [
                "pdftotext",
                *senha_args,
                "-f", "1",
                "-l", str(MAX_PAGES),
                "-layout",
                str(pdf_path),
                "-",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if text_result.returncode == 0:
            text = text_result.stdout.decode("utf-8", errors="replace").strip()
        else:
            logger.warning("pdftotext falhou; tentando OCR local.")
            text = ""

        ocr_used = not bool(text)
        if ocr_used:
            prefix = work_dir / "pagina"
            render_result = subprocess.run(
                [
                    "pdftoppm",
                    *senha_args,
                    "-f", "1",
                    "-l", str(MAX_PAGES),
                    "-scale-to", "1000",
                    "-jpeg",
                    str(pdf_path),
                    str(prefix),
                ],
                capture_output=True,
                timeout=60,
                check=False,
            )
            if render_result.returncode != 0:
                logger.error(
                    "pdftoppm falhou: %s",
                    render_result.stderr.decode("utf-8", errors="replace")[-1000:],
                )
                raise PdfProcessingError("Não foi possível converter as páginas do PDF para OCR.")

            pages = sorted(
                work_dir.glob("pagina-*.jpg"),
                key=lambda path: int(path.stem.rsplit("-", 1)[1]),
            )
            page_texts = []
            ocr_env = os.environ.copy()
            ocr_env["OMP_THREAD_LIMIT"] = "1"
            for page in pages:
                ocr_result = subprocess.run(
                    [
                        "tesseract",
                        str(page),
                        "stdout",
                        "-l", "por",
                        "--psm", "11",
                    ],
                    capture_output=True,
                    timeout=30,
                    check=False,
                    env=ocr_env,
                )
                if ocr_result.returncode != 0:
                    logger.error(
                        "Tesseract falhou: %s",
                        ocr_result.stderr.decode("utf-8", errors="replace")[-1000:],
                    )
                    raise PdfProcessingError("O OCR local não conseguiu processar uma página do PDF.")
                page_texts.append(ocr_result.stdout.decode("utf-8", errors="replace").strip())
            text = normalize_ocr_text("\n".join(value for value in page_texts if value).strip())

    return {
        "text": text,
        "textEncontrado": bool(text),
        "ocrUsado": ocr_used,
        "paginasMaximasProcessadas": MAX_PAGES,
        "pdfProtegido": protegido,
        "aviso": "" if text else "Não foi possível reconhecer texto no PDF, mesmo após o OCR local.",
    }


class OcrHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            raizes = [r for r in os.environ.get("SIGP_PDF_SENHA_CNPJS", "").split(",") if re.sub(r"\D", "", r)]
            self._send_json(200, {"ok": True, "regrasSenha": len(raizes)})
            return
        self._send_json(404, {"ok": False, "error": "Rota não encontrada."})

    def do_POST(self) -> None:
        if self.path != "/extract":
            self._send_json(404, {"ok": False, "error": "Rota não encontrada."})
            return
        if not PROCESS_LOCK.acquire(blocking=False):
            self._send_json(503, {"ok": False, "error": "Outro PDF está em processamento; tente novamente em instantes."})
            return

        try:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json(400, {"ok": False, "error": "Cabeçalho Content-Length inválido."})
                return

            if content_length <= 0:
                self._send_json(400, {"ok": False, "error": "O corpo do PDF está vazio."})
                return
            if content_length > MAX_UPLOAD_BYTES:
                self._send_json(413, {"ok": False, "error": "O PDF excede o limite de 15 MiB."})
                return

            pdf_data = self.rfile.read(content_length)
            if len(pdf_data) != content_length:
                self._send_json(400, {"ok": False, "error": "O upload do PDF foi interrompido."})
                return

            try:
                self._send_json(200, {"ok": True, **extract_text(pdf_data)})
            except PdfProcessingError as error:
                self._send_json(422, {"ok": False, "error": str(error), **error.extra})
            except subprocess.TimeoutExpired:
                logger.exception("Tempo limite excedido durante o processamento do PDF.")
                self._send_json(504, {"ok": False, "error": "O processamento do PDF excedeu o tempo limite."})
            except OSError:
                logger.exception("Ferramenta local de PDF/OCR indisponível.")
                self._send_json(500, {"ok": False, "error": "Uma ferramenta local de PDF/OCR não está disponível."})
        finally:
            PROCESS_LOCK.release()

    def log_message(self, format_string: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format_string % args)


if __name__ == "__main__":
    logger.info("Serviço OCR local iniciado na porta %s.", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), OcrHandler).serve_forever()
