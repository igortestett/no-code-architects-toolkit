FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Instalar apenas FFmpeg e dependências essenciais
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        wget \
        curl \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Garantir que /tmp existe e tem permissões corretas para armazenamento local
RUN chmod 777 /tmp && \
    mkdir -p /tmp/downloads && \
    chmod 777 /tmp/downloads

# Copiar requirements.txt primeiro para otimizar cache do Docker
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir jsonschema

# Copiar todo o código da aplicação
COPY . .

# Configurar apenas as variáveis de ambiente necessárias (removidas as do S3/Minio)
ARG API_KEY
ARG MAX_QUEUE_LENGTH
ARG GUNICORN_TIMEOUT
ARG LOCAL_STORAGE_PATH
ARG GUNICORN_WORKERS
ARG GUNICORN_THREADS
ARG WORKER_CLASS
ARG GIT_SHA

# Definir variáveis de ambiente
ENV API_KEY=$API_KEY
ENV MAX_QUEUE_LENGTH=$MAX_QUEUE_LENGTH
ENV GUNICORN_TIMEOUT=$GUNICORN_TIMEOUT
ENV LOCAL_STORAGE_PATH=/tmp
ENV GUNICORN_WORKERS=$GUNICORN_WORKERS
ENV GUNICORN_THREADS=$GUNICORN_THREADS
ENV WORKER_CLASS=$WORKER_CLASS
ENV GIT_SHA=$GIT_SHA

# Variáveis de ambiente Flask
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Expor a porta da aplicação
EXPOSE 8080

# Health check para verificar se a aplicação está funcionando
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/files || exit 1

# Comando para iniciar a aplicação usando Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", "--timeout", "12000", "--worker-class", "gthread", "--threads", "3", "app:app"]
