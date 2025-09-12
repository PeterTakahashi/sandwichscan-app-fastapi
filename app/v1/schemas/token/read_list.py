from typing import List
from app.v1.schemas.common.list.base_list_response import BaseListResponse
from app.v1.schemas.token.read import TokenRead


class TokenListRead(BaseListResponse):
    data: List[TokenRead]
