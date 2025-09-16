from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
from typing import Optional

from sqlalchemy import select, and_, or_, desc, func

from app.db.session import async_session_maker
from app.models import Chain, Token, DefiPool, DefiFactory, DefiVersion, UsdStableCoin
from app.models.wrapped_native_token import WrappedNativeToken


async def resolve_chain_id(session, chain_name: str) -> Optional[int]:
    row = await session.execute(select(Chain.id).where(Chain.name == chain_name))
    return row.scalar_one_or_none()


async def resolve_token_id(session, chain_id: int, address: str) -> Optional[int]:
    addr = address.lower()
    # Compare in a case-insensitive manner: LOWER(tokens.address) = lower(input)
    row = await session.execute(
        select(Token.id).where(
            and_(Token.chain_id == chain_id, func.lower(Token.address) == addr)
        )
    )
    return row.scalar_one_or_none()


async def resolve_usd_stable_coin_id(session, chain_id: int, token_id: int) -> Optional[int]:
    row = await session.execute(
        select(UsdStableCoin.id).where(
            and_(UsdStableCoin.chain_id == chain_id, UsdStableCoin.token_id == token_id)
        )
    )
    return row.scalar_one_or_none()


async def resolve_uniswap_pool_id(
    session,
    *,
    chain_id: int,
    token_a_id: int,
    token_b_id: int,
    version_name: str,  # 'uniswap-v2' or 'uniswap-v3'
) -> Optional[int]:
    # pick most recently active pool matching tokens irrespective of order
    stmt = (
        select(DefiPool.id)
        .join(DefiFactory, DefiFactory.id == DefiPool.defi_factory_id)
        .join(DefiVersion, DefiVersion.id == DefiFactory.defi_version_id)
        .where(
            and_(
                DefiPool.chain_id == chain_id,
                DefiVersion.name == version_name,
                or_(
                    and_(DefiPool.token0_id == token_a_id, DefiPool.token1_id == token_b_id),
                    and_(DefiPool.token0_id == token_b_id, DefiPool.token1_id == token_a_id),
                ),
            )
        )
        .order_by(desc(DefiPool.is_active), desc(DefiPool.last_swap_block), desc(DefiPool.created_block_number))
        .limit(1)
    )
    row = await session.execute(stmt)
    return row.scalar_one_or_none()


async def upsert_wrapped_native_token(
    session,
    *,
    chain_id: int,
    wrapped_token_id: int,
    usd_stable_coin_id: Optional[int],
    v2_pool_id: Optional[int],
    v3_pool_id: Optional[int],
) -> None:
    existing_row = await session.execute(
        select(WrappedNativeToken).where(WrappedNativeToken.chain_id == chain_id)
    )
    entity = existing_row.scalars().first()
    if entity is None:
        entity = WrappedNativeToken(
            chain_id=chain_id,
            token_id=wrapped_token_id,
            usd_stable_coin_id=usd_stable_coin_id,
            usd_uniswap_v2_pool_id=v2_pool_id,
            usd_uniswap_v3_pool_id=v3_pool_id,
        )
        session.add(entity)
    else:
        entity.token_id = wrapped_token_id
        entity.usd_stable_coin_id = usd_stable_coin_id
        entity.usd_uniswap_v2_pool_id = v2_pool_id
        entity.usd_uniswap_v3_pool_id = v3_pool_id


async def run(csv_path: str) -> None:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    async with async_session_maker() as session:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                chain_name = row["chain_name"].strip()
                stable_addr = row["usd_stable_coin_address"].strip().lower()
                native_addr = row["native_token_address"].strip().lower()

                chain_id = await resolve_chain_id(session, chain_name)
                if chain_id is None:
                    print(f"[skip] chain not found: {chain_name}")
                    continue

                stable_token_id = await resolve_token_id(session, chain_id, stable_addr)
                if stable_token_id is None:
                    print(f"[skip] stable token not found: {chain_name} {stable_addr}")
                    continue
                wrapped_token_id = await resolve_token_id(session, chain_id, native_addr)
                if wrapped_token_id is None:
                    print(f"[skip] wrapped token not found: {chain_name} {native_addr}")
                    continue

                usd_sc_id = await resolve_usd_stable_coin_id(session, chain_id, stable_token_id)

                v3_pool_id = await resolve_uniswap_pool_id(
                    session,
                    chain_id=chain_id,
                    token_a_id=wrapped_token_id,
                    token_b_id=stable_token_id,
                    version_name="uniswap-v3",
                )
                v2_pool_id = await resolve_uniswap_pool_id(
                    session,
                    chain_id=chain_id,
                    token_a_id=wrapped_token_id,
                    token_b_id=stable_token_id,
                    version_name="uniswap-v2",
                )

                await upsert_wrapped_native_token(
                    session,
                    chain_id=chain_id,
                    wrapped_token_id=wrapped_token_id,
                    usd_stable_coin_id=usd_sc_id,
                    v2_pool_id=v2_pool_id,
                    v3_pool_id=v3_pool_id,
                )
                count += 1

            await session.commit()
            print(f"Upserted {count} wrapped_native_tokens from {csv_path}")


def main():
    ap = argparse.ArgumentParser(description="Create/Update wrapped_native_tokens from CSV")
    ap.add_argument(
        "--csv",
        default="app/db/data/wrapped_native_tokens.csv",
        help="Path to CSV file",
    )
    args = ap.parse_args()
    asyncio.run(run(args.csv))


if __name__ == "__main__":
    main()
