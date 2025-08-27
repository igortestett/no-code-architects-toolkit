# Base image - mantém Python 3.9 que funcionava
FROM python:3.9-slim

# Install system dependencies incluindo fontes
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    tar \
    xz-utils \
    fonts-liberation \
    fontconfig \
    ffmpeg \
    git \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Criar diretório de fontes custom e copiar Liberation como Arial
RUN mkdir -p /usr/share/fonts/custom && \
    cp /usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf /usr/share/fonts/custom/Arial.ttf 2>/dev/null || \
    find /usr/share/fonts -name "*Liberation*Sans*Regular*" -exec cp {} /usr/share/fonts/custom/Arial.ttf \; || \
    find /usr/share/fonts -name "*DejaVu*Sans.ttf" -exec cp {} /usr/share/fonts/custom/Arial.ttf \;

# Rebuild the font cache
RUN fc-cache -f -v

# Set work directory
WORKDIR /app

# Set environment variable for Whisper cache
ENV WHISPER_CACHE_DIR="/app/whisper_cache"

# Create cache directory
RUN mkdir -p ${WHISPER_CACHE_DIR} 

# Copy the requirements file first to optimize caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install openai-whisper && \
    pip install playwright && \
    pip install jsonschema 

# Create the appuser 
RUN useradd -m appuser 

# Give appuser ownership of the /app directory
RUN chown appuser:appuser /app 

# Switch to the appuser before downloading the model
USER appuser
RUN python -c "import os; print(os.environ.get('WHISPER_CACHE_DIR')); import whisper; whisper.load_model('base')"

# Install Playwright Chromium browser as appuser
RUN playwright install chromium

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Create run script
RUN echo '#!/bin/bash\n\
gunicorn --bind 0.0.0.0:8080 \
    --workers ${GUNICORN_WORKERS:-2} \
    --timeout ${GUNICORN_TIMEOUT:-300} \
    --worker-class sync \
    --keep-alive 80 \
    app:app' > /app/run_gunicorn.sh && \
    chmod +x /app/run_gunicorn.sh

# Run the shell script
CMD ["/app/run_gunicorn.sh"]
