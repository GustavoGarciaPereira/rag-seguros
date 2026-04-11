from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class TextChunker(ABC):
    """Estratégia de divisão de texto em fragmentos indexáveis.

    Retorna lista de (chunk_text, start_pos) onde *start_pos* é o offset
    do chunk dentro do texto original — usado para calcular a página de cada chunk.
    """

    @abstractmethod
    def chunk(
        self,
        text: str,
        chunk_size: int = 1200,
        overlap: int = 200,
    ) -> List[tuple[str, int]]:
        ...
