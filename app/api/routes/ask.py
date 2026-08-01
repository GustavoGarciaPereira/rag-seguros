import json as _json
import logging
import time as _time
import uuid as _uuid
from typing import Dict, Generator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import ALLOWED_DOCUMENT_TYPES, settings
from app.core.dependencies import get_ask_use_case, get_rate_limiter
from app.core.metrics import metrics
from app.core.rate_limit import RateLimiter
from app.models.requests import AskRequest
from app.use_cases.answer_question import AskInsuranceQuestion

router = APIRouter()
logger = logging.getLogger("rag")

# Chaves aceitas no filtro de metadados (evita pós-filtro inútil com chaves arbitrárias)
_ALLOWED_FILTER_KEYS = {"seguradora", "ramo"}
_MAX_FILTER_VALUE_LEN = 100


def _validate_filter(filter_dict: Optional[Dict[str, str]]) -> None:
    """Valida as chaves e o tamanho dos valores do filtro recebido da UI."""
    if not filter_dict:
        return
    unknown = set(filter_dict) - _ALLOWED_FILTER_KEYS
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Chaves de filtro inválidas: {', '.join(sorted(unknown))}. "
            f"Valores aceitos: {', '.join(sorted(_ALLOWED_FILTER_KEYS))}",
        )
    for key, value in filter_dict.items():
        if len(value) > _MAX_FILTER_VALUE_LEN:
            raise HTTPException(
                status_code=400,
                detail=f"Valor do filtro '{key}' muito longo (máx. {_MAX_FILTER_VALUE_LEN} caracteres).",
            )


def _client_ip(request: Request) -> str:
    """IP do cliente para rate limiting.

    Só confia em ``X-Forwarded-For`` quando o serviço está atrás de um proxy
    confiável (Render/nginx) — caso contrário o header é forjável e contorna
    o rate limit.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/ask")
def ask_question(
    request: Request,
    data: AskRequest,
    use_case: AskInsuranceQuestion = Depends(get_ask_use_case),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
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

    _validate_filter(data.filter)

    if not rate_limiter.allow(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Muitas requisições em curto período. Aguarde um instante e tente novamente.",
        )

    seguradora = data.filter.get("seguradora") if data.filter else None
    logger.info(
        "Filtro recebido via UI",
        extra={"event_data": {"filter": str(data.filter)[:200]}},
    )

    session_id = data.session_id or str(_uuid.uuid4())

    def sse_stream() -> Generator[str, None, None]:
        # Emit session_id como primeiro evento (mesmo se já fornecido pelo cliente)
        yield f"data: {_json.dumps({'type': 'session', 'data': session_id})}\n\n"

        # execute_stream is a plain sync method — safe to call from a sync generator.
        logger.info(
            "SSE stream iniciado",
            extra={
                "event_data": {
                    "session": session_id,
                    "pergunta": data.question[:60],
                    "top_k": data.top_k,
                    "filter": str(data.filter)[:200],
                }
            },
        )
        t0 = _time.perf_counter()
        try:
            reranked, text_stream = use_case.execute_stream(
                question=data.question,
                top_k=data.top_k,
                filter_dict=data.filter,
                seguradora=seguradora,
                document_type=data.document_type,
                session_id=session_id,
            )
            retrieval_ms = (_time.perf_counter() - t0) * 1000

            if not reranked:
                logger.info(
                    "Query sem contexto",
                    extra={
                        "event_data": {
                            "event": "query_no_context",
                            "top_k": data.top_k,
                            "filter": str(data.filter)[:200],
                            "document_type": data.document_type,
                        }
                    },
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
                # Não vaza detalhes internos para o cliente
                yield f"data: {_json.dumps({'type': 'error', 'data': 'Erro ao gerar a resposta. Tente novamente.'})}\n\n"
                return

            total_ms = (_time.perf_counter() - t0) * 1000
            llm_ms = max(total_ms - retrieval_ms, 0.0)
            metrics.record(retrieval_ms, llm_ms)
            logger.info(
                "Query concluída",
                extra={
                    "event_data": {
                        "event": "query",
                        "total_ms": round(total_ms, 1),
                        "retrieval_ms": round(retrieval_ms, 1),
                        "llm_ms": round(llm_ms, 1),
                        "top_k": data.top_k,
                        "chunks_returned": len(reranked),
                        "filter": str(data.filter)[:200],
                        "document_type": data.document_type,
                    }
                },
            )

        except Exception as exc:
            logger.error("Erro no SSE stream: %s", exc, exc_info=True)
            yield f"data: {_json.dumps({'type': 'error', 'data': 'Erro ao processar a pergunta. Tente novamente.'})}\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
