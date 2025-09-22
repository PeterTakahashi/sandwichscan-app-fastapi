from typing import Optional, List
from datetime import datetime
from pydantic import field_validator
from app.v1.schemas.common.list.base_search_params import BaseSearchParams
from app.v1.schemas.common.validators import decode_hashid_list


class DefiPoolSearchParams(BaseSearchParams):
    address__exact: Optional[str] = None
    created_block_number__gte: Optional[int] = None
    created_block_number__lte: Optional[int] = None
    chain_id__in: Optional[List[int]] = None
    token0_id__exact: Optional[int] = None
    token1_id__exact: Optional[int] = None
    fee_tier_bps__gte: Optional[int] = None
    fee_tier_bps__lte: Optional[int] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None
    updated_at__gte: Optional[datetime] = None
    updated_at__lte: Optional[datetime] = None

    @field_validator("chain_id__in", mode="before")
    @classmethod
    def _decode_ids(cls, values: Optional[List[str]]) -> Optional[list[int]]:
        return decode_hashid_list(values)
