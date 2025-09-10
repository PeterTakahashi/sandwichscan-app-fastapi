from datetime import datetime
from pydantic import Field, ConfigDict
from app.v1.schemas.common.id_encoder import HasEncodedID


class ChainRead(HasEncodedID):
    chain_id: int = Field(..., description="Chain ID.")
    name: str = Field(..., description="Chain name.")
    native_symbol: str = Field(..., description="Native currency symbol.")
    native_decimals: int = Field(..., description="Native currency decimals.")

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
