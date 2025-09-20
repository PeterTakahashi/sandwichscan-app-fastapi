from fastapi import Depends
from app.models.sandwich_attack import SandwichAttack
from app.repositories.sandwich_attack_repository import SandwichAttackRepository
from app.lib.utils.convert_id import decode_id
from app.dependencies.repositories.sandwich_attack_repository import (
    get_sandwich_attack_repository,
)
from app.models.swap import Swap
from app.models.defi_version import DefiVersion


async def get_sandwich_attack_by_id(
    sandwich_attack_id: str,
    sandwich_attack_repository: SandwichAttackRepository = Depends(
        get_sandwich_attack_repository
    ),
) -> SandwichAttack:
    sandwich_attack = await sandwich_attack_repository.find_by_or_raise(
        id=decode_id(sandwich_attack_id),
        joinedload_models=[
            SandwichAttack.chain,
            SandwichAttack.defi_pool,
            (SandwichAttack.front_attack_swap, Swap.sell_token),
            (SandwichAttack.front_attack_swap, Swap.buy_token),
            (SandwichAttack.front_attack_swap, Swap.transaction),
            (SandwichAttack.victim_swap, Swap.sell_token),
            (SandwichAttack.victim_swap, Swap.buy_token),
            (SandwichAttack.victim_swap, Swap.transaction),
            (SandwichAttack.back_attack_swap, Swap.sell_token),
            (SandwichAttack.back_attack_swap, Swap.buy_token),
            (SandwichAttack.back_attack_swap, Swap.transaction),
            SandwichAttack.base_token,
            (SandwichAttack.defi_version, DefiVersion.defi),
        ],  # Eager load relationships
    )
    return sandwich_attack
