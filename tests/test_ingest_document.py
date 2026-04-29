
"""Testes unitários para IngestDocument (use case de ingestao).

Usa mocks para DocumentParser, TextChunker, VectorRepository e DocumentCatalog.
"""
from unittest.mock import MagicMock

import pytest

from app.domain.entities.document import Chunk, DocumentRecord, InsuranceMetadata
from app.use_cases.ingest_document import IngestDocument


# ------------------------------------------------------------------
# Fixtures / helpers
# ------------------------------------------------------------------

@pytest.fixture
def meta():
    return InsuranceMetadata(seguradora="Bradesco", ano=2025, tipo="Geral", ramo="Automovel")


@pytest.fixture
def mock_parser():
    p = MagicMock()
    # Retorna 2 paginas parseadas
    from app.domain.entities.document import ParsedPage
    p.parse.return_value = [
        ParsedPage(page_number=1, text="Pagina 1: coberturas incluem..."),
        ParsedPage(page_number=2, text="Pagina 2: exclusoes da apolice..."),
    ]
    return p


@pytest.fixture
def mock_chunker():
    c = MagicMock()
    # chunk() retorna [(text, start_pos), ...]
    c.chunk.return_value = [
        ("Chunk 1: cobertura de vidros e para-brisas.", 0),
        ("Chunk 2: franquia obrigatoria.", 60),
    ]
    return c


@pytest.fixture
def mock_vector_repo():
    repo = MagicMock()
    repo.delete.return_value = 0
    return repo


@pytest.fixture
def mock_catalog():
    cat = MagicMock()
    cat.find_by_hash.return_value = None  # documento novo
    return cat


# ------------------------------------------------------------------
# Testes
# ------------------------------------------------------------------

def test_new_document_full_pipeline(meta, mock_parser, mock_chunker, mock_vector_repo, mock_catalog):
    """Documento novo: parse -> chunk -> add -> register, retorna chunk_count."""
    uc = IngestDocument(mock_parser, mock_chunker, mock_vector_repo, mock_catalog)

    # Simula hash de arquivo (patch do metodo estatico)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(IngestDocument, "_hash_file", staticmethod(lambda _: "abc123"))
        mp.setattr(IngestDocument, "_make_doc_id", staticmethod(lambda fp, h: f"doc_{h[:6]}"))
        count = uc.execute("fake.pdf", meta, source_name="teste.pdf")

    assert count == 4  # 4 chunks (2 paginas x 2 chunks cada)
    mock_parser.parse.assert_called_once_with("fake.pdf")
    mock_chunker.chunk.assert_called()
    mock_vector_repo.add.assert_called_once()
    mock_catalog.register.assert_called_once()


def test_duplicate_document_skip(meta, mock_parser, mock_chunker, mock_vector_repo, mock_catalog):
    """Hash ja existe + metadados identicos: skip total."""
    existing = DocumentRecord(
        doc_id="doc_abc123",
        source_name="teste.pdf",
        file_hash="abc123",
        seguradora="Bradesco",
        ano=2025,
        tipo="Geral",
        ramo="Automovel",
        chunk_count=2,
        created_at="2025-01-01T00:00:00",
    )
    mock_catalog.find_by_hash.return_value = existing
    uc = IngestDocument(mock_parser, mock_chunker, mock_vector_repo, mock_catalog)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(IngestDocument, "_hash_file", staticmethod(lambda _: "abc123"))
        count = uc.execute("fake.pdf", meta, source_name="teste.pdf")

    assert count == existing.chunk_count
    mock_parser.parse.assert_not_called()
    mock_vector_repo.add.assert_not_called()


def test_metadata_update_no_reindex(meta, mock_parser, mock_chunker, mock_vector_repo, mock_catalog):
    """Hash igual mas metadados diferentes: update sem re-embedding."""
    existing = DocumentRecord(
        doc_id="doc_abc123",
        source_name="teste.pdf",
        file_hash="abc123",
        seguradora="Allianz",  # diferente
        ano=2024,              # diferente
        tipo="Geral",
        ramo="Automovel",
        chunk_count=3,
        created_at="2025-01-01T00:00:00",
    )
    mock_catalog.find_by_hash.return_value = existing
    uc = IngestDocument(mock_parser, mock_chunker, mock_vector_repo, mock_catalog)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(IngestDocument, "_hash_file", staticmethod(lambda _: "abc123"))
        count = uc.execute("fake.pdf", meta, source_name="teste.pdf")

    assert count == existing.chunk_count
    mock_catalog.update_metadata.assert_called_once()
    mock_vector_repo.update_metadata.assert_called_once()
    mock_vector_repo.add.assert_not_called()


def test_hash_file_uses_sha256(tmp_path):
    """_hash_file() retorna SHA-256 hexadecimal do conteudo do arquivo."""
    path = tmp_path / "test.txt"
    path.write_text("conteudo de teste")
    digest = IngestDocument._hash_file(str(path))
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
