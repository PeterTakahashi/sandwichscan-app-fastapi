from fastapi import Depends
from app.v1.services.chain_service import ChainService
from app.repositories.chain_repository import ChainRepository
from app.dependencies.repositories.chain_repository import (
    get_chain_repository,
)


def get_chain_service(
    chain_repository: ChainRepository = Depends(get_chain_repository),
) -> ChainService:
    return ChainService(
        chain_repository=chain_repository,
    )
