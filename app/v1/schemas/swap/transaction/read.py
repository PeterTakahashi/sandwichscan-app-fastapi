from datetime import datetime
from pydantic import Field, ConfigDict, field_validator

from app.v1.schemas.common.id_encoder import HasEncodedID


class TransactionRead(HasEncodedID):
    block_number: int = Field(..., description="The block number of the transaction.")
    block_timestamp: datetime = Field(
        ..., description="The timestamp of the block containing the transaction."
    )
    tx_hash: str = Field(..., description="The hash of the transaction.")
    tx_index: int = Field(..., description="The index of the transaction in the block.")

    from_address: str = Field(..., description="The address of the sender.")
    to_address: str | None = Field(None, description="The address of the recipient.")

    gas_used: int | None = Field(
        None, description="The amount of gas used by the transaction."
    )
    gas_price_wei: int | None = Field(
        None, description="The gas price of the transaction in wei."
    )
    effective_gas_price_wei: int | None = Field(
        None, description="The effective gas price of the transaction in wei."
    )
    value_wei: int = Field(..., description="The value of the transaction in wei.")

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("block_timestamp", mode="before")
    @classmethod
    def _normalize_block_timestamp(cls, v):
        # The DB stores an ISO-like string e.g. "YYYY-MM-DD HH:MM:SS+00".
        # Normalize to a form datetime.fromisoformat can parse.
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            s = v.strip()
            # Convert trailing "+00" to "+00:00" for ISO compliance
            if s.endswith("+00"):
                s = s + ":00"
            try:
                return datetime.fromisoformat(s)
            except Exception:
                # As a fallback, return the original string to let Pydantic re-attempt
                # or raise a clearer error later if truly invalid.
                return s
        return v
