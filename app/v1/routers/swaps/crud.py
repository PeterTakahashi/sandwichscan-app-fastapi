from fastapi import Depends, Request
from app.v1.schemas.swap.read import SwapRead
from app.v1.dependencies.models.swap.get_swap_by_id import (
    get_swap_by_id,
)
from app.models.swap import Swap

from app.core.routers.api_router import APIRouter

router = APIRouter(prefix="/swaps", tags=["Swaps"])

@router.get(
    "/{swap_id}",
    response_model=SwapRead,
    name="swaps:get_swap",
)
async def get_swap(
    swap: Swap = Depends(get_swap_by_id),
):
    """
    Retrieve an swap by its ID.
    """
    return SwapRead.model_validate(swap)
