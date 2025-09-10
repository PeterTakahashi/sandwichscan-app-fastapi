from app.v1.schemas.defi import (
    DefiRead,
    DefiListRead,
    DefiSearchParams,
)
from app.repositories.defi_repository import DefiRepository

from app.v1.schemas.common.list.base_list_response import ListResponseMeta


class DefiService:
    def __init__(
        self,
        defi_repository: DefiRepository,
    ):
        self.defi_repository = defi_repository

    async def get_list(self, search_params: DefiSearchParams) -> DefiListRead:
        """
        Retrieve a list of defis with filtering, sorting, and pagination.
        """
        defis = await self.defi_repository.where(
            **search_params.model_dump(exclude_none=True),
        )
        total_count = await self.defi_repository.count(
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        return DefiListRead(
            meta=ListResponseMeta(
                total_count=total_count,
                **search_params.model_dump(exclude_none=True),
            ),
            data=[DefiRead.model_validate(tx) for tx in defis],
        )
