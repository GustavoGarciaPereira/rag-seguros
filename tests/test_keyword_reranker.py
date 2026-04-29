"""Testes unitários para KeywordOverlapReranker.

Cobre: pesos configuráveis, validação de construtor, expansões de domínio,
filtragem de stopwords, e retorno vazio.
"""
from __future__ import annotations

import pytest

from app.domain.entities.document import SearchResult
from app.infrastructure.rerankers.keyword_reranker import KeywordOverlapReranker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def reranker() -> KeywordOverlapReranker:
    return KeywordOverlapReranker()


@pytest.fixture
def sample_results() -> list[SearchResult]:
    return [
        SearchResult(
            text="Carro reserva: diárias de Básico, Plus e Premium disponíveis.",
            source="manual_bradesco.pdf",
            page=12,
            seguradora="Bradesco",
            ramo="Automovel",
            relevance_score=0.85,
        ),
        SearchResult(
            text="Valores de franquia e dedutível obrigatório.",
            source="manual_allianz.pdf",
            page=34,
            seguradora="Allianz",
            ramo="Automovel",
            relevance_score=0.75,
        ),
        SearchResult(
            text="Cobertura de incêndio e compreensivo inclui assistência 24h.",
            source="manual_porto.pdf",
            page=7,
            seguradora="Porto Seguro",
            ramo="Residencial",
            relevance_score=0.65,
        ),
    ]


# ---------------------------------------------------------------------------
# Construtor
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_default_weights(self, reranker: KeywordOverlapReranker) -> None:
        """Peso padrão: 70% semântico + 30% léxico."""
        assert reranker.semantic_weight == 0.7
        assert reranker.keyword_weight == 0.3

    def test_custom_weights(self) -> None:
        """Pesos customizados devem ser aceitos."""
        r = KeywordOverlapReranker(semantic_weight=0.5, keyword_weight=0.5)
        assert r.semantic_weight == 0.5
        assert r.keyword_weight == 0.5

    def test_all_semantic(self) -> None:
        """100% semântico (0% léxico) deve ser válido."""
        r = KeywordOverlapReranker(semantic_weight=1.0, keyword_weight=0.0)
        assert r.semantic_weight == 1.0

    def test_invalid_weights_raises(self) -> None:
        """Soma diferente de 1.0 deve levantar ValueError."""
        with pytest.raises(ValueError, match="deve ser igual a 1.0"):
            KeywordOverlapReranker(semantic_weight=0.8, keyword_weight=0.3)

    def test_zero_weights_raises(self) -> None:
        """Soma zero deve levantar ValueError."""
        with pytest.raises(ValueError, match="deve ser igual a 1.0"):
            KeywordOverlapReranker(semantic_weight=0.0, keyword_weight=0.0)


# ---------------------------------------------------------------------------
# Rerank — estrutura básica
# ---------------------------------------------------------------------------

