from pydantic import Field, field_serializer, ConfigDict
from app.lib.utils.convert_id import encode_id

from app.v1.schemas.common.id_encoder import HasEncodedID

IDField = Field(
    ...,
    json_schema_extra={"example": "abcd1234xyzc"},
    description="The ID of the object",
)


class DefiPoolRead(HasEncodedID):
    address: str = Field(..., description="The contract address of the DeFi protocol.")
    created_block_number: int = Field(
        ..., description="The block number when the DeFi protocol was created."
    )
    tick_spacing: int = Field(..., description="The tick spacing of the DeFi pool.")
    fee_tier_bps: int = Field(
        ..., description="The fee tier in basis points of the DeFi pool."
    )
    token0_id: int = Field(..., description="The ID of token0.")
    token1_id: int = Field(..., description="The ID of token1.")

    @field_serializer("token0_id")
    def serialize_token0_id(self, value: int) -> str:
        return encode_id(value)

    @field_serializer("token1_id")
    def serialize_token1_id(self, value: int) -> str:
        return encode_id(value)

    model_config = ConfigDict(from_attributes=True)
