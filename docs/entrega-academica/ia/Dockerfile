FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg unixodbc \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends mssql-tools18 \
    && ln -s /opt/mssql-tools18/bin/sqlcmd /usr/local/bin/sqlcmd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY docs/entrega-academica/ia/app.py /app/app.py
COPY docs/entrega-academica/ia/rag_documents.json /app/rag_documents.json
COPY docs/entrega-academica/ia/prompts /app/prompts

RUN pip install --no-cache-dir Flask==3.1.0

RUN useradd --uid 10001 --create-home appuser \
    && chown -R appuser:appuser /app
USER 10001

EXPOSE 5010
CMD ["python", "app.py"]
