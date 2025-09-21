from pydantic import Field
from app.v1.schemas.common.list.base_list_response import ListResponseMeta


class SandwichAttackListResponseMeta(ListResponseMeta):
    total_revenue_usd: float = Field(
        ...,
        description="Total revenue in USD for the current query.",
        json_schema_extra={"example": 100.00},
    )
    total_profit_usd: float = Field(
        ...,
        description="Total profit in USD for the current query.",
        json_schema_extra={"example": 100.00},
    )
    total_harm_usd: float = Field(
        ...,
        description="Total harm in USD for the current query.",
        json_schema_extra={"example": 100.00},
    )
