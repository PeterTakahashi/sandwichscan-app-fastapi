from fastapi import Depends
from app.v1.services.defi_service import DefiService
from app.repositories.defi_repository import DefiRepository
from app.dependencies.repositories.defi_repository import (
    get_defi_repository,
)


def get_defi_service(
    defi_repository: DefiRepository = Depends(get_defi_repository),
) -> DefiService:
    return DefiService(
        defi_repository=defi_repository,
    )
