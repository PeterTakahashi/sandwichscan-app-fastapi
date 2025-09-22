from datetime import datetime
from pydantic import Field, ConfigDict
from app.v1.schemas.common.id_encoder import HasEncodedID
from app.models.enums.token import TokenType
from app.v1.schemas.chain.read import ChainRead


class TokenRead(HasEncodedID):
    token_type: TokenType = Field(..., description="Type of the token (e.g., ERC20).")
    address: str = Field(..., description="Token contract address.")
    symbol: str = Field(..., description="Token symbol.")
    decimals: int = Field(..., description="Token decimals.")
    decimals_invalid: bool = Field(
        ..., description="Indicates if the token decimals are invalid."
    )
    logo_url: str | None = Field(None, description="URL of the token logo.")
    chain: ChainRead = Field(..., description="The chain this token belongs to.")

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
