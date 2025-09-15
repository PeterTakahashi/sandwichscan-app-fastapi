from fastapi import Depends, Request
from app.v1.schemas.token import (
    TokenListRead,
    TokenRead,
    TokenSearchParams,
)
from app.v1.dependencies.models.token.get_token_by_id import (
    get_token_by_id,
)
from app.v1.dependencies.services.token_service import get_token_service
from app.v1.services.token_service import TokenService
from app.models.token import Token
from app.v1.dependencies.query_params.get_token_search_params import (
    get_token_search_params,
)

from app.core.routers.api_router import APIRouter

router = APIRouter(prefix="/tokens", tags=["Tokens"])


@router.get(
    "",
    response_model=TokenListRead,
    name="tokens:list_tokens",
)
async def list_tokens(
    request: Request,
    search_params: TokenSearchParams = Depends(get_token_search_params),
    service: TokenService = Depends(get_token_service),
):
    """
    Retrieve a list of tokens with filtering, sorting, and pagination.
    """
    return await service.get_list(search_params=search_params)


@router.get(
    "/{token_id}",
    response_model=TokenRead,
    name="tokens:get_token",
)
async def get_token(
    token: Token = Depends(get_token_by_id),
):
    """
    Retrieve an token by its ID.
    """
    return TokenRead.model_validate(token)
