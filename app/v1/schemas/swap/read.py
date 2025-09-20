from datetime import datetime
from pydantic import Field, ConfigDict

from app.v1.schemas.chain.read import ChainRead
from app.v1.schemas.common.id_encoder import HasEncodedID
from app.v1.schemas.defi_pool.token.read import TokenRead
from .transaction.read import TransactionRead


class SwapRead(HasEncodedID):
    log_index: int = Field(..., description="The log index of the swap event.")
    sender: str | None = Field(None, description="The address of the sender.")
    recipient: str | None = Field(None, description="The address of the recipient.")
    amount0_in_raw: int = Field(..., description="The raw amount of token0 input.")
    amount1_in_raw: int = Field(..., description="The raw amount of token1 input.")
    amount0_out_raw: int = Field(..., description="The raw amount of token0 output.")
    amount1_out_raw: int = Field(..., description="The raw amount of token1 output.")
    sqrt_price_x96: int | None = Field(
        None, description="The square root price in Q96 format."
    )
    # In the DB model this column is named `liquidity_raw` and may be NULL
    liquidity_raw: int | None = Field(
        None, description="The liquidity of the pool (raw units)."
    )
    tick: int | None = Field(None, description="The tick of the pool.")

    sell_token: TokenRead | None = Field(
        None, description="The token being sold in the swap."
    )
    buy_token: TokenRead | None = Field(
        None, description="The token being bought in the swap."
    )
    transaction: TransactionRead = Field(
        ..., description="The transaction associated with the swap."
    )
    chain: ChainRead = Field(..., description="The chain this swap belongs to.")

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
