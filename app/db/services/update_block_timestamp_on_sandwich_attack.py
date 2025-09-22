import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.sandwich_attack_repository import SandwichAttackRepository
from app.models.swap import Swap
from app.models.sandwich_attack import SandwichAttack
from app.db.session import async_session_maker
from datetime import datetime

LIMIT = 999999999


async def update_block_timestamp_on_sandwich_attack(session: AsyncSession):
    sandwich_attack_repo = SandwichAttackRepository(session)

    sandwich_attacks = await sandwich_attack_repo.where(
        limit=LIMIT,
        joinedload_models=[
            (SandwichAttack.front_attack_swap, Swap.transaction),
        ],
    )

    for sa in sandwich_attacks:
        # block_timestamp(string) -> datetime型に変換
        block_timestamp = datetime.fromisoformat(
            sa.front_attack_swap.transaction.block_timestamp.replace("+00", "")
        )
        await sandwich_attack_repo.update(
            id=sa.id,
            block_timestamp=block_timestamp,
        )

    await session.commit()


async def _main():
    async with async_session_maker() as db_session:
        await update_block_timestamp_on_sandwich_attack(db_session)


if __name__ == "__main__":
    asyncio.run(_main())
