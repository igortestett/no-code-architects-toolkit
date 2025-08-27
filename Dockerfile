FROM python:3.11-slim

# Configurar DNS para EasyPanel
RUN echo "nameserver 8.8.8.8" > /etc/resolv.conf && \
    echo "nameserver 8.8.4.4" >> /etc/resolv.conf

ENV DEBIAN_FRONTEND=noninteractive

# Instalar apenas FFmpeg do repositório oficial (muito mais simples)
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        wget \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Configurar diretório de trabalho
WORKDIR /app

# Copiar e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o código da aplicação
COPY . .

# Variáveis de ambiente (usando os build args do EasyPanel)
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

# Expor porta
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["python", "app.py"]
