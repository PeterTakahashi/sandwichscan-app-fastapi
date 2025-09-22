from fastapi import Depends
from app.models.defi import Defi
from app.repositories.defi_repository import DefiRepository
from app.lib.utils.convert_id import decode_id
from app.dependencies.repositories.defi_repository import (
    get_defi_repository,
)


async def get_defi_by_id(
    defi_id: str,
    defi_repository: DefiRepository = Depends(get_defi_repository),
) -> Defi:
    defi = await defi_repository.find_by_or_raise(id=decode_id(defi_id))
    return defi
