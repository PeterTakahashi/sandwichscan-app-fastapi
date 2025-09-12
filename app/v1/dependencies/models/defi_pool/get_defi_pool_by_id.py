from fastapi import Depends
from app.models.defi_pool import DefiPool
from app.repositories.defi_pool_repository import DefiPoolRepository
from app.lib.utils.convert_id import decode_id
from app.dependencies.repositories.defi_pool_repository import (
    get_defi_pool_repository,
)


async def get_defi_pool_by_id(
    defi_pool_id: str,
    defi_pool_repository: DefiPoolRepository = Depends(get_defi_pool_repository),
) -> DefiPool:
    defi_pool = await defi_pool_repository.find_by_or_raise(id=decode_id(defi_pool_id))
    return defi_pool
