from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from collections import deque
import logging
import json as _json
import time as _time
import os
import uuid
from typing import Optional, Dict, Deque, Tuple

# ---------------------------------------------------------------------------
# Logging estruturado em JSON — nível configurável via LOG_LEVEL no .env
# ---------------------------------------------------------------------------
class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return _json.dumps(obj, ensure_ascii=False)

_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
logger = logging.getLogger("rag")
logger.addHandler(_handler)
logger.setLevel(_log_level)
logger.propagate = False

# Usar FAISS em vez de ChromaDB
from vector_store_faiss import create_vector_store
from llm_service import create_llm_service

# Inicializar serviços
vector_store = create_vector_store()
llm_service = create_llm_service()

app = FastAPI(
    title="Multi-Seguradora Insurance RAG Assistant",
    description="Assistente de IA para análise de apólices de seguro (Bradesco, Porto Seguro, etc.)",
    version="1.1.0"
)

# ... (CORS configuration remains same)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Pré-carrega o modelo de embeddings em background durante o startup.
    Isso move o carregamento pesado (~60s) para antes do primeiro request,
    evitando timeout no Render durante o healthcheck inicial."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, vector_store.warm_up)

# Criar diretório para arquivos temporários
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
# ENABLE_UPLOAD=false desabilita os endpoints de upload (produção com índice pré-construído)
ENABLE_UPLOAD = os.getenv("ENABLE_UPLOAD", "true").lower() != "false"

# ---------------------------------------------------------------------------
# Métricas em memória — últimas 24 horas
# ---------------------------------------------------------------------------
class MetricsStore:
    """Armazena latências de queries em memória sem dependências externas."""
    def __init__(self) -> None:
        self._events: Deque[Tuple[float, float, float]] = deque()  # (ts, retrieval_ms, llm_ms)

    def record(self, retrieval_ms: float, llm_ms: float) -> None:
        self._events.append((_time.time(), retrieval_ms, llm_ms))
        self._prune()

    def _prune(self) -> None:
        cutoff = _time.time() - 86400
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def stats(self) -> dict:
        self._prune()
        ev = list(self._events)
        n = len(ev)
        if n == 0:
            return {"queries_24h": 0, "avg_retrieval_ms": 0.0, "avg_llm_ms": 0.0, "avg_total_ms": 0.0}
        avg_r = sum(e[1] for e in ev) / n
        avg_l = sum(e[2] for e in ev) / n
        return {
            "queries_24h": n,
            "avg_retrieval_ms": round(avg_r, 1),
            "avg_llm_ms": round(avg_l, 1),
            "avg_total_ms": round(avg_r + avg_l, 1),
        }

metrics = MetricsStore()

ALLOWED_DOCUMENT_TYPES = {"apolice", "sinistro", "cobertura", "franquia", "endosso"}

class AskRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=500, description="Pergunta sobre os documentos")
    top_k: int = Field(default=10, ge=1, le=20, description="Número de trechos a recuperar")
    filter: Optional[Dict[str, str]] = Field(default=None, description="Filtro de metadados, ex: {'seguradora': 'Bradesco'}")
    document_type: Optional[str] = Field(default=None, description="Tipo de documento: apolice | sinistro | cobertura | franquia | endosso")

# Montar pasta estática para o frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve a página principal"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/health")
async def health_check():
    """Endpoint de verificação de saúde"""
    return {
        "status": "healthy",
        "service": "Insurance RAG Assistant",
        "vector_store": vector_store.get_collection_stats()
    }

@app.get("/status")
async def get_status():
    """Verifica se existem documentos prontos no banco"""
    count = vector_store.get_count()
    return {"total_chunks": count, "ready": count > 0}

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    seguradora: Optional[str] = Form(None),
    ano: Optional[int] = Form(None),
    tipo: Optional[str] = Form(None)
):
    """
    Endpoint para upload de PDFs com metadados
    """
    if not ENABLE_UPLOAD:
        raise HTTPException(status_code=403, detail="Upload desabilitado neste ambiente")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    # Preparar metadados
    metadata = {}
    if seguradora: metadata["seguradora"] = seguradora
    if ano: metadata["ano"] = ano
    if tipo: metadata["tipo"] = tipo
    
    # Salvar arquivo temporariamente com nome seguro (nunca usar file.filename no filesystem)
    safe_name = f"{uuid.uuid4().hex}.pdf"
    temp_path = os.path.join(TEMP_DIR, safe_name)

    try:
        # Salvar o arquivo
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Arquivo muito grande. Limite máximo: {MAX_FILE_SIZE // 1024 // 1024}MB"
            )
        with open(temp_path, "wb") as f:
            f.write(contents)

        # Processar o PDF com metadados
        chunks_added = vector_store.add_document(temp_path, metadata_input=metadata)

        # Limpar arquivo temporário
        os.remove(temp_path)

        return JSONResponse({
            "success": True,
            "message": f"Documento '{file.filename}' processado com sucesso!",
            "chunks_added": chunks_added,
            "filename": file.filename,
            "metadata": metadata
        })

    except HTTPException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF: {str(e)}")

