from typing import Optional, List
from datetime import datetime
from pydantic import field_validator
from app.v1.schemas.common.list.base_search_params import BaseSearchParams
from app.v1.schemas.common.validators import decode_hashid_list


class SandwichAttackSearchParams(BaseSearchParams):
    chain_id__in: Optional[List[str]] = None
    victim_address__exact: Optional[str] = None
    attacker_address__exact: Optional[str] = None
    revenue_base_raw__gte: Optional[int] = None
    revenue_base_raw__lte: Optional[int] = None
    profit_base_raw__gte: Optional[int] = None
    profit_base_raw__lte: Optional[int] = None
    harm_base_raw__gte: Optional[int] = None
    harm_base_raw__lte: Optional[int] = None
    gas_fee_wei_attacker__gte: Optional[int] = None
    gas_fee_wei_attacker__lte: Optional[int] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None
    updated_at__gte: Optional[datetime] = None
    updated_at__lte: Optional[datetime] = None

    @field_validator("chain_id__in", mode="before")
    @classmethod
    def _decode_ids(cls, values: Optional[List[str]]) -> Optional[list[int]]:
        return decode_hashid_list(values)
