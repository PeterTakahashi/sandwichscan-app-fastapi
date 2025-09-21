import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.sandwich_attack_repository import SandwichAttackRepository
from app.models.swap import Swap
from app.models.sandwich_attack import SandwichAttack
from app.db.session import async_session_maker

LIMIT = 13306


async def update_usd_on_sandwich_attack(session: AsyncSession):
    sandwich_attack_repo = SandwichAttackRepository(session)

    sandwich_attacks = await sandwich_attack_repo.where(
        limit=LIMIT,
        joinedload_models=[
            (SandwichAttack.front_attack_swap, Swap.sell_token),
            (SandwichAttack.front_attack_swap, Swap.buy_token),
        ],
    )

    for sa in sandwich_attacks:
        decimals = sa.front_attack_swap.sell_token.decimals
        await sandwich_attack_repo.update(
            id=sa.id,
            revenue_usd=sa.revenue_base_raw / (10**decimals),
            cost_usd=sa.gas_fee_base_raw / (10**decimals),
            profit_usd=(sa.profit_base_raw) / (10**decimals),
            harm_usd=(sa.harm_base_raw) / (10**decimals),
        )

    await session.commit()


async def _main():
    async with async_session_maker() as db_session:
        await update_usd_on_sandwich_attack(db_session)


if __name__ == "__main__":
    asyncio.run(_main())