# Lista de seguradoras permitidas para validação
ALLOWED_SEGURADORAS = ["Bradesco", "Porto Seguro", "Azul", "Allianz", "Tokio Marine", "Liberty", "Mapfre"]

@app.post("/admin/upload")
async def admin_upload_pdf(
    file: UploadFile = File(...),
    seguradora: str = Form(...),
    ano: int = Form(...),
    tipo: Optional[str] = Form("Geral"),
    x_admin_key: str = Header(...)
):
    """
    Endpoint administrativo para upload de documentos com curadoria.
    Requer o header X-Admin-Key com o valor de ADMIN_API_KEY do .env
    """
    if not ENABLE_UPLOAD:
        raise HTTPException(status_code=403, detail="Upload desabilitado neste ambiente")

    if not ADMIN_API_KEY or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Chave de administrador inválida ou ausente")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")
    
    # Validação da seguradora
    if seguradora not in ALLOWED_SEGURADORAS:
        raise HTTPException(
            status_code=400, 
            detail=f"Seguradora não permitida. Escolha entre: {', '.join(ALLOWED_SEGURADORAS)}"
        )
    
    # Preparar metadados
    metadata = {
        "seguradora": seguradora,
        "ano": ano,
        "tipo": tipo
    }
    
    # Salvar arquivo temporariamente com nome seguro (nunca usar file.filename no filesystem)
    safe_name = f"{uuid.uuid4().hex}.pdf"
    temp_path = os.path.join(TEMP_DIR, safe_name)
    
    try:
        # Salvar o arquivo
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Arquivo muito grande. Limite máximo: {MAX_FILE_SIZE // 1024 // 1024}MB"
            )
        with open(temp_path, "wb") as f:
            f.write(contents)

        # Processar o PDF com metadados
        chunks_added = vector_store.add_document(temp_path, metadata_input=metadata)

        # Limpar arquivo temporário
        os.remove(temp_path)

        return JSONResponse({
            "success": True,
            "message": f"Documento da {seguradora} processado com sucesso!",
            "chunks_added": chunks_added,
            "filename": file.filename,
            "metadata": metadata
        })

    except HTTPException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF administrativo: {str(e)}")

@app.post("/ask")
async def ask_question(data: AskRequest):
    """
    Endpoint para fazer perguntas sobre os documentos com suporte a filtro.

    Body: { "question": "...", "top_k": 10, "filter": {"seguradora": "Bradesco"}, "document_type": "apolice" }
    """
    if data.document_type is not None and data.document_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"document_type inválido. Valores aceitos: {', '.join(sorted(ALLOWED_DOCUMENT_TYPES))}"
        )

    seguradora = data.filter.get("seguradora") if data.filter else None

    t0 = _time.perf_counter()
    try:
        # Etapa 1: recuperação FAISS
        t1 = _time.perf_counter()
        context = vector_store.query_documents(data.question, n_results=data.top_k, filter_dict=data.filter)
        retrieval_ms = (_time.perf_counter() - t1) * 1000

        if not context:
            logger.info(_json.dumps({"event": "query_no_context", "filter": data.filter}))
            return JSONResponse({
                "success": True,
                "answer": "Não encontrei informações relevantes nos documentos filtrados para responder sua pergunta.",
                "context_used": [],
                "has_context": False
            })

        # Etapa 2: geração LLM
        t2 = _time.perf_counter()
        answer = llm_service.generate_answer(context, data.question, seguradora=seguradora, document_type=data.document_type)
        llm_ms = (_time.perf_counter() - t2) * 1000

        total_ms = (_time.perf_counter() - t0) * 1000
        metrics.record(retrieval_ms, llm_ms)
        logger.info(_json.dumps({
            "event": "query",
            "retrieval_ms": round(retrieval_ms, 1),
            "llm_ms": round(llm_ms, 1),
            "total_ms": round(total_ms, 1),
            "chunks": len(context),
            "filter": data.filter,
            "document_type": data.document_type,
        }))

        # Preparar contexto para retorno
        context_preview = [
            {
                "text": ctx["text"][:200] + "..." if len(ctx["text"]) > 200 else ctx["text"],
                "source": ctx["source"],
                "page": ctx.get("page", 0),
                "seguradora": ctx.get("seguradora"),
                "relevance_score": round(ctx["relevance_score"], 3)
            }
            for ctx in context
        ]

        return JSONResponse({
            "success": True,
            "answer": answer,
            "context_used": context_preview,
            "has_context": True,
            "context_count": len(context)
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar pergunta: {str(e)}")

@app.get("/stats")
async def get_stats():
    """Retorna estatísticas do sistema"""
    try:
        vs_stats = vector_store.get_collection_stats()
        
        # Testar conexão com DeepSeek
        success, llm_status = llm_service.test_connection()
        
        return {
            "vector_store": vs_stats,
            "llm_service": {
                "status": "connected" if success else "disconnected",
                "message": llm_status
            },
            "temp_directory": TEMP_DIR,
            "service": "Bradesco Insurance RAG Assistant"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter estatísticas: {str(e)}")

@app.get("/metrics")
async def get_metrics():
    """Métricas operacionais: volume de queries (24h) e latências médias por etapa."""
    return {
        "vector_store": vector_store.get_collection_stats(),
        "queries": metrics.stats(),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)