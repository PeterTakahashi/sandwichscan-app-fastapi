from pydantic import Field, ConfigDict

from app.v1.schemas.common.id_encoder import HasEncodedID
from app.v1.schemas.token.read import TokenRead


class SwapReadOnList(HasEncodedID):
    sell_token: TokenRead | None = Field(
        None, description="The token being sold in the swap."
    )
    buy_token: TokenRead | None = Field(
        None, description="The token being bought in the swap."
    )


    model_config = ConfigDict(from_attributes=True)
