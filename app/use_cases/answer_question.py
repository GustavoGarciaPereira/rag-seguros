"""Use Case: AskInsuranceQuestion.

Orquestra o pipeline de RAG:
    Busca vetorial → Reranking → Geração LLM.

As três etapas são injetadas como interfaces — o use case não conhece
FAISS, DeepSeek nem nenhuma implementação concreta.
"""
import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

from app.domain.entities.document import SearchResult
from app.domain.interfaces.chat_history import ChatHistory
from app.domain.interfaces.llm_gateway import LLMGateway
from app.domain.interfaces.reranker import Reranker
from app.domain.interfaces.vector_repository import VectorRepository

logger = logging.getLogger("rag")


def _build_history_prefix(
    chat_history: ChatHistory,
    session_id: str,
    limit: int = 10,
) -> str:
    """Monta um prefixo com as últimas *limit* mensagens da sessão.

    Retorna string vazia se não houver histórico.
    """
    messages = chat_history.get_recent_messages(session_id, limit=limit)
    if not messages:
        return ""

    lines: List[str] = ["[Histórico recente da conversa]"]
    for role, content in messages:
        label = "Usuário" if role == "user" else "Assistente"
        lines.append(f"{label}: {content}")
    lines.append("")
    lines.append("[Pergunta atual]")
    return "\n".join(lines) + "\n"


class AskInsuranceQuestion:
    """Pipeline RAG completo: recuperação → reranking → geração."""

    def __init__(
        self,
        vector_repo: VectorRepository,
        reranker: Reranker,
        llm: LLMGateway,
        chat_history: Optional[ChatHistory] = None,
    ) -> None:
        self._vector_repo = vector_repo
        self._reranker = reranker
        self._llm = llm
        self._chat_history = chat_history

    # ------------------------------------------------------------------
    # Prompt helper
    # ------------------------------------------------------------------

    def _prompt_with_history(
        self, session_id: Optional[str], question: str
    ) -> str:
        """Prepend recent conversation history to the question if available."""
        if not session_id or not self._chat_history:
            return question
        prefix = _build_history_prefix(self._chat_history, session_id)
        if not prefix:
            return question
        return prefix + question

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        question: str,
        top_k: int = 15,
        filter_dict: Optional[Dict[str, Any]] = None,
        seguradora: Optional[str] = None,
        document_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[str], List[SearchResult]]:
        """Executa o pipeline RAG.

        Args:
            question:      Pergunta do usuário.
            top_k:         Número de chunks a recuperar (1–20).
            filter_dict:   Filtro de metadados, ex: ``{"seguradora": "Bradesco"}``.
            seguradora:    Seguradora filtrada, repassada ao LLM para contextualizar.
            document_type: Tipo de documento filtrado, repassado ao LLM.
            session_id:    Identificador da sessão para histórico de conversa.

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

        # Etapa 3: geração LLM (com histórico se disponível)
        prompt = self._prompt_with_history(session_id, question)
        answer = self._llm.generate(
            prompt,
            reranked,
            seguradora=seguradora,
            document_type=document_type,
        )

        # Etapa 4: salvar no histórico
        if session_id and self._chat_history and answer:
            self._chat_history.add_message(session_id, "user", question)
            self._chat_history.add_message(session_id, "assistant", answer)

        return answer, reranked

    def execute_stream(
        self,
        question: str,
        top_k: int = 15,
        filter_dict: Optional[Dict[str, Any]] = None,
        seguradora: Optional[str] = None,
        document_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[List[SearchResult], Iterator[str]]:
        """Executa busca + reranking e devolve os chunks e um gerador de texto.

        O gerador salva o par pergunta/resposta no histórico automaticamente
        após o último token ser consumido.

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

        prompt = self._prompt_with_history(session_id, question)
        text_stream = self._llm.generate_stream(
            prompt,
            reranked,
            seguradora=seguradora,
            document_type=document_type,
        )

        # Wraps the stream so the Q&A pair is persisted after the last token.
        if session_id and self._chat_history:
            return reranked, self._save_on_stream_end(
                session_id, question, text_stream
            )

        return reranked, text_stream

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save_on_stream_end(
        self,
        session_id: str,
        question: str,
        text_stream: Iterator[str],
    ) -> Iterator[str]:
        """Yield chunks and persist the Q&A pair after the stream finishes."""
        full_chunks: List[str] = []
        try:
            for chunk in text_stream:
                full_chunks.append(chunk)
                yield chunk
        finally:
            full_answer = "".join(full_chunks)
            if full_answer.strip():
                self._chat_history.add_message(session_id, "user", question)  # type: ignore[union-attr]
                self._chat_history.add_message(session_id, "assistant", full_answer)  # type: ignore[union-attr]
