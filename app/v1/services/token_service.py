from app.v1.schemas.token import (
    TokenRead,
    TokenListRead,
    TokenSearchParams,
)
from app.repositories.token_repository import TokenRepository

from app.v1.schemas.common.list.base_list_response import ListResponseMeta
from app.models.token import Token


class TokenService:
    def __init__(
        self,
        token_repository: TokenRepository,
    ):
        self.token_repository = token_repository

    async def get_list(self, search_params: TokenSearchParams) -> TokenListRead:
        """
        Retrieve a list of tokens with filtering, sorting, and pagination.
        """
        tokens = await self.token_repository.where(
            **search_params.model_dump(exclude_none=True),
            joinedload_models=[Token.chain],
        )
        total_count = await self.token_repository.count(
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        return TokenListRead(
            meta=ListResponseMeta(
                total_count=total_count,
                **search_params.model_dump(exclude_none=True),
            ),
            data=[TokenRead.model_validate(tx) for tx in tokens],
        )
