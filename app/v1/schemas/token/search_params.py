from typing import Optional
from datetime import datetime
from app.v1.schemas.common.list.base_search_params import BaseSearchParams
from typing import List
from app.models.enums.token import TokenType


class TokenSearchParams(BaseSearchParams):
    token_type__in: Optional[List[TokenType]] = None
    address__exact: Optional[str] = None
    symbol__exact: Optional[str] = None
    chain_id__exact: Optional[str] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None
    updated_at__gte: Optional[datetime] = None
    updated_at__lte: Optional[datetime] = None
