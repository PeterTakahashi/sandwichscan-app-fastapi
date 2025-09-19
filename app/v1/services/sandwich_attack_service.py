from app.v1.schemas.sandwich_attack import (
    SandwichAttackRead,
    SandwichAttackListRead,
    SandwichAttackSearchParams,
)
from app.repositories.sandwich_attack_repository import SandwichAttackRepository

from app.v1.schemas.common.list.base_list_response import ListResponseMeta
from app.models.sandwich_attack import SandwichAttack
from app.models.swap import Swap
from app.models.defi_version import DefiVersion


class SandwichAttackService:
    def __init__(
        self,
        sandwich_attack_repository: SandwichAttackRepository,
    ):
        self.sandwich_attack_repository = sandwich_attack_repository

    async def get_list(
        self, search_params: SandwichAttackSearchParams
    ) -> SandwichAttackListRead:
        """
        Retrieve a list of sandwich_attacks with filtering, sorting, and pagination.
        """
        sandwich_attacks = await self.sandwich_attack_repository.where(
            **search_params.model_dump(exclude_none=True),
            joinedload_models=[
                SandwichAttack.chain,
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
        total_count = await self.sandwich_attack_repository.count(
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        return SandwichAttackListRead(
            meta=ListResponseMeta(
                total_count=total_count,
                **search_params.model_dump(exclude_none=True),
            ),
            data=[SandwichAttackRead.model_validate(tx) for tx in sandwich_attacks],
        )
