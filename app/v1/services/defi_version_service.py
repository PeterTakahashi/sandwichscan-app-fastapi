from app.v1.schemas.defi_version import (
    DefiVersionRead,
    DefiVersionListRead,
    DefiVersionSearchParams,
)
from app.repositories.defi_version_repository import DefiVersionRepository

from app.v1.schemas.common.list.base_list_response import ListResponseMeta
from app.models.defi_version import DefiVersion


class DefiVersionService:
    def __init__(
        self,
        defi_version_repository: DefiVersionRepository,
    ):
        self.defi_version_repository = defi_version_repository

    async def get_list(self, search_params: DefiVersionSearchParams) -> DefiVersionListRead:
        """
        Retrieve a list of defi_versions with filtering, sorting, and pagination.
        """
        defi_versions = await self.defi_version_repository.where(
            **search_params.model_dump(exclude_none=True),
            joinedload_models=[DefiVersion.defi]
        )
        total_count = await self.defi_version_repository.count(
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        return DefiVersionListRead(
            meta=ListResponseMeta(
                total_count=total_count,
                **search_params.model_dump(exclude_none=True),
            ),
            data=[DefiVersionRead.model_validate(tx) for tx in defi_versions],
        )
