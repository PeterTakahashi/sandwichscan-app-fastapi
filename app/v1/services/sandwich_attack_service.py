from app.v1.schemas.sandwich_attack import (
    SandwichAttackRead,
    SandwichAttackListRead,
    SandwichAttackSearchParams,
    SandwichAttackReadByMonth,
)
from app.repositories.sandwich_attack_repository import SandwichAttackRepository

from app.v1.schemas.sandwich_attack.list_response_meta import (
    SandwichAttackListResponseMeta,
)
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
        total_count = await self.sandwich_attack_repository.count(
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        total_revenue_usd = await self.sandwich_attack_repository.sum(
            "revenue_usd",
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        total_profit_usd = await self.sandwich_attack_repository.sum(
            "profit_usd",
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        total_harm_usd = await self.sandwich_attack_repository.sum(
            "harm_usd",
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )
        return SandwichAttackListRead(
            meta=SandwichAttackListResponseMeta(
                total_count=total_count,
                total_revenue_usd=total_revenue_usd,
                total_profit_usd=total_profit_usd,
                total_harm_usd=total_harm_usd,
                **search_params.model_dump(exclude_none=True),
            ),
            data=[SandwichAttackRead.model_validate(tx) for tx in sandwich_attacks],
        )

    async def get_read_by_month(
        self, search_params: SandwichAttackSearchParams
    ) -> list[SandwichAttackReadByMonth]:
        """
        Retrieve a list of sandwich_attacks aggregated by month with filtering.
        """
        results = await self.sandwich_attack_repository.aggregate_by_month(
            **search_params.model_dump(
                exclude_none=True,
                exclude={"limit", "offset", "sorted_by", "sorted_order"},
            ),
        )

        return [
            SandwichAttackReadByMonth(
                month=result.month,
                total_attacks=result.total_attacks,
                total_revenue_usd=result.total_revenue_usd,
                total_profit_usd=result.total_profit_usd,
                total_harm_usd=result.total_harm_usd,
            )
            for result in results
        ]
