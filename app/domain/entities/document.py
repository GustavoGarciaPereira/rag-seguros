from __future__ import annotations

from pydantic import BaseModel, field_validator


class InsuranceMetadata(BaseModel):
    """Value Object: metadados de um documento de seguro.

    Validação de domínio aplicada antes de chegar na infra.
    A restrição de allowlist de seguradoras fica na rota admin/upload (preocupação
    de entrega), não aqui — pois uploads abertos aceitam 'Desconhecida'.
    """

    seguradora: str = "Desconhecida"
    ano: int = 0
    tipo: str = "Geral"

    @field_validator("tipo", mode="before")
    @classmethod
    def _normalise_tipo(cls, v: object) -> str:
        if not v:
            return "Geral"
        return str(v).strip().title()

    @field_validator("seguradora", mode="before")
    @classmethod
    def _normalise_seguradora(cls, v: object) -> str:
        return str(v).strip() if v else "Desconhecida"


class ParsedPage(BaseModel):
    """Página extraída de um documento."""

    page_number: int
    text: str


class Chunk(BaseModel):
    """Fragmento de texto pronto para indexação vetorial."""

    text: str
    source: str
    document_id: str
    page: int = 0
    chunk_index: int = 0
    metadata: InsuranceMetadata = InsuranceMetadata()


class SearchResult(BaseModel):
    """Resultado de uma busca vetorial com score de relevância."""

    text: str
    source: str
    page: int = 0
    seguradora: str = "Desconhecida"
    ano: int = 0
    tipo: str = "Geral"
    relevance_score: float = 0.0

    def to_context_dict(self) -> dict:
        """Retorna dict compatível com o formato de contexto legado."""
        return self.model_dump()


class DocumentRecord(BaseModel):
    """Registro de inventário de um documento indexado no catálogo.

    Um DocumentRecord representa um arquivo PDF completo, enquanto
    Chunk representa um fragmento individual desse arquivo.
    """

    doc_id: str
    source_name: str
    file_hash: str  # SHA-256 do conteúdo binário
    seguradora: str = "Desconhecida"
    ano: int = 0
    tipo: str = "Geral"
    chunk_count: int = 0
    created_at: str  # ISO 8601 UTC
