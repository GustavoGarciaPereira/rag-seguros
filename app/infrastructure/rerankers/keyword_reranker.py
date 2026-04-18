"""Re-ranqueamento leve por sobreposição de termos-chave.

Combina o score semântico do FAISS (70%) com a sobreposição de termos da
query no texto do chunk (30%).  Melhora a recuperação de termos específicos
de seguros — valores em R$, nomes de coberturas — que costumam ter baixo
score semântico em embeddings genéricos.
"""
from __future__ import annotations

import re
from typing import List

from app.domain.entities.document import SearchResult
from app.domain.interfaces.reranker import Reranker

_STOPWORDS_PT: frozenset = frozenset({
    "de", "da", "do", "das", "dos", "e", "em", "o", "a", "os", "as",
    "que", "por", "com", "para", "se", "um", "uma", "no", "na", "nos",
    "nas", "ao", "aos", "é", "são", "foi", "ser", "ter", "mais", "mas",
    "ou", "também", "não", "sim", "já", "como", "quando", "seu", "sua",
})

_PUNCT = re.compile(r"[^\w\s]")

# Termos de domínio: quando a query contém a chave, os valores são adicionados
# ao conjunto de termos para fins de overlap (captura sinônimos e métricas).
_DOMAIN_EXPANSIONS: dict[str, list[str]] = {
    "perda":        ["indenização", "vmr", "fipe", "0km", "180", "365"],
    "indenização":  ["perda", "vmr", "fipe", "0km", "180", "365"],
    "total":        ["0km", "zero quilômetro", "180", "365", "vmr"],
    "carro":        ["veículo", "automóvel", "reserva", "locação"],
    "reserva":      ["carro", "locação", "diárias", "básico", "plus", "premium"],
    "franquia":     ["dedutível", "participação", "obrigatória"],
    "cobertura":    ["cláusula", "assistência", "incluído", "compreendido"],
}


class KeywordOverlapReranker(Reranker):
    """Reranker de sobreposição de termos com pesos configuráveis."""

    def __init__(
        self,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> None:
        if abs(semantic_weight + keyword_weight - 1.0) > 1e-6:
            raise ValueError("semantic_weight + keyword_weight deve ser igual a 1.0")
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight

    def rerank(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        query_terms = set(_PUNCT.sub("", query.lower()).split()) - _STOPWORDS_PT
        # Expansão de domínio: adiciona termos relacionados ao conjunto da query
        extra: set[str] = set()
        for term in query_terms:
            for expansion in _DOMAIN_EXPANSIONS.get(term, []):
                extra.update(_PUNCT.sub("", expansion.lower()).split())
        query_terms = query_terms | (extra - _STOPWORDS_PT)
        if not query_terms:
            return results

        reranked: List[SearchResult] = []
        for result in results:
            text_terms = set(_PUNCT.sub("", result.text.lower()).split())
            overlap = len(query_terms & text_terms) / len(query_terms)
            new_score = (
                self.semantic_weight * result.relevance_score
                + self.keyword_weight * overlap
            )
            reranked.append(result.model_copy(update={"relevance_score": new_score}))

        return sorted(reranked, key=lambda r: r.relevance_score, reverse=True)
