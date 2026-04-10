import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import MAX_FILE_SIZE, TEMP_DIR, settings
from app.core.dependencies import get_ingest_use_case
from app.domain.entities.document import InsuranceMetadata
from app.domain.entities.insurance import Seguradora
from app.use_cases.ingest_document import IngestDocument

router = APIRouter()
logger = logging.getLogger("rag")

_ALLOWED_ADMIN_SEGURADORAS = {s.value for s in Seguradora if s is not Seguradora.DESCONHECIDA}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_ingest(
    ingest: IngestDocument,
    contents: bytes,
    original_filename: str,
    metadata: InsuranceMetadata,
) -> int:
    """Salva temp, indexa e limpa.  Retorna chunks resultantes."""
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Limite máximo: {MAX_FILE_SIZE // 1024 // 1024}MB",
        )
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
    file: UploadFile = File(...),
    seguradora: Optional[str] = Form(None),
    ano: Optional[int] = Form(None),
    tipo: Optional[str] = Form(None),
    ingest: IngestDocument = Depends(get_ingest_use_case),
):
    """Upload aberto de PDFs com metadados opcionais."""
    if not settings.upload_enabled:
        raise HTTPException(status_code=403, detail="Upload desabilitado neste ambiente")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    metadata = InsuranceMetadata(
        seguradora=seguradora or "Desconhecida",
        ano=ano or 0,
        tipo=tipo or "Geral",
    )

    try:
        contents = await file.read()
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF: {exc}")


@router.post("/admin/upload")
async def admin_upload_pdf(
    file: UploadFile = File(...),
    seguradora: str = Form(...),
    ano: int = Form(...),
    tipo: Optional[str] = Form("Geral"),
    x_admin_key: str = Header(...),
    ingest: IngestDocument = Depends(get_ingest_use_case),
):
    """Upload administrativo — valida seguradora via enum e requer X-Admin-Key."""
    if not settings.upload_enabled:
        raise HTTPException(status_code=403, detail="Upload desabilitado neste ambiente")

    if not settings.admin_api_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Chave de administrador inválida ou ausente")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    if seguradora not in _ALLOWED_ADMIN_SEGURADORAS:
        raise HTTPException(
            status_code=400,
            detail=f"Seguradora não permitida. Escolha entre: {', '.join(sorted(_ALLOWED_ADMIN_SEGURADORAS))}",
        )

    metadata = InsuranceMetadata(seguradora=seguradora, ano=ano, tipo=tipo or "Geral")

    try:
        contents = await file.read()
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF administrativo: {exc}")
