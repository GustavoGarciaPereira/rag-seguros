from collections import deque
import time as _time
from typing import Deque, Tuple


class MetricsStore:
    """Armazena latências de queries em memória sem dependências externas."""

    def __init__(self) -> None:
        self._events: Deque[Tuple[float, float, float]] = deque()  # (ts, retrieval_ms, llm_ms)

    def record(self, retrieval_ms: float, llm_ms: float) -> None:
        self._events.append((_time.time(), retrieval_ms, llm_ms))
        self._prune()

    def _prune(self) -> None:
        cutoff = _time.time() - 86400
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def stats(self) -> dict:
        self._prune()
        ev = list(self._events)
        n = len(ev)
        if n == 0:
            return {"queries_24h": 0, "avg_retrieval_ms": 0.0, "avg_llm_ms": 0.0, "avg_total_ms": 0.0}
        avg_r = sum(e[1] for e in ev) / n
        avg_l = sum(e[2] for e in ev) / n
        return {
            "queries_24h": n,
            "avg_retrieval_ms": round(avg_r, 1),
            "avg_llm_ms": round(avg_l, 1),
            "avg_total_ms": round(avg_r + avg_l, 1),
        }


metrics = MetricsStore()
