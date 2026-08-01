"""Testes das validações de entrada da API (filter e upload)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes.ask import _validate_filter
from app.api.routes.upload import _validate_pdf_bytes


class TestValidateFilter:
    def test_filtro_vazio_ok(self) -> None:
        _validate_filter(None)
        _validate_filter({})

    def test_chaves_validas_ok(self) -> None:
        _validate_filter({"seguradora": "Bradesco"})
        _validate_filter({"ramo": "Automovel"})
        _validate_filter({"seguradora": "Allianz", "ramo": "PME"})

    def test_chave_desconhecida_rejeitada(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _validate_filter({"seguradora": "Bradesco", "ano": "2024"})
        assert exc.value.status_code == 400
        assert "ano" in exc.value.detail

    def test_valor_muito_longo_rejeitado(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _validate_filter({"seguradora": "X" * 200})
        assert exc.value.status_code == 400

    def test_valor_no_limite_aceito(self) -> None:
        _validate_filter({"seguradora": "X" * 100})


class TestValidatePdfBytes:
    def test_pdf_valido_ok(self) -> None:
        _validate_pdf_bytes(b"%PDF-1.7\nconteudo")

    def test_nao_pdf_rejeitado(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _validate_pdf_bytes(b"<html>nao sou pdf</html>")
        assert exc.value.status_code == 400
        assert "%PDF" in exc.value.detail

    def test_vazio_rejeitado(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _validate_pdf_bytes(b"")
        assert exc.value.status_code == 400

    def test_tamanho_acima_do_limite_rejeitado(self) -> None:
        from app.core.config import MAX_FILE_SIZE

        with pytest.raises(HTTPException) as exc:
            _validate_pdf_bytes(b"%PDF-" + b"0" * (MAX_FILE_SIZE + 1))
        assert exc.value.status_code == 413
