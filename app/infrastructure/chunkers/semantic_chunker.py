"""Chunking semântico heurístico para apólices de seguros.

Implementa :class:`TextChunker` dividindo o texto nos limites naturais do
documento (parágrafos, cláusulas numeradas, artigos, seções) antes de
recorrer ao corte fixo por caractere.  Isso mantém cláusulas inteiras no
mesmo chunk, melhorando a precisão das citações.
"""
from __future__ import annotations

import re
from typing import List

from app.domain.interfaces.text_chunker import TextChunker

# Detecta limites semânticos comuns em apólices brasileiras
_CLAUSE_BOUNDARY = re.compile(
    r'\n{2,}'                                               # parágrafo duplo
    r'|\n(?=[ \t]*(?:'
    r'\d+(?:\.\d+)*\.?[ \t]'                               # cláusulas numeradas: "1.", "3.2."
    r'|Art\.?[ \t]|Artigo[ \t]'                            # artigos
    r'|SEÇ[AÃ]O\b|CAP[IÍ]TULO\b|CL[AÁ]USULA\b'          # seções
    r'|COBERTURA\b|EXCLUS[AÃ]O\b|FRANQUIA\b'              # blocos de apólice
    r'))',
    re.IGNORECASE,
)


class InsuranceSemanticChunker(TextChunker):
    """Chunker baseado em heurísticas de seguros + fallback de tamanho fixo."""

    def chunk(
        self,
        text: str,
        chunk_size: int = 1200,
        overlap: int = 200,
    ) -> List[tuple[str, int]]:
        segments = self._split_by_boundaries(text)
        if not segments:
            return self._fixed_chunk(text, chunk_size, overlap)
        return self._merge_segments(segments, text, chunk_size, overlap)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _split_by_boundaries(self, text: str) -> List[tuple[str, int]]:
        """Quebra o texto nos limites semânticos detectados pelo regex."""
        segments: List[tuple[str, int]] = []
        last = 0
        for m in _CLAUSE_BOUNDARY.finditer(text):
            seg = text[last : m.start()].strip()
            if seg:
                segments.append((seg, last))
            last = m.end()
        if last < len(text):
            seg = text[last:].strip()
            if seg:
                segments.append((seg, last))
        return segments

    def _merge_segments(
        self,
        segments: List[tuple[str, int]],
        original_text: str,
        chunk_size: int,
        overlap: int,
    ) -> List[tuple[str, int]]:
        """Agrupa segmentos em chunks respeitando chunk_size, com overlap."""
        chunks: List[tuple[str, int]] = []
        current_parts: List[str] = []
        current_start = 0
        current_len = 0

        for seg_text, seg_pos in segments:
            if len(seg_text) > chunk_size:
                # Segmento isolado muito grande: fechar acumulado e subdividir
                if current_parts:
                    chunks.append(("\n\n".join(current_parts), current_start))
                    current_parts, current_len = [], 0
                for sub_text, sub_pos in self._fixed_chunk(seg_text, chunk_size, overlap):
                    chunks.append((sub_text, seg_pos + sub_pos))
                current_start = 0
                continue

            if current_len + len(seg_text) + 2 > chunk_size and current_parts:
                # Fechar chunk atual e iniciar novo com overlap
                chunk = "\n\n".join(current_parts)
                chunks.append((chunk, current_start))
                overlap_text = chunk[-overlap:] if len(chunk) > overlap else chunk
                current_parts = [overlap_text, seg_text]
                current_start = seg_pos
                current_len = len(overlap_text) + len(seg_text) + 2
            else:
                if not current_parts:
                    current_start = seg_pos
                current_parts.append(seg_text)
                current_len += len(seg_text) + 2

        if current_parts:
            chunks.append(("\n\n".join(current_parts), current_start))

        return chunks or self._fixed_chunk(original_text, chunk_size, overlap)

    @staticmethod
    def _fixed_chunk(text: str, chunk_size: int, overlap: int) -> List[tuple[str, int]]:
        """Fallback: divide por tamanho fixo com overlap, evitando cortar palavras."""
        chunks: List[tuple[str, int]] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if end < len(text) and text[end] != " ":
                last_space = chunk.rfind(" ")
                if last_space != -1:
                    end = start + last_space + 1
                    chunk = text[start:end]
            chunks.append((chunk.strip(), start))
            start = end - overlap
            if start >= len(text):
                break
        return chunks
