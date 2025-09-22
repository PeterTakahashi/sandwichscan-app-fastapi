from typing import Optional, List
from fastapi import Query
from datetime import datetime
from app.v1.schemas.defi_pool.search_params import (
    DefiPoolSearchParams,
)


def get_defi_pool_search_params(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sorted_by: str = Query("created_at"),
    sorted_order: str = Query("desc"),
    address__exact: Optional[str] = Query(None),
    created_block_number__gte: Optional[int] = Query(None, ge=0),
    created_block_number__lte: Optional[int] = Query(None, ge=0),
    chain_id__in: Optional[List[str]] = Query(None),
    token0_id__exact: Optional[int] = Query(None, ge=0),
    token1_id__exact: Optional[int] = Query(None, ge=0),
    fee_tier_bps__gte: Optional[int] = Query(None, ge=0),
    fee_tier_bps__lte: Optional[int] = Query(None, ge=0),
    created_at__gte: Optional[datetime] = Query(None),
    created_at__lte: Optional[datetime] = Query(None),
    updated_at__gte: Optional[datetime] = Query(None),
    updated_at__lte: Optional[datetime] = Query(None),
) -> DefiPoolSearchParams:
    return DefiPoolSearchParams(
        limit=limit,
        offset=offset,
        sorted_by=sorted_by,
        sorted_order=sorted_order,
        address__exact=address__exact,
        created_block_number__gte=created_block_number__gte,
        created_block_number__lte=created_block_number__lte,
        chain_id__in=chain_id__in,
        token0_id__exact=token0_id__exact,
        token1_id__exact=token1_id__exact,
        fee_tier_bps__gte=fee_tier_bps__gte,
        fee_tier_bps__lte=fee_tier_bps__lte,
        created_at__gte=created_at__gte,
        created_at__lte=created_at__lte,
        updated_at__gte=updated_at__gte,
        updated_at__lte=updated_at__lte,
    )
