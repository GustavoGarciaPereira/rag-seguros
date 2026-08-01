"""Rate limiter simples em memória (janela deslizante por chave).

Sem dependências externas — suficiente para mitigar abuso de custo
(endpoints que chamam o LLM) em um serviço single-process.
"""
import threading
import time
from typing import Dict, List, Optional


class RateLimiter:
    """Permite no máximo ``max_requests`` chamadas por janela por chave."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests deve ser > 0")
        self._max_requests = max_requests
        self._window = window_seconds
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Registra uma chamada e retorna True se dentro do limite."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            hits = self._hits.setdefault(key, [])
            # Poda entradas fora da janela (lista ordenada por tempo)
            while hits and hits[0] < cutoff:
                hits.pop(0)
            # Poda de chaves mortas: evita crescimento sem teto com IPs distintos
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if v}
            if len(hits) >= self._max_requests:
                return False
            hits.append(now)
            return True

    def reset(self, key: Optional[str] = None) -> None:
        """Zera o histórico de uma chave (ou de todas, se key=None)."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    @property
    def keys(self) -> int:
        with self._lock:
            return len(self._hits)
