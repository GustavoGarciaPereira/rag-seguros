import json as _json
import logging
import time as _time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import ALLOWED_DOCUMENT_TYPES
from app.core.dependencies import get_ask_use_case
from app.core.metrics import metrics
from app.models.requests import AskRequest
from app.use_cases.answer_question import AskInsuranceQuestion

router = APIRouter()
logger = logging.getLogger("rag")


@router.post("/ask")
async def ask_question(
    data: AskRequest,
    use_case: AskInsuranceQuestion = Depends(get_ask_use_case),
):
    """Pergunta sobre os documentos indexados com suporte a filtro.

    Body: ``{"question": "...", "top_k": 10, "filter": {"seguradora": "Bradesco"}}``
    """
    if data.document_type is not None and data.document_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"document_type inválido. Valores aceitos: {', '.join(sorted(ALLOWED_DOCUMENT_TYPES))}",
        )

    seguradora = data.filter.get("seguradora") if data.filter else None

    t0 = _time.perf_counter()
    try:
        t1 = _time.perf_counter()
        answer, context = use_case.execute(
            question=data.question,
            top_k=data.top_k,
            filter_dict=data.filter,
            seguradora=seguradora,
            document_type=data.document_type,
        )
        total_elapsed = (_time.perf_counter() - t1) * 1000

        if answer is None:
            logger.info(_json.dumps({"event": "query_no_context", "filter": data.filter}))
            return JSONResponse(
                {
                    "success": True,
                    "answer": "Não encontrei informações relevantes nos documentos filtrados para responder sua pergunta.",
                    "context_used": [],
                    "has_context": False,
                }
            )

        # Separa latências de forma aproximada (retrieval+rerank vs. geração)
        # A medição exata ficou no use case; aqui apenas registramos o total.
        retrieval_ms = 0.0
        llm_ms = total_elapsed
        metrics.record(retrieval_ms, llm_ms)

        logger.info(
            _json.dumps(
                {
                    "event": "query",
                    "total_ms": round(total_elapsed, 1),
                    "chunks": len(context),
                    "filter": data.filter,
                    "document_type": data.document_type,
                }
            )
        )

        context_preview = [
            {
                "text": ctx.text[:200] + "..." if len(ctx.text) > 200 else ctx.text,
                "source": ctx.source,
                "page": ctx.page,
                "seguradora": ctx.seguradora,
                "relevance_score": round(ctx.relevance_score, 3),
            }
            for ctx in context
        ]

        return JSONResponse(
            {
                "success": True,
                "answer": answer,
                "context_used": context_preview,
                "has_context": True,
                "context_count": len(context),
            }
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao processar pergunta: {exc}")
