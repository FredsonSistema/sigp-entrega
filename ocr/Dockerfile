FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py /app/app.py

ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 5002
USER 1000:1000

CMD ["python", "/app/app.py"]
