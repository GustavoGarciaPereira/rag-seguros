import logging
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form, Header, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.core.config import settings, ALLOWED_SEGURADORAS
from app.core.dependencies import get_document_service
from app.services.document_service import DocumentService

router = APIRouter()
logger = logging.getLogger("rag")


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    seguradora: Optional[str] = Form(None),
    ano: Optional[int] = Form(None),
    tipo: Optional[str] = Form(None),
    doc_service: DocumentService = Depends(get_document_service),
):
    """Endpoint para upload de PDFs com metadados"""
    if not settings.upload_enabled:
        raise HTTPException(status_code=403, detail="Upload desabilitado neste ambiente")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    metadata = {}
    if seguradora:
        metadata["seguradora"] = seguradora
    if ano:
        metadata["ano"] = ano
    if tipo:
        metadata["tipo"] = tipo

    try:
        contents = await file.read()
        chunks_added = doc_service.process_upload(contents, metadata)
        return JSONResponse({
            "success": True,
            "message": f"Documento '{file.filename}' processado com sucesso!",
            "chunks_added": chunks_added,
            "filename": file.filename,
            "metadata": metadata
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF: {str(e)}")


@router.post("/admin/upload")
async def admin_upload_pdf(
    file: UploadFile = File(...),
    seguradora: str = Form(...),
    ano: int = Form(...),
    tipo: Optional[str] = Form("Geral"),
    x_admin_key: str = Header(...),
    doc_service: DocumentService = Depends(get_document_service),
):
    """
    Endpoint administrativo para upload de documentos com curadoria.
    Requer o header X-Admin-Key com o valor de ADMIN_API_KEY do .env
    """
    if not settings.upload_enabled:
        raise HTTPException(status_code=403, detail="Upload desabilitado neste ambiente")

    if not settings.admin_api_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Chave de administrador inválida ou ausente")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    if seguradora not in ALLOWED_SEGURADORAS:
        raise HTTPException(
            status_code=400,
            detail=f"Seguradora não permitida. Escolha entre: {', '.join(ALLOWED_SEGURADORAS)}"
        )

    metadata = {"seguradora": seguradora, "ano": ano, "tipo": tipo}

    try:
        contents = await file.read()
        chunks_added = doc_service.process_upload(contents, metadata)
        return JSONResponse({
            "success": True,
            "message": f"Documento da {seguradora} processado com sucesso!",
            "chunks_added": chunks_added,
            "filename": file.filename,
            "metadata": metadata
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF administrativo: {str(e)}")
