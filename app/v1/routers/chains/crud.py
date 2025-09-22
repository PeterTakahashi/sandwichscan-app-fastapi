from fastapi import Depends, Request
from app.v1.schemas.chain import (
    ChainListRead,
    ChainRead,
    ChainSearchParams,
)
from app.v1.dependencies.models.chain.get_chain_by_id import (
    get_chain_by_id,
)
from app.v1.dependencies.services.chain_service import get_chain_service
from app.v1.services.chain_service import ChainService
from app.models.chain import Chain

from app.core.routers.api_router import APIRouter

router = APIRouter(prefix="/chains", tags=["Chains"])


@router.get(
    "",
    response_model=ChainListRead,
    name="chains:list_chains",
)
async def list_chains(
    request: Request,
    search_params: ChainSearchParams = Depends(),
    service: ChainService = Depends(get_chain_service),
):
    """
    Retrieve a list of chains with filtering, sorting, and pagination.
    """
    return await service.get_list(search_params=search_params)


@router.get(
    "/{chain_id}",
    response_model=ChainRead,
    name="chains:get_chain",
)
async def get_chain(
    chain: Chain = Depends(get_chain_by_id),
):
    """
    Retrieve an chain by its ID.
    """
    return ChainRead.model_validate(chain)
