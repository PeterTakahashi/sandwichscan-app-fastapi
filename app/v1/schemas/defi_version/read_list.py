from typing import List
from app.v1.schemas.common.list.base_list_response import BaseListResponse
from app.v1.schemas.defi_version.read import DefiVersionRead


class DefiVersionListRead(BaseListResponse):
    data: List[DefiVersionRead]
