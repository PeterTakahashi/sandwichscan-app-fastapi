from typing import Optional
from datetime import datetime
from app.v1.schemas.common.list.base_search_params import BaseSearchParams


class DefiPoolSearchParams(BaseSearchParams):
    address__exact: Optional[str] = None
    created_block_number__gte: Optional[int] = None
    created_block_number__lte: Optional[int] = None
    chain_id__in: Optional[list[int]] = None
    token0_id__exact: Optional[int] = None
    token1_id__exact: Optional[int] = None
    fee_tier_bps__gte: Optional[int] = None
    fee_tier_bps__lte: Optional[int] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None
    updated_at__gte: Optional[datetime] = None
    updated_at__lte: Optional[datetime] = None
