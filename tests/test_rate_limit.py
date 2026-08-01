"""Testes do RateLimiter (app/core/rate_limit.py)."""
from __future__ import annotations

import time

import pytest

from app.core.rate_limit import RateLimiter


class TestRateLimiter:
    def test_permite_ate_o_limite(self) -> None:
        rl = RateLimiter(max_requests=3, window_seconds=60)
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is True

    def test_bloqueia_excedente(self) -> None:
        rl = RateLimiter(max_requests=2, window_seconds=60)
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is False

    def test_janela_deslizante_expira(self) -> None:
        rl = RateLimiter(max_requests=2, window_seconds=0.05)
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is False
        time.sleep(0.07)
        assert rl.allow("ip-1") is True  # janela expirou

    def test_chaves_independentes(self) -> None:
        rl = RateLimiter(max_requests=1, window_seconds=60)
        assert rl.allow("ip-a") is True
        assert rl.allow("ip-b") is True
        assert rl.allow("ip-a") is False
        assert rl.allow("ip-b") is False

    def test_reset_por_chave(self) -> None:
        rl = RateLimiter(max_requests=1, window_seconds=60)
        assert rl.allow("ip-1") is True
        assert rl.allow("ip-1") is False
        rl.reset("ip-1")
        assert rl.allow("ip-1") is True

    def test_reset_total(self) -> None:
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.allow("ip-1")
        rl.allow("ip-2")
        assert rl.keys == 2
        rl.reset()
        assert rl.keys == 0
        assert rl.allow("ip-1") is True

    def test_max_requests_invalido(self) -> None:
        with pytest.raises(ValueError):
            RateLimiter(max_requests=0)
