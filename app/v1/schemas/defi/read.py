from datetime import datetime
from pydantic import Field, ConfigDict
from app.v1.schemas.common.id_encoder import HasEncodedID


class DefiRead(HasEncodedID):
    name: str = Field(..., description="The name of the DeFi protocol.")
    logo_url: str = Field(..., description="URL of the DeFi protocol logo.")

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
