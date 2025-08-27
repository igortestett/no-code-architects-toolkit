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

# Copiar fontes Liberation já disponíveis do sistema para o diretório custom
RUN find /usr/share/fonts -name "Liberation*.ttf" -exec cp {} /usr/share/fonts/custom/ \;

# Criar fontes Arial usando Liberation Sans no diretório custom
RUN cd /usr/share/fonts/custom && \
    if [ -f "LiberationSans-Regular.ttf" ]; then \
        cp LiberationSans-Regular.ttf Arial.ttf && \
        cp LiberationSans-Bold.ttf ArialBold.ttf 2>/dev/null || cp LiberationSans-Regular.ttf ArialBold.ttf && \
        cp LiberationSans-Italic.ttf ArialItalic.ttf 2>/dev/null || cp LiberationSans-Regular.ttf ArialItalic.ttf && \
        cp LiberationSans-BoldItalic.ttf ArialBoldItalic.ttf 2>/dev/null || cp LiberationSans-Regular.ttf ArialBoldItalic.ttf; \
    fi

# Fallback: Se Liberation não estiver disponível, criar Arial com DejaVu
RUN cd /usr/share/fonts/custom && \
    if [ ! -f "Arial.ttf" ]; then \
        find /usr/share/fonts -name "DejaVuSans.ttf" -exec cp {} Arial.ttf \; && \
        find /usr/share/fonts -name "DejaVuSans-Bold.ttf" -exec cp {} ArialBold.ttf \; 2>/dev/null || cp Arial.ttf ArialBold.ttf && \
        cp Arial.ttf ArialItalic.ttf && \
        cp Arial.ttf ArialBoldItalic.ttf; \
    fi

# Atualizar cache de fontes
RUN fc-cache -f -v

# Listar fontes disponíveis para debug
RUN ls -la /usr/share/fonts/custom/

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
