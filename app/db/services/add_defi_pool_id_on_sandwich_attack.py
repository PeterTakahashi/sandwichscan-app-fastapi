import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.sandwich_attack_repository import SandwichAttackRepository
from app.models.swap import Swap
from app.models.sandwich_attack import SandwichAttack
from app.db.session import async_session_maker


async def add_defi_pool_id_on_sandwich_attack(session: AsyncSession):
    sandwich_attack_repo = SandwichAttackRepository(session)

    sandwich_attacks = await sandwich_attack_repo.where(
        limit=13306,
        joinedload_models=[
            (SandwichAttack.front_attack_swap, Swap.defi_pool),
        ],
    )

    for sa in sandwich_attacks:
        await sandwich_attack_repo.update(
            id=sa.id, defi_pool_id=sa.front_attack_swap.defi_pool_id
        )

    await session.commit()


async def _main():
    async with async_session_maker() as db_session:
        await add_defi_pool_id_on_sandwich_attack(db_session)


if __name__ == "__main__":
    asyncio.run(_main())
