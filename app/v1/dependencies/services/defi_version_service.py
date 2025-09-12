from fastapi import Depends
from app.v1.services.defi_version_service import DefiVersionService
from app.repositories.defi_version_repository import DefiVersionRepository
from app.dependencies.repositories.defi_version_repository import (
    get_defi_version_repository,
)


def get_defi_version_service(
    defi_version_repository: DefiVersionRepository = Depends(get_defi_version_repository),
) -> DefiVersionService:
    return DefiVersionService(
        defi_version_repository=defi_version_repository,
    )
