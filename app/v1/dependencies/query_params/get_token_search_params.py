from typing import Optional, List
from fastapi import Query
from datetime import datetime
from app.v1.schemas.token.search_params import (
    TokenSearchParams,
)
from app.models.enums.token import TokenType


def get_token_search_params(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sorted_by: str = Query("created_at"),
    sorted_order: str = Query("desc"),
    token_type__in: Optional[List[TokenType]] = Query(None),
    address__exact: Optional[str] = Query(None),
    symbol__exact: Optional[str] = Query(None),
    chain_id__in: Optional[List[str]] = Query(None),
    token0_id__exact: Optional[int] = Query(None, ge=0),
    token1_id__exact: Optional[int] = Query(None, ge=0),
    created_at__gte: Optional[datetime] = Query(None),
    created_at__lte: Optional[datetime] = Query(None),
    updated_at__gte: Optional[datetime] = Query(None),
    updated_at__lte: Optional[datetime] = Query(None),
) -> TokenSearchParams:
    return TokenSearchParams(
        limit=limit,
        offset=offset,
        sorted_by=sorted_by,
        sorted_order=sorted_order,
        token_type__in=token_type__in,
        address__exact=address__exact,
        symbol__exact=symbol__exact,
        chain_id__in=chain_id__in,
        token0_id__exact=token0_id__exact,
        token1_id__exact=token1_id__exact,
        created_at__gte=created_at__gte,
        created_at__lte=created_at__lte,
        updated_at__gte=updated_at__gte,
        updated_at__lte=updated_at__lte,
    )
