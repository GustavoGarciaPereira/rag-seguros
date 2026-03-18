FROM python:3.11-slim

# Evita geração de .pyc e bufferiza stdout/stderr diretamente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências do sistema necessárias para faiss-cpu e sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Instala torch CPU-only ANTES do requirements.txt para evitar download de ~2GB de pacotes CUDA.
# Sem isso, pip resolve torch com suporte NVIDIA e estoura a memória do Render (512MB).
RUN pip install --no-cache-dir \
    torch==2.2.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do projeto
COPY . .

# Cria diretórios necessários em tempo de build
RUN mkdir -p faiss_db temp_uploads static

EXPOSE 8000

# Healthcheck: testa /health a cada 30s, timeout 10s, 3 retries antes de marcar unhealthy
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Produção: sem --reload
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
