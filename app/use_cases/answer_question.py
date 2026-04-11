"""Use Case: AskInsuranceQuestion.

Orquestra o pipeline de RAG:
    Busca vetorial → Reranking → Geração LLM.

As três etapas são injetadas como interfaces — o use case não conhece
FAISS, DeepSeek nem nenhuma implementação concreta.
"""
import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

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
        # Etapa 1: recuperação vetorial com oversampling (fetch_k = top_k * 4)
        fetch_k = top_k * 4
        raw_results = self._vector_repo.search(
            question, n_results=fetch_k, filter_dict=filter_dict
        )

        logger.debug(
            "Retrieval: %d chunks retornados pelo FAISS.",
            len(raw_results),
        )

        if not raw_results:
            return None, []

        # Etapa 2: reranking por sobreposição de termos + slice final
        reranked = self._reranker.rerank(question, raw_results)[:top_k]

        logger.debug(
            "Reranking: %d avaliados, top %d retidos para o LLM.",
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

    def execute_stream(
        self,
        question: str,
        top_k: int = 15,
        filter_dict: Optional[Dict[str, Any]] = None,
        seguradora: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> Tuple[List[SearchResult], Iterator[str]]:
        """Executa busca + reranking e devolve os chunks e um gerador de texto.

        Returns:
            ``(reranked_results, text_stream)`` — text_stream é um gerador que
            cede deltas de texto conforme a API responde. Se não houver contexto,
            retorna ``([], iter([]))``.
        """
        fetch_k = top_k * 4
        raw_results = self._vector_repo.search(
            question, n_results=fetch_k, filter_dict=filter_dict
        )

        logger.debug(
            "Retrieval: %d chunks retornados pelo FAISS.",
            len(raw_results),
        )

        if not raw_results:
            return [], iter([])

        reranked = self._reranker.rerank(question, raw_results)[:top_k]

        logger.debug(
            "Reranking: %d avaliados, top %d retidos para o LLM.",
            len(raw_results),
            len(reranked),
        )

        text_stream = self._llm.generate_stream(
            question,
            reranked,
            seguradora=seguradora,
            document_type=document_type,
        )
        return reranked, text_stream
