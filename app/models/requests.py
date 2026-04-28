from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict


class AskRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question: str = Field(..., min_length=5, max_length=500, description="Pergunta sobre os documentos")
    top_k: int = Field(default=15, ge=1, le=20, description="Número de trechos a recuperar")
    filter: Optional[Dict[str, str]] = Field(default=None, description="Filtro de metadados, ex: {'seguradora': 'Bradesco'}")
    document_type: Optional[str] = Field(default=None, description="Tipo de documento: apolice | sinistro | cobertura | franquia | endosso")
    session_id: Optional[str] = Field(
        default=None,
        alias="sessionId",
        description="ID da sessão de chat. Se omitido, uma nova sessão é criada."
    )
