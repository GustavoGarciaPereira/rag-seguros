import hmac
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import ALLOWED_SEGURADORAS, MAX_FILE_SIZE, TEMP_DIR, settings
from app.core.dependencies import get_ingest_use_case
from app.domain.entities.document import InsuranceMetadata
from app.domain.entities.insurance import Ramo
from app.use_cases.ingest_document import IngestDocument

router = APIRouter()
logger = logging.getLogger("rag")

_ALLOWED_RAMOS = {r.value for r in Ramo if r is not Ramo.DESCONHECIDO}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_pdf_bytes(contents: bytes) -> None:
    """Valida tamanho e assinatura PDF (magic bytes) antes de qualquer ingestão."""
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Limite máximo: {MAX_FILE_SIZE // 1024 // 1024}MB",
        )
    if not contents.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail="Arquivo inválido: o conteúdo não é um PDF (assinatura %PDF ausente).",
        )


def _reject_oversized_request(request: Request) -> None:
    """Rejeita por Content-Length antes de ler o corpo (evita DoS de leitura)."""
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Limite máximo: {MAX_FILE_SIZE // 1024 // 1024}MB",
        )


def _run_ingest(
    ingest: IngestDocument,
    contents: bytes,
    original_filename: str,
    metadata: InsuranceMetadata,
) -> int:
    """Valida, salva temp, indexa e limpa.  Retorna chunks resultantes."""
    _validate_pdf_bytes(contents)
    os.makedirs(TEMP_DIR, exist_ok=True)
    temp_path = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}.pdf")
    try:
        with open(temp_path, "wb") as f:
            f.write(contents)
        return ingest.execute(temp_path, metadata, source_name=original_filename)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    seguradora: Optional[str] = Form(None),
    ano: Optional[int] = Form(None),
    tipo: Optional[str] = Form(None),
    ramo: Optional[str] = Form(None),
    ingest: IngestDocument = Depends(get_ingest_use_case),
):
    """Upload aberto de PDFs com metadados opcionais."""
    if not settings.upload_enabled:
        raise HTTPException(status_code=403, detail="Upload desabilitado neste ambiente")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    _reject_oversized_request(request)

    metadata = InsuranceMetadata(
        seguradora=seguradora or "Desconhecida",
        ano=ano or 0,
        tipo=tipo or "Geral",
        ramo=ramo or "Desconhecido",
    )

    try:
        # Lê no máximo MAX_FILE_SIZE+1 bytes — nunca materializa corpo gigante em RAM
        contents = await file.read(MAX_FILE_SIZE + 1)
        chunks = _run_ingest(ingest, contents, file.filename, metadata)
        return JSONResponse(
            {
                "success": True,
                "message": f"Documento '{file.filename}' processado com sucesso!",
                "chunks_added": chunks,
                "filename": file.filename,
                "metadata": metadata.model_dump(),
            }
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao processar upload público", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro ao processar o PDF. Verifique se o arquivo é um PDF válido e tente novamente.",
        )


@router.post("/admin/upload")
async def admin_upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    seguradora: str = Form(...),
    ano: int = Form(...),
    tipo: Optional[str] = Form("Geral"),
    ramo: Optional[str] = Form(None),
    x_admin_key: str = Header(...),
    ingest: IngestDocument = Depends(get_ingest_use_case),
):
    """Upload administrativo — valida seguradora via enum e requer X-Admin-Key."""
    if not settings.upload_enabled:
        raise HTTPException(status_code=403, detail="Upload desabilitado neste ambiente")

    if not settings.admin_api_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Chave de administrador inválida ou ausente")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    _reject_oversized_request(request)

    if seguradora not in ALLOWED_SEGURADORAS:
        raise HTTPException(
            status_code=400,
            detail=f"Seguradora não permitida. Escolha entre: {', '.join(sorted(ALLOWED_SEGURADORAS))}",
        )

    ramo_value = ramo or "Desconhecido"
    if ramo and ramo not in _ALLOWED_RAMOS:
        raise HTTPException(
            status_code=400,
            detail=f"Ramo não permitido. Escolha entre: {', '.join(sorted(_ALLOWED_RAMOS))}",
        )

    metadata = InsuranceMetadata(seguradora=seguradora, ano=ano, tipo=tipo or "Geral", ramo=ramo_value)

    try:
        contents = await file.read(MAX_FILE_SIZE + 1)
        chunks = _run_ingest(ingest, contents, file.filename, metadata)
        return JSONResponse(
            {
                "success": True,
                "message": f"Documento da {seguradora} processado com sucesso!",
                "chunks_added": chunks,
                "filename": file.filename,
                "metadata": metadata.model_dump(),
            }
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao processar upload administrativo", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro ao processar o PDF. Verifique se o arquivo é um PDF válido e tente novamente.",
        )