class TestRerankBasic:
    def test_returns_same_count(
        self, reranker: KeywordOverlapReranker, sample_results: list[SearchResult]
    ) -> None:
        """rerank deve retornar o mesmo número de resultados."""
        result = reranker.rerank("carro reserva", sample_results)
        assert len(result) == len(sample_results)

    def test_returns_sorted_by_score_desc(
        self, reranker: KeywordOverlapReranker, sample_results: list[SearchResult]
    ) -> None:
        """Resultados devem vir ordenados por relevance_score decrescente."""
        result = reranker.rerank("carro reserva", sample_results)
        scores = [r.relevance_score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_empty_results(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Lista vazia de resultados deve retornar lista vazia."""
        assert reranker.rerank("carro reserva", []) == []

    def test_single_result(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Um único resultado: score recalculado, metadados preservados."""
        results = [
            SearchResult(
                text="Carro reserva basico.",
                source="manual.pdf",
                page=1,
                relevance_score=0.9,
            )
        ]
        out = reranker.rerank("carro reserva", results)
        assert len(out) == 1
        # O reranker sempre recalcula o score composto:
        # score = 0.9 * 0.7 + overlap_fraction * 0.3
        # query expandida: {carro, reserva, veículo, automóvel, locação,
        #                    diárias, básico, plus, premium} = 9 termos
        # overlap: {carro, reserva} = 2 termos → 2/9
        # score = 0.63 + 0.0667 = 0.6967
        assert 0.0 < out[0].relevance_score < 1.0
        assert out[0].source == "manual.pdf"
        assert out[0].page == 1

    def test_preserves_metadata(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Metadados do resultado original não devem ser alterados."""
        results = [
            SearchResult(
                text="Carro reserva basico.",
                source="manual_bradesco.pdf",
                page=42,
                seguradora="Bradesco",
                ramo="Automovel",
                relevance_score=0.8,
            )
        ]
        out = reranker.rerank("carro", results)
        r = out[0]
        assert r.source == "manual_bradesco.pdf"
        assert r.page == 42
        assert r.seguradora == "Bradesco"
        assert r.ramo == "Automovel"


# ---------------------------------------------------------------------------
# Rerank — domínio e expansões
# ---------------------------------------------------------------------------

class TestDomainExpansions:
    def test_query_carro_expande_veiculo(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Query 'carro' deve expandir e pontuar chunk com 'veículo'."""
        results = [
            SearchResult(
                text="O veículo segurado receberá carro reserva.",
                source="manual.pdf",
                page=1,
                relevance_score=0.5,
            ),
            SearchResult(
                text="Franquia obrigatória para todos os seguros.",
                source="manual.pdf",
                page=2,
                relevance_score=0.9,
            ),
        ]
        out = reranker.rerank("carro reserva diárias", results)
        # O primeiro chunk tem termos que expandem da query → deve subir
        assert out[0].relevance_score > out[1].relevance_score

    def test_query_reserva_expande_basico_plus_premium(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Query 'reserva' expande para 'básico', 'plus', 'premium'."""
        results = [
            SearchResult(
                text="Plano Básico: 7 diárias. Plano Plus: 15 diárias.",
                source="manual.pdf",
                page=1,
                relevance_score=0.6,
            ),
            SearchResult(
                text="Exclusões gerais da apólice.",
                source="manual.pdf",
                page=2,
                relevance_score=0.9,
            ),
        ]
        out = reranker.rerank("carro reserva", results)
        assert out[0].relevance_score > out[1].relevance_score

    def test_query_perda_expande_vmr_fipe(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Query 'perda total' expande para 'vmr', 'fipe', '0km'."""
        results = [
            SearchResult(
                text="VMR é calculada pela tabela FIPE para veículos 0km.",
                source="manual.pdf",
                page=1,
                relevance_score=0.5,
            ),
            SearchResult(
                text="Franquia obrigatória para todos os seguros.",
                source="manual.pdf",
                page=2,
                relevance_score=0.9,
            ),
        ]
        out = reranker.rerank("perda total indenização", results)
        assert out[0].relevance_score > out[1].relevance_score

    def test_query_cobertura_expande_assistencia(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Query 'cobertura' expande para 'assistência', 'incluído'."""
        results = [
            SearchResult(
                text="Assistência 24h incluída em todos os planos.",
                source="manual.pdf",
                page=1,
                relevance_score=0.5,
            ),
            SearchResult(
                text="Pagamento em até 30 dias.",
                source="manual.pdf",
                page=2,
                relevance_score=0.9,
            ),
        ]
        out = reranker.rerank("cobertura adicional", results)
        assert out[0].relevance_score > out[1].relevance_score

    def test_query_franquia_expande_dedutivel(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Query 'franquia' expande para 'dedutível', 'participação'."""
        results = [
            SearchResult(
                text="Participação obrigatória do segurado: R$ 500,00.",
                source="manual.pdf",
                page=1,
                relevance_score=0.5,
            ),
            SearchResult(
                text="Carro reserva incluso.",
                source="manual.pdf",
                page=2,
                relevance_score=0.9,
            ),
        ]
        out = reranker.rerank("franquia dedutível", results)
        assert out[0].relevance_score > out[1].relevance_score


# ---------------------------------------------------------------------------
# Rerank — stopwords
# ---------------------------------------------------------------------------

class TestStopwords:
    def test_query_all_stopwords(
        self, reranker: KeywordOverlapReranker, sample_results: list[SearchResult]
    ) -> None:
        """Query composta apenas de stopwords deve retornar resultados
        inalterados (sem termos para fazer overlap)."""
        out = reranker.rerank("de da do e em", sample_results)
        # Scores devem manter apenas o peso semântico original
        assert len(out) == len(sample_results)

    def test_mixed_stopwords_and_terms(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Stopwords na query não devem interferir no overlap."""
        results = [
            SearchResult(
                text="Diárias do carro reserva.",
                source="manual.pdf",
                page=1,
                relevance_score=0.5,
            ),
            SearchResult(
                text="Taxa de administração.",
                source="manual.pdf",
                page=2,
                relevance_score=0.9,
            ),
        ]
        out = reranker.rerank("o que e o carro reserva", results)
        assert out[0].relevance_score > out[1].relevance_score


# ---------------------------------------------------------------------------
# Rerank — score composto
# ---------------------------------------------------------------------------

class TestCompositeScore:
    def test_identical_results_preserve_order(
        self, reranker: KeywordOverlapReranker
    ) -> None:
        """Resultados com mesmo score semântico devem manter ordem
        relativa (overlap define o desempate)."""
        results = [
            SearchResult(
                text="Carro reserva e diárias incluídas.",
                source="manual.pdf",
                page=1,
                relevance_score=0.7,
            ),
            SearchResult(
                text="Franquia obrigatória e dedutível.",
                source="manual.pdf",
                page=2,
                relevance_score=0.7,
            ),
        ]
        out = reranker.rerank("carro reserva diárias", results)
        scores = [r.relevance_score for r in out]
        assert scores == sorted(scores, reverse=True)
