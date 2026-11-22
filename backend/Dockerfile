FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo

# tzdata: "hoje" dos alertas de vencimento precisa ser a data de Brasília, não UTC.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/*.py /app/backend/
# Conhecimento do assistente em partes (JSON por tema).
COPY backend/conhecimento_assistente/ /app/backend/conhecimento_assistente/

EXPOSE 5001

CMD ["python", "-m", "backend.app"]
