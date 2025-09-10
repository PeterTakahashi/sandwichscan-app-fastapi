from app.v1.schemas.chain import (
    ChainRead,
    ChainListRead,
    ChainSearchParams,
)
from app.models.chain import Chain
from app.repositories.chain_repository import ChainRepository

from app.v1.schemas.common.list.base_list_response import ListResponseMeta


class ChainService:
    def __init__(
        self,
        chain_repository: ChainRepository,
    ):
        self.chain_repository = chain_repository

    async def get_list(self, search_params: ChainSearchParams) -> ChainListRead:
        """
        Retrieve a list of chains with filtering, sorting, and pagination.
        """
        chains = await self.chain_repository.where(
            **search_params.model_dump(exclude_none=True),
        )
        total_count = await self.chain_repository.count(
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        return ChainListRead(
            meta=ListResponseMeta(
                total_count=total_count,
                **search_params.model_dump(exclude_none=True),
            ),
            data=[ChainRead.model_validate(tx) for tx in chains],
        )
