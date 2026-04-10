"""Use Case: GetInventory.

Consulta o catálogo de documentos e retorna o inventário organizado
por seguradora, pronto para exibição na UI ou no endpoint /api/inventory.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.domain.interfaces.document_catalog import DocumentCatalog


class GetInventory:
    """Retorna o inventário de documentos indexados, agrupado por seguradora."""

    def __init__(self, catalog: DocumentCatalog) -> None:
        self._catalog = catalog

    def execute(self) -> Dict[str, Any]:
        """Executa a consulta ao catálogo.

        Returns:
            Dict com chaves:
            - ``total_documents``: total de arquivos registrados.
            - ``total_chunks``: soma de chunk_count de todos os documentos.
            - ``by_seguradora``: dict seguradora → lista de registros (dict).
            - ``documents``: lista plana de todos os registros (dict).
        """
        documents = self._catalog.list_all()
        total_chunks = self._catalog.total_chunks()

        by_seguradora: Dict[str, List[Dict[str, Any]]] = {}
        for doc in documents:
            seg = doc.seguradora
            if seg not in by_seguradora:
                by_seguradora[seg] = []
            by_seguradora[seg].append(doc.model_dump())

        return {
            "total_documents": len(documents),
            "total_chunks": total_chunks,
            "by_seguradora": by_seguradora,
            "documents": [d.model_dump() for d in documents],
        }
