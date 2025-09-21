from fastapi import Depends
from app.models.swap import Swap
from app.repositories.swap_repository import SwapRepository
from app.lib.utils.convert_id import decode_id
from app.dependencies.repositories.swap_repository import (
    get_swap_repository,
)


async def get_swap_by_id(
    swap_id: str,
    swap_repository: SwapRepository = Depends(get_swap_repository),
) -> Swap:
    swap = await swap_repository.find_by_or_raise(
        id=decode_id(swap_id),
        joinedload_models=[
            Swap.chain,
            Swap.defi_pool,
            Swap.transaction,
            Swap.sell_token,
            Swap.buy_token,
        ],  # Eager load relationships
    )
    return swap
