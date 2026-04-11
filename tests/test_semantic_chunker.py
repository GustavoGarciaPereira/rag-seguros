"""Testes unitários para InsuranceSemanticChunker — injeção de título de seção."""
import pytest

from app.infrastructure.chunkers.semantic_chunker import (
    InsuranceSemanticChunker,
    _is_section_title,
    _apply_section_prefix,
)


# ---------------------------------------------------------------------------
# _is_section_title
# ---------------------------------------------------------------------------

class TestIsSectionTitle:
    def test_clausula_numerada(self):
        assert _is_section_title("CLÁUSULA 5 – COBERTURAS") is True

    def test_artigo(self):
        assert _is_section_title("Art. 12 – Vigência") is True
        assert _is_section_title("Artigo 3") is True

    def test_secao(self):
        assert _is_section_title("SEÇÃO II – EXCLUSÕES") is True

    def test_capitulo(self):
        assert _is_section_title("CAPÍTULO 1") is True

    def test_all_caps_multi_word(self):
        assert _is_section_title("DISPOSIÇÕES GERAIS") is True

    def test_all_caps_single_word_nao_e_titulo(self):
        # Uma única palavra maiúscula não deve ser título
        assert _is_section_title("TOTAL") is False

    def test_paragrafo_longo_nao_e_titulo(self):
        long_text = "Este é um parágrafo normal com texto suficientemente longo para não ser título de seção."
        assert _is_section_title(long_text) is False

    def test_linha_vazia(self):
        assert _is_section_title("") is False

    def test_numerado_com_capital(self):
        assert _is_section_title("3.2. Franquia") is True


# ---------------------------------------------------------------------------
# _apply_section_prefix
# ---------------------------------------------------------------------------

class TestApplySectionPrefix:
    def test_sem_secao_nao_altera(self):
        text = "Texto qualquer."
        assert _apply_section_prefix(text, None) == text
        assert _apply_section_prefix(text, "") == text

    def test_adiciona_prefixo(self):
        text = "| Cobertura | Limite |\n| Incêndio | 100% |"
        result = _apply_section_prefix(text, "CLÁUSULA 5")
        assert result.startswith("[SEÇÃO: CLÁUSULA 5]\n")
        assert "| Cobertura |" in result

    def test_nao_duplica_se_chunk_ja_abre_com_titulo(self):
        title = "CLÁUSULA 5 – COBERTURAS"
        text = f"{title}\n\nTexto da cláusula."
        result = _apply_section_prefix(text, title)
        assert result == text  # sem prefixo


# ---------------------------------------------------------------------------
# InsuranceSemanticChunker.chunk — integração
# ---------------------------------------------------------------------------

class TestInsuranceSemanticChunker:
    def setup_method(self):
        self.chunker = InsuranceSemanticChunker()

    def test_chunk_titulo_nao_recebe_prefixo_duplicado(self):
        """O chunk que contém o próprio título não recebe [SEÇÃO: ...]."""
        text = (
            "CLÁUSULA 1 – OBJETO DO SEGURO\n\n"
            "Este seguro cobre os riscos agrícolas descritos nesta apólice."
        )
        chunks = self.chunker.chunk(text, chunk_size=1200, overlap=0)
        assert chunks, "Deve gerar ao menos um chunk"
        first_text = chunks[0][0]
        # O chunk abre com o título → sem prefixo duplicado
        assert not first_text.startswith("[SEÇÃO:")

    def test_tabela_dentro_de_secao_recebe_prefixo(self):
        """Chunk de tabela separado do título deve receber o prefixo da seção."""
        # Gerar texto que force a tabela em chunk separado do título
        titulo = "CLÁUSULA 5 – COBERTURAS"
        paragrafo = "A " * 300  # ~600 chars — ocupa quase um chunk de 700
        tabela = "| Cobertura | Limite |\n| Incêndio  | 100%   |\n| Granizo   | 80%    |"

        text = f"{titulo}\n\n{paragrafo}\n\n{tabela}"
        chunks = self.chunker.chunk(text, chunk_size=700, overlap=50)

        # Encontra o chunk que contém a tabela
        tabela_chunks = [c for c, _ in chunks if "Incêndio" in c]
        assert tabela_chunks, "Tabela deve aparecer em algum chunk"

        for tc in tabela_chunks:
            if not tc.startswith(titulo):  # chunk separado do título
                assert tc.startswith("[SEÇÃO: CLÁUSULA 5"), (
                    f"Chunk de tabela fora do título deveria ter prefixo.\nChunk: {tc!r}"
                )

    def test_texto_sem_titulo_nao_recebe_prefixo(self):
        """Texto que não possui seção identificada não deve ser prefixado."""
        text = "Texto simples sem nenhuma marcação de seção ou cláusula."
        chunks = self.chunker.chunk(text, chunk_size=1200, overlap=0)
        for chunk_text, _ in chunks:
            assert not chunk_text.startswith("[SEÇÃO:")

    def test_chunk_apos_titulo_recebe_prefixo(self):
        """Chunk gerado após o título (em chunk separado) recebe o prefixo."""
        titulo = "ARTIGO 10 – FRANQUIA"
        # Forçar o título num chunk e o conteúdo num chunk separado
        conteudo = "X " * 400  # ~800 chars

        text = f"{titulo}\n\n{conteudo}"
        chunks = self.chunker.chunk(text, chunk_size=500, overlap=0)

        conteudo_chunks = [c for c, _ in chunks if "X X X" in c and titulo not in c]
        for cc in conteudo_chunks:
            assert cc.startswith("[SEÇÃO: ARTIGO 10"), (
                f"Chunk de conteúdo após o título deveria ter prefixo.\nChunk: {cc!r}"
            )
