from typing import List
from app.v1.schemas.common.list.base_list_response import BaseListResponse
from app.v1.schemas.defi.read import DefiRead


class DefiListRead(BaseListResponse):
    data: List[DefiRead]
