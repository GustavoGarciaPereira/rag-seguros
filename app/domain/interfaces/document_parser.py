from abc import ABC, abstractmethod
from typing import List

from app.domain.entities.document import ParsedPage


class DocumentParser(ABC):
    """Estratégia de extração de texto de um arquivo.

    A implementação concreta é responsável por converter formatos específicos
    (PDF, DOCX…) em páginas de texto puro.
    """

    @abstractmethod
    def parse(self, file_path: str) -> List[ParsedPage]:
        """Extrai o texto de *file_path* página a página.

        Returns:
            Lista de :class:`ParsedPage` com número de página (1-indexado) e texto.
            Páginas vazias são omitidas.
        """
        ...
