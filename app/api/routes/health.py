import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.core.dependencies import get_vector_service, get_llm_service
from app.core.metrics import metrics
from app.services.vector_service import FAISSStore
from app.services.llm_service import LLMService

router = APIRouter()
logger = logging.getLogger("rag")


@router.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve a página principal"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)


@router.get("/health")
async def health_check(vs: FAISSStore = Depends(get_vector_service)):
    """Endpoint de verificação de saúde"""
    return {
        "status": "healthy",
        "service": "Insurance RAG Assistant",
        "vector_store": vs.get_collection_stats()
    }


@router.get("/status")
async def get_status(vs: FAISSStore = Depends(get_vector_service)):
    """Verifica se existem documentos prontos no banco"""
    count = vs.get_count()
    return {"total_chunks": count, "ready": count > 0}


@router.get("/stats")
async def get_stats(
    vs: FAISSStore = Depends(get_vector_service),
    llm: LLMService = Depends(get_llm_service),
):
    """Retorna estatísticas do sistema"""
    try:
        vs_stats = vs.get_collection_stats()
        success, llm_status = llm.test_connection()
        return {
            "vector_store": vs_stats,
            "llm_service": {
                "status": "connected" if success else "disconnected",
                "message": llm_status
            },
            "temp_directory": "temp_uploads",
            "service": "Bradesco Insurance RAG Assistant"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter estatísticas: {str(e)}")


@router.get("/metrics")
async def get_metrics(vs: FAISSStore = Depends(get_vector_service)):
    """Métricas operacionais: volume de queries (24h) e latências médias por etapa."""
    return {
        "vector_store": vs.get_collection_stats(),
        "queries": metrics.stats(),
    }
