from fastapi import APIRouter, Depends

from app.core.dependencies import get_inventory_use_case
from app.use_cases.get_inventory import GetInventory

router = APIRouter()


@router.get("/api/inventory")
async def get_inventory(use_case: GetInventory = Depends(get_inventory_use_case)):
    """Inventário de documentos indexados, agrupado por seguradora.

    Retorna:
    - ``total_documents``: quantidade de arquivos no índice.
    - ``total_chunks``: total de fragmentos vetorizados.
    - ``by_seguradora``: documentos agrupados por seguradora.
    - ``documents``: lista plana com todos os registros.
    """
    return use_case.execute()
