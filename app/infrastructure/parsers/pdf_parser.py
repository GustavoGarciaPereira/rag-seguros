"""Parser de PDF usando pypdf."""
from typing import List

from pypdf import PdfReader

from app.domain.entities.document import ParsedPage
from app.domain.interfaces.document_parser import DocumentParser


class PdfDocumentParser(DocumentParser):
    """Extrai texto de PDFs página a página usando pypdf.

    Páginas sem texto extraível (ex.: imagens escaneadas sem OCR) são omitidas.
    """

    def parse(self, file_path: str) -> List[ParsedPage]:
        reader = PdfReader(file_path)
        pages: List[ParsedPage] = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append(ParsedPage(page_number=i + 1, text=text))
        return pages
