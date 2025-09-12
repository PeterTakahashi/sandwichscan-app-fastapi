from datetime import datetime
from pydantic import Field, ConfigDict
from app.v1.schemas.common.id_encoder import HasEncodedID
from app.v1.schemas.defi.read import DefiRead

class DefiVersionRead(HasEncodedID):
    name: str = Field(..., description="The name of the DeFi protocol.")
    defi: DefiRead = Field(..., description="The DeFi protocol this version belongs to.")

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
