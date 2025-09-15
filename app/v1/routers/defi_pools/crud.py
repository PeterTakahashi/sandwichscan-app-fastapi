from fastapi import Depends, Request
from app.v1.schemas.defi_pool import (
    DefiPoolListRead,
    DefiPoolRead,
    DefiPoolSearchParams,
)
from app.v1.dependencies.models.defi_pool.get_defi_pool_by_id import (
    get_defi_pool_by_id,
)
from app.v1.dependencies.services.defi_pool_service import get_defi_pool_service
from app.v1.services.defi_pool_service import DefiPoolService
from app.models.defi_pool import DefiPool
from app.v1.dependencies.query_params.get_defi_pool_search_params import (
    get_defi_pool_search_params,
)

from app.core.routers.api_router import APIRouter

router = APIRouter(prefix="/defi_pools", tags=["DefiPools"])


@router.get(
    "",
    response_model=DefiPoolListRead,
    name="defi_pools:list_defi_pools",
)
async def list_defi_pools(
    request: Request,
    search_params: DefiPoolSearchParams = Depends(get_defi_pool_search_params),
    service: DefiPoolService = Depends(get_defi_pool_service),
):
    """
    Retrieve a list of defi_pools with filtering, sorting, and pagination.
    """
    return await service.get_list(search_params=search_params)


@router.get(
    "/{defi_pool_id}",
    response_model=DefiPoolRead,
    name="defi_pools:get_defi_pool",
)
async def get_defi_pool(
    defi_pool: DefiPool = Depends(get_defi_pool_by_id),
):
    """
    Retrieve an defi_pool by its ID.
    """
    return DefiPoolRead.model_validate(defi_pool)
