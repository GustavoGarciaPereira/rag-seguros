import os
import uuid
from typing import Dict, Any

from fastapi import HTTPException

from app.core.config import TEMP_DIR, MAX_FILE_SIZE
from app.services.vector_service import VectorStoreBase


class DocumentService:
    """Gerencia o fluxo de upload: salva temp, delega ao vector store, limpa."""

    def __init__(self, vector_service: VectorStoreBase) -> None:
        self.vector_service = vector_service
        os.makedirs(TEMP_DIR, exist_ok=True)

    def process_upload(self, contents: bytes, metadata: Dict[str, Any]) -> int:
        """Persiste o PDF em arquivo temporário, indexa e remove o arquivo.

        Returns:
            Número de chunks adicionados ao índice.
        """
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Arquivo muito grande. Limite máximo: {MAX_FILE_SIZE // 1024 // 1024}MB"
            )

        safe_name = f"{uuid.uuid4().hex}.pdf"
        temp_path = os.path.join(TEMP_DIR, safe_name)

        try:
            with open(temp_path, "wb") as f:
                f.write(contents)
            return self.vector_service.add_document(temp_path, metadata_input=metadata)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
