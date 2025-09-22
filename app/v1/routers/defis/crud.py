from fastapi import Depends, Request
from app.v1.schemas.defi import (
    DefiListRead,
    DefiRead,
    DefiSearchParams,
)
from app.v1.dependencies.models.defi.get_defi_by_id import (
    get_defi_by_id,
)
from app.v1.dependencies.services.defi_service import get_defi_service
from app.v1.services.defi_service import DefiService
from app.models.defi import Defi

from app.core.routers.api_router import APIRouter

router = APIRouter(prefix="/defis", tags=["Defis"])


@router.get(
    "",
    response_model=DefiListRead,
    name="defis:list_defis",
)
async def list_defis(
    request: Request,
    search_params: DefiSearchParams = Depends(),
    service: DefiService = Depends(get_defi_service),
):
    """
    Retrieve a list of defis with filtering, sorting, and pagination.
    """
    return await service.get_list(search_params=search_params)


@router.get(
    "/{defi_id}",
    response_model=DefiRead,
    name="defis:get_defi",
)
async def get_defi(
    defi: Defi = Depends(get_defi_by_id),
):
    """
    Retrieve an defi by its ID.
    """
    return DefiRead.model_validate(defi)
