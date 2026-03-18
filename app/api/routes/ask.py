import logging
import json as _json
import time as _time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.models.requests import AskRequest
from app.core.config import ALLOWED_DOCUMENT_TYPES
from app.core.dependencies import get_vector_service, get_llm_service
from app.core.metrics import metrics
from app.services.vector_service import FAISSStore
from app.services.llm_service import LLMService

router = APIRouter()
logger = logging.getLogger("rag")


@router.post("/ask")
async def ask_question(
    data: AskRequest,
    vs: FAISSStore = Depends(get_vector_service),
    llm: LLMService = Depends(get_llm_service),
):
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
        context = vs.search(data.question, n_results=data.top_k, filter_dict=data.filter)
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
        answer = llm.generate_answer(context, data.question, seguradora=seguradora, document_type=data.document_type)
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
