from app.v1.schemas.defi_pool import (
    DefiPoolRead,
    DefiPoolListRead,
    DefiPoolSearchParams,
)
from app.repositories.defi_pool_repository import DefiPoolRepository

from app.v1.schemas.common.list.base_list_response import ListResponseMeta
from app.models.defi_pool import DefiPool
from app.models.defi_factory import DefiFactory
from app.models.defi_version import DefiVersion


class DefiPoolService:
    def __init__(
        self,
        defi_pool_repository: DefiPoolRepository,
    ):
        self.defi_pool_repository = defi_pool_repository

    async def get_list(self, search_params: DefiPoolSearchParams) -> DefiPoolListRead:
        """
        Retrieve a list of defi_pools with filtering, sorting, and pagination.
        """
        defi_pools = await self.defi_pool_repository.where(
            **search_params.model_dump(exclude_none=True),
            joinedload_models=[
                DefiPool.chain,
                DefiPool.token0,
                DefiPool.token1,
                (DefiPool.defi_factory, DefiFactory.defi_version, DefiVersion.defi)
            ],  # Eager load relationships
        )
        total_count = await self.defi_pool_repository.count(
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        defi_pool = defi_pools[0]
        print(defi_pool.defi_factory.defi_version.name)
        return DefiPoolListRead(
            meta=ListResponseMeta(
                total_count=total_count,
                **search_params.model_dump(exclude_none=True),
            ),
            data=[DefiPoolRead.model_validate(tx) for tx in defi_pools],
        )
