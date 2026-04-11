import json as _json
import logging
import time as _time
from typing import Generator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import ALLOWED_DOCUMENT_TYPES
from app.core.dependencies import get_ask_use_case
from app.core.metrics import metrics
from app.models.requests import AskRequest
from app.use_cases.answer_question import AskInsuranceQuestion

router = APIRouter()
logger = logging.getLogger("rag")


@router.post("/ask")
def ask_question(
    data: AskRequest,
    use_case: AskInsuranceQuestion = Depends(get_ask_use_case),
):
    """Pergunta sobre os documentos indexados com suporte a filtro.

    Retorna Server-Sent Events:
    - ``{"type": "context", "data": [...]}`` — metadados dos trechos recuperados
    - ``{"type": "text", "data": "..."}``    — deltas de texto da resposta
    - ``{"type": "no_context"}``             — nenhum trecho encontrado
    - ``{"type": "error", "data": "..."}``   — erro durante o processamento

    Body: ``{"question": "...", "top_k": 15, "filter": {"seguradora": "Bradesco"}}``
    """
    if data.document_type is not None and data.document_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"document_type inválido. Valores aceitos: {', '.join(sorted(ALLOWED_DOCUMENT_TYPES))}",
        )

    seguradora = data.filter.get("seguradora") if data.filter else None
    logger.info("Filtro recebido via UI: %s", data.filter)

    def sse_stream() -> Generator[str, None, None]:
        # execute_stream is a plain sync method — safe to call from a sync generator.
        logger.info(
            "SSE stream iniciado | pergunta='%s...' top_k=%d filter=%s",
            data.question[:60],
            data.top_k,
            data.filter,
        )
        t0 = _time.perf_counter()
        try:
            reranked, text_stream = use_case.execute_stream(
                question=data.question,
                top_k=data.top_k,
                filter_dict=data.filter,
                seguradora=seguradora,
                document_type=data.document_type,
            )

            if not reranked:
                logger.info(
                    _json.dumps(
                        {
                            "event": "query_no_context",
                            "top_k": data.top_k,
                            "filter": data.filter,
                            "document_type": data.document_type,
                        }
                    )
                )
                yield f"data: {_json.dumps({'type': 'no_context'})}\n\n"
                return

            context_preview = [
                {
                    "text": ctx.text[:200] + "..." if len(ctx.text) > 200 else ctx.text,
                    "source": ctx.source,
                    "page": ctx.page,
                    "seguradora": ctx.seguradora,
                    "relevance_score": round(ctx.relevance_score, 3),
                }
                for ctx in reranked
            ]
            yield f"data: {_json.dumps({'type': 'context', 'data': context_preview})}\n\n"

            try:
                for chunk in text_stream:
                    if chunk:
                        yield f"data: {_json.dumps({'type': 'text', 'data': chunk})}\n\n"
            except Exception as stream_exc:
                logger.error("Erro no streaming LLM: %s", stream_exc, exc_info=True)
                yield f"data: {_json.dumps({'type': 'error', 'data': str(stream_exc)})}\n\n"
                return

            total_ms = (_time.perf_counter() - t0) * 1000
            metrics.record(0.0, total_ms)
            logger.info(
                _json.dumps(
                    {
                        "event": "query",
                        "total_ms": round(total_ms, 1),
                        "top_k": data.top_k,
                        "chunks_returned": len(reranked),
                        "filter": data.filter,
                        "document_type": data.document_type,
                    }
                )
            )

        except Exception as exc:
            logger.error("Erro no SSE stream: %s", exc, exc_info=True)
            yield f"data: {_json.dumps({'type': 'error', 'data': str(exc)})}\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
