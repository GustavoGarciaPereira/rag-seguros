"""Enums de domínio para o contexto de seguros.

Centraliza os valores permitidos para seguradoras e tipos de documento,
eliminando strings mágicas espalhadas pelo código.
"""
from __future__ import annotations

from enum import Enum
from typing import List


class Seguradora(str, Enum):
    """Seguradoras suportadas pela plataforma."""

    BRADESCO = "Bradesco"
    PORTO_SEGURO = "Porto Seguro"
    AZUL = "Azul"
    ALLIANZ = "Allianz"
    TOKIO_MARINE = "Tokio Marine"
    LIBERTY = "Liberty"
    MAPFRE = "Mapfre"
    DESCONHECIDA = "Desconhecida"

    @classmethod
    def allowed_for_admin(cls) -> List[str]:
        """Valores aceitos no endpoint /admin/upload (exclui DESCONHECIDA)."""
        return [s.value for s in cls if s is not cls.DESCONHECIDA]


class DocumentType(str, Enum):
    """Tipos de documento reconhecidos."""

    APOLICE = "apolice"
    SINISTRO = "sinistro"
    COBERTURA = "cobertura"
    FRANQUIA = "franquia"
    ENDOSSO = "endosso"
    GERAL = "Geral"


class Ramo(str, Enum):
    """Ramo de seguro — evita confusão entre manuais de ramos distintos."""

    AGRICOLA = "Agricola"
    AUTOMOVEL = "Automovel"
    PME = "PME"
    CONSTRUCAO_CIVIL = "Construcao Civil"
    RESIDENCIAL = "Residencial"
    DESCONHECIDO = "Desconhecido"
