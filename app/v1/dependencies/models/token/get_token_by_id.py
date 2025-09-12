from fastapi import Depends
from app.models.token import Token
from app.repositories.token_repository import TokenRepository
from app.lib.utils.convert_id import decode_id
from app.dependencies.repositories.token_repository import (
    get_token_repository,
)


async def get_token_by_id(
    token_id: str,
    token_repository: TokenRepository = Depends(get_token_repository),
) -> Token:
    token = await token_repository.find_by_or_raise(
        id=decode_id(token_id),
        joinedload_models=[Token.chain],
    )
    return token
