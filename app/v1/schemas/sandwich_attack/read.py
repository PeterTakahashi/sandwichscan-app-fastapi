from datetime import datetime
from pydantic import Field, ConfigDict

from app.v1.schemas.common.id_encoder import HasEncodedID
from app.v1.schemas.chain.read import ChainRead
from app.v1.schemas.sandwich_attack.swap.read import SwapRead
from app.v1.schemas.token.read import TokenRead


class SandwichAttackRead(HasEncodedID):
    chain: ChainRead = Field(..., description="The chain this pool belongs to.")
    front_attack_swap: SwapRead = Field(
        ..., description="The front-running swap of the sandwich attack."
    )
    victim_swap: SwapRead = Field(
        ..., description="The victim swap of the sandwich attack."
    )
    back_attack_swap: SwapRead = Field(
        ..., description="The back-running swap of the sandwich attack."
    )

    attacker_address: str = Field(..., description="The address of the attacker.")
    victim_address: str | None = Field(None, description="The address of the victim.")

    base_token: TokenRead | None = Field(
        None, description="The base token of the sandwich attack."
    )

    revenue_base_raw: int = Field(
        ...,
        description="The revenue of the sandwich attack in base token (raw amount).",
    )
    gas_fee_wei_attacker: int = Field(
        ..., description="The gas fee paid by the attacker in wei."
    )
    profit_base_raw: int = Field(
        ..., description="The profit of the sandwich attack in base token (raw amount)."
    )
    harm_base_raw: int = Field(
        ..., description="The harm caused to the victim in base token (raw amount)."
    )

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
