from fastapi import Depends
from app.models.defi_version import DefiVersion
from app.repositories.defi_version_repository import DefiVersionRepository
from app.lib.utils.convert_id import decode_id
from app.dependencies.repositories.defi_version_repository import (
    get_defi_version_repository,
)


async def get_defi_version_by_id(
    defi_version_id: str,
    defi_version_repository: DefiVersionRepository = Depends(get_defi_version_repository),
) -> DefiVersion:
    defi_version = await defi_version_repository.find_by_or_raise(id=decode_id(defi_version_id))
    return defi_version
