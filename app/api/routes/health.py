import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.core.dependencies import get_llm_service, get_vector_service
from app.core.metrics import metrics
from app.infrastructure.gateways.deepseek_gateway import DeepSeekGateway
from app.infrastructure.repositories.faiss_repository import FAISSVectorRepository

router = APIRouter()
logger = logging.getLogger("rag")


@router.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)


@router.get("/health")
async def health_check(vs: FAISSVectorRepository = Depends(get_vector_service)):
    return {
        "status": "healthy",
        "service": "Insurance RAG Assistant",
        "vector_store": vs.get_collection_stats(),
    }


@router.get("/status")
async def get_status(vs: FAISSVectorRepository = Depends(get_vector_service)):
    count = vs.count()
    return {"total_chunks": count, "ready": count > 0}


@router.get("/stats")
async def get_stats(
    vs: FAISSVectorRepository = Depends(get_vector_service),
    llm: DeepSeekGateway = Depends(get_llm_service),
):
    try:
        vs_stats = vs.get_collection_stats()
        success, llm_status = llm.test_connection()
        return {
            "vector_store": vs_stats,
            "llm_service": {
                "status": "connected" if success else "disconnected",
                "message": llm_status,
            },
            "temp_directory": "temp_uploads",
            "service": "Insurance RAG Assistant",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao obter estatísticas: {exc}")


@router.get("/metrics")
async def get_metrics(vs: FAISSVectorRepository = Depends(get_vector_service)):
    return {
        "vector_store": vs.get_collection_stats(),
        "queries": metrics.stats(),
    }
