from typing import List
from pydantic import BaseModel
from app.v1.schemas.sandwich_attack.read_on_list import SandwichAttackReadOnList
from app.v1.schemas.sandwich_attack.list_response_meta import (
    SandwichAttackListResponseMeta,
)


class SandwichAttackListRead(BaseModel):
    meta: SandwichAttackListResponseMeta
    data: List[SandwichAttackReadOnList]
