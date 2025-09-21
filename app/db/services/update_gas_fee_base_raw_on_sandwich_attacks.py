import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.sandwich_attack_repository import SandwichAttackRepository
from app.models.swap import Swap
from app.models.sandwich_attack import SandwichAttack
from app.db.session import async_session_maker

LIMIT = 13306


async def update_gas_fee_base_raw_on_sandwich_attacks(session: AsyncSession):
    sandwich_attack_repo = SandwichAttackRepository(session)

    with open("app/db/data/gas_fee_base_raw_by_sandwich_attack.csv", "r") as f:
        lines = f.readlines()
        for line in lines[1:]:
            cols = line.strip().split(",")
            sandwich_attack_id = int(cols[0])
            gas_fee_base_raw = int(cols[2])
            sandwich_attack = await sandwich_attack_repo.find(
                id=sandwich_attack_id,
                joinedload_models=[
                    (SandwichAttack.front_attack_swap, Swap.sell_token),
                ],
            )
            await sandwich_attack_repo.update(
                id=sandwich_attack.id,
                gas_fee_base_raw=gas_fee_base_raw,
            )
            print(
                f"id: {sandwich_attack.id}, gas_fee_base_raw: {gas_fee_base_raw}, usd: {gas_fee_base_raw / (10 ** sandwich_attack.front_attack_swap.sell_token.decimals)}"
            )

    await session.commit()


async def _main():
    async with async_session_maker() as db_session:
        await update_gas_fee_base_raw_on_sandwich_attacks(db_session)


if __name__ == "__main__":
    asyncio.run(_main())
