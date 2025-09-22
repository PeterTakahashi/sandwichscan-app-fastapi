from datetime import datetime
from pydantic import Field, ConfigDict

from app.v1.schemas.common.id_encoder import HasEncodedID
from app.v1.schemas.chain.read import ChainRead
from app.v1.schemas.defi_pool.token.read import TokenRead
from app.v1.schemas.defi_factory.read import DefiFactoryRead


class DefiPoolRead(HasEncodedID):
    address: str = Field(..., description="The contract address of the DeFi protocol.")
    created_block_number: int = Field(
        ..., description="The block number when the DeFi protocol was created."
    )
    tick_spacing: int = Field(..., description="The tick spacing of the DeFi pool.")
    fee_tier_bps: int = Field(
        ..., description="The fee tier in basis points of the DeFi pool."
    )
    chain: ChainRead = Field(..., description="The chain this pool belongs to.")
    defi_factory: DefiFactoryRead = Field(
        ..., description="The factory this pool belongs to."
    )
    token0: TokenRead = Field(..., description="The first token of the pool.")
    token1: TokenRead = Field(..., description="The second token of the pool.")

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
