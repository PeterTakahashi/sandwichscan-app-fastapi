from datetime import datetime
from pydantic import Field, ConfigDict
from app.v1.schemas.common.id_encoder import HasEncodedID
from app.v1.schemas.chain.read import ChainRead
from app.v1.schemas.defi_version.read import DefiVersionRead

class DefiFactoryRead(HasEncodedID):
    address: str = Field(..., description="The contract address of the DeFi factory.")
    created_block_number: int = Field(..., description="The block number when the DeFi factory was created.")

    chain: ChainRead = Field(..., description="The chain this DeFi factory belongs to.")
    defi_version: DefiVersionRead = Field(..., description="The DeFi version this factory is associated with.")

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
