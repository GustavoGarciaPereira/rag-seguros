from pydantic import BaseModel
from typing import Optional, List, Any, Dict


class ContextItem(BaseModel):
    text: str
    source: str
    page: int
    seguradora: Optional[str]
    relevance_score: float


class AskResponse(BaseModel):
    success: bool
    answer: str
    context_used: List[Dict[str, Any]]
    has_context: bool
    context_count: Optional[int] = None


class UploadResponse(BaseModel):
    success: bool
    message: str
    chunks_added: int
    filename: str
    metadata: Dict[str, Any]
