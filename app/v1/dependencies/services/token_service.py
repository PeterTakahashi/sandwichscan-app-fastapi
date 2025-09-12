from fastapi import Depends
from app.v1.services.token_service import TokenService
from app.repositories.token_repository import TokenRepository
from app.dependencies.repositories.token_repository import (
    get_token_repository,
)


def get_token_service(
    token_repository: TokenRepository = Depends(get_token_repository),
) -> TokenService:
    return TokenService(
        token_repository=token_repository,
    )
