from typing import List
from app.v1.schemas.common.list.base_list_response import BaseListResponse
from app.v1.schemas.defi_pool.read import DefiPoolRead


class DefiPoolListRead(BaseListResponse):
    data: List[DefiPoolRead]
