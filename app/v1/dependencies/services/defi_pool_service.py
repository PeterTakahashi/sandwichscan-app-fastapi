from fastapi import Depends
from app.v1.services.defi_pool_service import DefiPoolService
from app.repositories.defi_pool_repository import DefiPoolRepository
from app.dependencies.repositories.defi_pool_repository import (
    get_defi_pool_repository,
)


def get_defi_pool_service(
    defi_pool_repository: DefiPoolRepository = Depends(get_defi_pool_repository),
) -> DefiPoolService:
    return DefiPoolService(
        defi_pool_repository=defi_pool_repository,
    )
