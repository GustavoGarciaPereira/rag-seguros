"""Chunking semântico heurístico para apólices de seguros.

Implementa :class:`TextChunker` dividindo o texto nos limites naturais do
documento (parágrafos, cláusulas numeradas, artigos, seções) antes de
recorrer ao corte fixo por caractere.  Isso mantém cláusulas inteiras no
mesmo chunk, melhorando a precisão das citações.

Injeção de título de seção
--------------------------
Tabelas e listas têm pouco texto próprio e perdem no score semântico para
parágrafos densos.  Para mitigar isso, cada chunk recebe um prefixo com o
último título de seção detectado antes do chunk:

    [SEÇÃO: CLÁUSULA 5 – COBERTURAS]
    | Cobertura | Limite |
    | Incêndio  | 100%   |

Chunks que já são o próprio título não recebem o prefixo duplicado.
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

# Padrões explícitos de cabeçalhos de seção
_SECTION_TITLE_RE = re.compile(
    r'^\s*(?:'
    r'(?:Art\.?|Artigo)\s+\d+'                              # Artigo N / Art. N
    r'|(?:SEÇ[AÃ]O|CAP[IÍ]TULO|CL[AÁ]USULA)\s*\d*'       # SEÇÃO, CAPÍTULO, CLÁUSULA
    r'|(?:COBERTURA|EXCLUS[AÃ]O|FRANQUIA)\b'               # blocos de apólice
    r'|[IVX]{2,7}[.\s]'                                    # algarismos romanos: II, III, IV…
    r'|\d+(?:\.\d+)*\.\s+[A-ZÁÉÍÓÚ]'                      # numerados: "1. Título", "3.2. X"
    r')',
    re.IGNORECASE,
)


def _is_section_title(text: str) -> bool:
    """True se *text* parece um cabeçalho de seção de apólice."""
    first_line = text.split('\n', 1)[0].strip()
    if not first_line or len(first_line) > 120:
        return False
    if _SECTION_TITLE_RE.match(first_line):
        return True
    # Heurística: linha curta com todas as letras em maiúsculas e ao menos
    # duas palavras → provável título (ex: "DISPOSIÇÕES GERAIS")
    words = re.findall(r'[A-Za-zÀ-ÿ]+', first_line)
    letters = ''.join(words)
    if len(words) >= 2 and letters == letters.upper() and len(first_line) <= 80:
        return True
    return False


def _apply_section_prefix(chunk_text: str, section_title: str) -> str:
    """Prefixa *chunk_text* com ``[SEÇÃO: <título>]`` quando aplicável.

    O prefixo é omitido se o chunk já abre com o próprio título (evita
    duplicação no chunk que contém o cabeçalho).
    """
    if not section_title:
        return chunk_text
    first_line = chunk_text.strip().split('\n', 1)[0].strip()
    if first_line == section_title or first_line.startswith(section_title):
        return chunk_text
    return f"[SEÇÃO: {section_title}]\n{chunk_text}"


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
        """Agrupa segmentos em chunks respeitando chunk_size, com overlap.

        Rastreia o último título de seção visto e injeta-o como prefixo nos
        chunks que não são o próprio título (ver :func:`_apply_section_prefix`).
        """
        chunks: List[tuple[str, int]] = []
        current_parts: List[str] = []
        current_start = 0
        current_len = 0
        last_section: str = None   # último título detectado no texto
        chunk_section: str = None  # título ativo no início do chunk corrente

        for seg_text, seg_pos in segments:
            if _is_section_title(seg_text):
                last_section = seg_text.split('\n', 1)[0].strip()

            if len(seg_text) > chunk_size:
                # Segmento isolado muito grande: fechar acumulado e subdividir
                if current_parts:
                    chunk = "\n\n".join(current_parts)
                    chunks.append((_apply_section_prefix(chunk, chunk_section), current_start))
                    current_parts, current_len = [], 0
                for sub_text, sub_pos in self._fixed_chunk(seg_text, chunk_size, overlap):
                    chunks.append((_apply_section_prefix(sub_text, last_section), seg_pos + sub_pos))
                current_start = 0
                chunk_section = last_section
                continue

            if current_len + len(seg_text) + 2 > chunk_size and current_parts:
                # Fechar chunk atual e iniciar novo com overlap
                chunk = "\n\n".join(current_parts)
                chunks.append((_apply_section_prefix(chunk, chunk_section), current_start))
                overlap_text = chunk[-overlap:] if len(chunk) > overlap else chunk
                current_parts = [overlap_text, seg_text]
                current_start = seg_pos
                current_len = len(overlap_text) + len(seg_text) + 2
                chunk_section = last_section  # captura seção ativa no início do novo chunk
            else:
                if not current_parts:
                    current_start = seg_pos
                    chunk_section = last_section  # captura seção ativa quando o chunk começa
                current_parts.append(seg_text)
                current_len += len(seg_text) + 2

        if current_parts:
            chunk = "\n\n".join(current_parts)
            chunks.append((_apply_section_prefix(chunk, chunk_section), current_start))

        return chunks or self._fixed_chunk(original_text, chunk_size, overlap)

    @staticmethod
    def _fixed_chunk(text: str, chunk_size: int, overlap: int) -> List[tuple[str, int]]:
        """Fallback: divide por tamanho fixo com overlap, evitando cortar palavras.

        # Optimization target: este processamento de string pesado (iteração byte a byte
        # para encontrar word boundaries + construção de lista de tuplas) será movido para
        # uma extensão em Rust/PyO3.  A interface permanece idêntica: recebe str Python,
        # devolve List[tuple[str, int]].  O ganho esperado é ~5-10× em documentos grandes
        # (>500 páginas) onde este método é chamado O(n_segmentos) vezes.
        """
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
