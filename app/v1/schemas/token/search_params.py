from typing import Optional, List, Union
from datetime import datetime
from app.v1.schemas.common.list.base_search_params import BaseSearchParams
from app.models.enums.token import TokenType
from pydantic import field_validator
from app.v1.schemas.common.validators import decode_hashid_list


class TokenSearchParams(BaseSearchParams):
    token_type__in: Optional[List[TokenType]] = None
    address__exact: Optional[str] = None
    symbol__exact: Optional[str] = None
    chain_id__in: Optional[List[int]] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None
    updated_at__gte: Optional[datetime] = None
    updated_at__lte: Optional[datetime] = None

    @field_validator("chain_id__in", mode="before")
    @classmethod
    def _decode_ids(
        cls, values: Optional[Union[List[str], str]]
    ) -> Optional[list[int]]:
        return decode_hashid_list(values)
