FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Instalar FFmpeg, fontes e dependências essenciais
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        wget \
        curl \
        fontconfig \
        fonts-dejavu-core \
        fonts-dejavu-extra \
        fonts-liberation \
        fonts-noto-core \
        fonts-noto-ui-core \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Criar diretório de fontes customizadas que o código espera
RUN mkdir -p /usr/share/fonts/custom

# Baixar e instalar fontes Liberation no diretório correto
RUN wget -q https://github.com/liberationfonts/liberation-fonts/releases/download/2.1.5/liberation-fonts-ttf-2.1.5.tar.gz && \
    tar -xzf liberation-fonts-ttf-2.1.5.tar.gz && \
    cp liberation-fonts-ttf-2.1.5/*.ttf /usr/share/fonts/custom/ && \
    rm -rf liberation-fonts-ttf-2.1.5*

# Criar fontes Arial usando Liberation Sans no diretório custom
RUN cd /usr/share/fonts/custom && \
    cp LiberationSans-Regular.ttf Arial.ttf && \
    cp LiberationSans-Bold.ttf ArialBold.ttf && \
    cp LiberationSans-Italic.ttf ArialItalic.ttf && \
    cp LiberationSans-BoldItalic.ttf ArialBoldItalic.ttf

# Atualizar cache de fontes
RUN fc-cache -f -v

# Garantir que /tmp existe e tem permissões corretas
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

# Configurar variáveis de ambiente
ARG API_KEY
ARG MAX_QUEUE_LENGTH
ARG GUNICORN_TIMEOUT
ARG LOCAL_STORAGE_PATH
ARG GUNICORN_WORKERS
ARG GUNICORN_THREADS
ARG WORKER_CLASS
ARG GIT_SHA

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
ENV FONTCONFIG_PATH=/etc/fonts

# Expor a porta da aplicação
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/files || exit 1

# Comando para iniciar a aplicação
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", "--timeout", "12000", "--worker-class", "gthread", "--threads", "3", "app:app"]
