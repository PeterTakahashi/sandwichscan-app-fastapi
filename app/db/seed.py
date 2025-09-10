import asyncio
from typing import Sequence

from sqlalchemy import select

from app.db.session import async_session_maker
from app.models.chain import Chain

CHAINS: Sequence[dict] = (
    {"chain_id": 1, "name": "ethereum", "native_symbol": "ETH", "native_decimals": 18},
    {"chain_id": 10, "name": "optimism", "native_symbol": "ETH", "native_decimals": 18},
    {
        "chain_id": 137,
        "name": "polygon",
        "native_symbol": "MATIC",
        "native_decimals": 18,
    },
    {"chain_id": 250, "name": "fantom", "native_symbol": "FTM", "native_decimals": 18},
    {
        "chain_id": 42161,
        "name": "arbitrum",
        "native_symbol": "ETH",
        "native_decimals": 18,
    },
    {
        "chain_id": 43114,
        "name": "avalanche",
        "native_symbol": "AVAX",
        "native_decimals": 18,
    },
)


async def seed_chains() -> None:
    """Idempotently seed chain master data."""
    async with async_session_maker() as session:
        for data in CHAINS:
            result = await session.execute(
                select(Chain).where(Chain.chain_id == data["chain_id"])
            )
            chain = result.scalars().first()
            if not chain:
                chain = Chain(**data)
                session.add(chain)
                await session.commit()


async def main() -> None:
    await seed_chains()
    print("✅ Seeded chains (idempotent)")


if __name__ == "__main__":
    asyncio.run(main())
