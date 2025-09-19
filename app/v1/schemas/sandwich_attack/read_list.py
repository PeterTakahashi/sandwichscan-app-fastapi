from typing import List
from app.v1.schemas.common.list.base_list_response import BaseListResponse
from app.v1.schemas.sandwich_attack.read import SandwichAttackRead


class SandwichAttackListRead(BaseListResponse):
    data: List[SandwichAttackRead]
