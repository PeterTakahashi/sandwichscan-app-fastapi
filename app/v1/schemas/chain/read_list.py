from typing import List
from app.v1.schemas.common.list.base_list_response import BaseListResponse
from app.v1.schemas.chain.read import ChainRead


class ChainListRead(BaseListResponse):
    data: List[ChainRead]
