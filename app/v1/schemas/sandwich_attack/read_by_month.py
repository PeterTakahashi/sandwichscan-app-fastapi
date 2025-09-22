from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class SandwichAttackReadByMonth(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: datetime = Field(..., description="The month of the sandwich attacks.")
    total_attacks: int = Field(
        ..., description="Total number of sandwich attacks in the month."
    )
    total_revenue_usd: float = Field(
        ..., description="Total revenue in USD for the month."
    )
    total_profit_usd: float = Field(
        ..., description="Total profit in USD for the month."
    )
    total_harm_usd: float = Field(..., description="Total harm in USD for the month.")
