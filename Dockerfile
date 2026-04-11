FROM python:3.11-slim

# Evita geração de .pyc e bufferiza stdout/stderr diretamente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Garante que o cache do Hugging Face fique em um local previsível
    HF_HOME=/app/model_cache 

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Instala torch CPU-only (Perfeito!)
RUN pip install --no-cache-dir \
    torch==2.2.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- NOVIDADE 1: PRE-DOWNLOAD DO MODELO ---
# Isso embutirá os ~90MB do modelo na imagem. O boot no Render será instantâneo.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copia o restante do projeto
COPY . .

# Cria diretórios necessários
RUN mkdir -p faiss_db temp_uploads static model_cache

EXPOSE 8000

# Healthcheck (Mantido, está muito bom)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# --- NOVIDADE 2: LIMITAÇÃO DE WORKERS ---
# Forçamos '--workers 1' para que o FastAPI não tente abrir múltiplos processos 
# e estoure os 512MB de RAM.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
