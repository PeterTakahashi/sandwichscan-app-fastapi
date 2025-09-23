from datetime import datetime
from pydantic import Field, ConfigDict

from app.v1.schemas.common.id_encoder import HasEncodedID
from app.v1.schemas.chain.read import ChainRead
from app.v1.schemas.sandwich_attack.swap.read_on_list import SwapReadOnList
from app.v1.schemas.defi_version.read import DefiVersionRead


class SandwichAttackReadOnList(HasEncodedID):
    chain: ChainRead = Field(..., description="The chain this pool belongs to.")
    front_attack_swap: SwapReadOnList = Field(
        ..., description="The front-running swap of the sandwich attack."
    )

    attacker_address: str = Field(..., description="The address of the attacker.")
    victim_address: str = Field(..., description="The address of the victim.")

    defi_version: DefiVersionRead = Field(
        ..., description="The DeFi version associated with the sandwich attack."
    )

    revenue_usd: float | None = Field(
        None, description="The revenue of the sandwich attack in USD."
    )
    cost_usd: float | None = Field(
        None, description="The cost of the sandwich attack in USD."
    )
    profit_usd: float | None = Field(
        None, description="The profit of the sandwich attack in USD."
    )
    harm_usd: float | None = Field(
        None, description="The harm caused to the victim in USD."
    )

    block_timestamp: datetime = Field(
        ...,
        description="The block timestamp of the sandwich attack (from the front-running swap).",
    )

    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record update timestamp.")

    model_config = ConfigDict(from_attributes=True)
