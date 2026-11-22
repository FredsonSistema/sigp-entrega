FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/cache/huggingface \
    SIGP_LORA_ADAPTER_PATH=/models/adapter

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
       torch==2.15.0+cpu \
    && python -m pip install --no-cache-dir \
       transformers==5.22.1 peft==0.21.2 Flask==3.1.0 \
    && useradd --uid 10002 --create-home modeluser \
    && mkdir -p /cache/huggingface \
    && chown -R modeluser:modeluser /cache

WORKDIR /app
COPY docs/entrega-academica/ia/finetuning/server.py /app/server.py
USER 10002

EXPOSE 5011
CMD ["python", "server.py"]
