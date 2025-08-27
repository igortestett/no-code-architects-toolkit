FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Instalar apenas FFmpeg do repositório oficial (sem configuração de DNS)
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        wget \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Configurar variáveis de ambiente
ARG S3_ENDPOINT_URL
ARG S3_ACCESS_KEY
ARG S3_SECRET_KEY  
ARG S3_BUCKET_NAME
ARG S3_REGION
ARG API_KEY
ARG MAX_QUEUE_LENGTH
ARG GUNICORN_TIMEOUT
ARG LOCAL_STORAGE_PATH
ARG GUNICORN_WORKERS
ARG GUNICORN_THREADS
ARG WORKER_CLASS

ENV S3_ENDPOINT_URL=$S3_ENDPOINT_URL
ENV S3_ACCESS_KEY=$S3_ACCESS_KEY
ENV S3_SECRET_KEY=$S3_SECRET_KEY
ENV S3_BUCKET_NAME=$S3_BUCKET_NAME
ENV S3_REGION=$S3_REGION
ENV API_KEY=$API_KEY
ENV MAX_QUEUE_LENGTH=$MAX_QUEUE_LENGTH
ENV GUNICORN_TIMEOUT=$GUNICORN_TIMEOUT
ENV LOCAL_STORAGE_PATH=$LOCAL_STORAGE_PATH
ENV GUNICORN_WORKERS=$GUNICORN_WORKERS
ENV GUNICORN_THREADS=$GUNICORN_THREADS
ENV WORKER_CLASS=$WORKER_CLASS

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# Comando para iniciar a aplicação
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", "--timeout", "12000", "--worker-class", "gthread", "--threads", "3", "app:app"]
