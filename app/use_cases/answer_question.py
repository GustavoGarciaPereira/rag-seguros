"""Use Case: AskInsuranceQuestion.

Orquestra o pipeline de RAG:
    Busca vetorial → Reranking → Geração LLM.

As três etapas são injetadas como interfaces — o use case não conhece
FAISS, DeepSeek nem nenhuma implementação concreta.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.domain.entities.document import SearchResult
from app.domain.interfaces.llm_gateway import LLMGateway
from app.domain.interfaces.reranker import Reranker
from app.domain.interfaces.vector_repository import VectorRepository

logger = logging.getLogger("rag")


class AskInsuranceQuestion:
    """Pipeline RAG completo: recuperação → reranking → geração."""

    def __init__(
        self,
        vector_repo: VectorRepository,
        reranker: Reranker,
        llm: LLMGateway,
    ) -> None:
        self._vector_repo = vector_repo
        self._reranker = reranker
        self._llm = llm

    def execute(
        self,
        question: str,
        top_k: int = 15,
        filter_dict: Optional[Dict[str, Any]] = None,
        seguradora: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> Tuple[Optional[str], List[SearchResult]]:
        """Executa o pipeline RAG.

        Args:
            question:      Pergunta do usuário.
            top_k:         Número de chunks a recuperar (1–20).
            filter_dict:   Filtro de metadados, ex: ``{"seguradora": "Bradesco"}``.
            seguradora:    Seguradora filtrada, repassada ao LLM para contextualizar.
            document_type: Tipo de documento filtrado, repassado ao LLM.

        Returns:
            ``(answer, reranked_results)`` — answer é None quando não há
            contexto suficiente para responder.
        """
        # Etapa 1: recuperação vetorial
        raw_results = self._vector_repo.search(
            question, n_results=top_k, filter_dict=filter_dict
        )

        logger.debug(
            "Retrieval: top_k=%d solicitado, %d chunks retornados pelo FAISS.",
            top_k,
            len(raw_results),
        )

        if not raw_results:
            return None, []

        # Etapa 2: reranking por sobreposição de termos
        reranked = self._reranker.rerank(question, raw_results)

        logger.debug(
            "Reranking: %d → %d chunks após reranking.",
            len(raw_results),
            len(reranked),
        )

        # Etapa 3: geração LLM
        answer = self._llm.generate(
            question,
            reranked,
            seguradora=seguradora,
            document_type=document_type,
        )
        return answer, reranked
