from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from web3 import Web3

from app.models.swap import Swap
from app.models.token import Token
from app.models.chain import Chain
from app.models.transaction import Transaction
from app.models.defi_pool import DefiPool
from app.models.wrapped_native_token import WrappedNativeToken
from app.lib.utils.uniswap_v3_price import price_base_per_stable, price1_per_0_from_sqrt_price_x96


async def _latest_swap_at_or_before(
    session: AsyncSession, *, pool_id: int, block_number: int
) -> Optional[tuple[Swap, int]]:
    stmt = (
        select(Swap, Transaction.block_number)
        .join(Transaction, Transaction.id == Swap.transaction_id)
        .where(and_(Swap.defi_pool_id == pool_id, Transaction.block_number <= block_number))
        .order_by(desc(Transaction.block_number), desc(Swap.log_index))
        .limit(1)
    )
    row = await session.execute(stmt)
    res = row.first()
    if not res:
        return None
    sw, blk = res[0], int(res[1])
    return sw, blk


# Minimal ABIs for on-chain reads
UNISWAP_V3_POOL_ABI = [
    {
        "name": "slot0",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
            {"name": "unlocked", "type": "bool"},
        ],
    }
]

UNISWAP_V2_PAIR_ABI = [
    {
        "name": "getReserves",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": "_reserve0", "type": "uint112"},
            {"name": "_reserve1", "type": "uint112"},
            {"name": "_blockTimestampLast", "type": "uint32"},
        ],
    },
    {
        "name": "token0",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "name": "token1",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
]


async def get_ethusd_from_uniswap_v3(
    session: AsyncSession, chain_id: int, block_number: int
) -> Optional[tuple[Decimal, int, int]]:
    # resolve wrapped + preferred v3 pool from DB
    wrow = await session.execute(
        select(WrappedNativeToken.token_id, WrappedNativeToken.usd_uniswap_v3_pool_id)
        .where(WrappedNativeToken.chain_id == chain_id)
        .limit(1)
    )
    w = wrow.first()
    if not w:
        return None
    wrapped_token_id, v3_pool_id = int(w[0]), (int(w[1]) if w[1] is not None else None)
    if v3_pool_id is None:
        return None

    v3_pool = await session.execute(
        select(DefiPool).where(DefiPool.id == v3_pool_id).limit(1)
    )
    v3_pool = v3_pool.scalar_one_or_none()
    if not v3_pool:
        return None
    if v3_pool.created_block_number > block_number:
        return None

    # 1) try from DB swaps (tick/sqrtPrice)
    res = await _latest_swap_at_or_before(session, pool_id=v3_pool_id, block_number=block_number)
    if res is not None:
        sw, priced_block_number = res
        prow = await session.execute(select(DefiPool).where(DefiPool.id == v3_pool_id))
        pool = prow.scalars().first()
        if pool is None:
            return None
        decs = await session.execute(select(Token.id, Token.decimals).where(Token.id.in_([pool.token0_id, pool.token1_id])))
        dec_map = {int(r[0]): int(r[1]) for r in decs.all()}
        base_is_token0 = (pool.token0_id == wrapped_token_id)
        price = price_base_per_stable(
            base_is_token0=base_is_token0,
            decimals0=dec_map.get(pool.token0_id, 18),
            decimals1=dec_map.get(pool.token1_id, 18),
            tick=int(sw.tick) if sw.tick is not None else None,
            sqrt_price_x96=int(sw.sqrt_price_x96) if sw.sqrt_price_x96 is not None else None,
        )
        if price is not None:
            return price, v3_pool_id, priced_block_number

    # 2) fallback to on-chain slot0 on the configured pool address

    rpc_row = await session.execute(select(Chain.rpc_url).where(Chain.id == chain_id))
    rpc_url = rpc_row.scalar_one_or_none()
    if not rpc_url:
        return None
    prow = await session.execute(select(DefiPool).where(DefiPool.id == v3_pool_id))
    pool = prow.scalars().first()
    if pool is None:
        return None
    # determine stable token id and decimals
    stable_token_id = pool.token1_id if pool.token0_id == wrapped_token_id else pool.token0_id
    sdec_row = await session.execute(select(Token.decimals).where(Token.id == stable_token_id))
    stable_decimals = int(sdec_row.scalar_one_or_none() or 6)
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    c = w3.eth.contract(address=Web3.to_checksum_address(pool.address), abi=UNISWAP_V3_POOL_ABI)
    try:
        slot0 = c.functions.slot0().call(block_identifier=block_number)
        sqrt_price_x96 = int(slot0[0])
    except Exception:
        return None
    wrapped_decimals = 18
    p1_per_0 = price1_per_0_from_sqrt_price_x96(sqrt_price_x96, wrapped_decimals, stable_decimals)
    # decide ordering by address
    waddr_row = await session.execute(select(Token.address).where(Token.id == wrapped_token_id))
    wadd = waddr_row.scalar_one()
    saddr_row = await session.execute(select(Token.address).where(Token.id == stable_token_id))
    sadd = saddr_row.scalar_one()
    if Web3.to_checksum_address(wadd) < Web3.to_checksum_address(sadd):
        eth_usd = p1_per_0
    else:
        eth_usd = Decimal(1) / p1_per_0 if p1_per_0 != 0 else None
    if eth_usd is None:
        return None
    return eth_usd, v3_pool_id, int(block_number)


async def get_ethusd_from_uniswap_v2(
    session: AsyncSession, chain_id: int, block_number: int
) -> Optional[tuple[Decimal, int, int]]:
    # resolve wrapped + preferred v2 pool from DB
    wrow = await session.execute(
        select(WrappedNativeToken.token_id, WrappedNativeToken.usd_uniswap_v2_pool_id)
        .where(WrappedNativeToken.chain_id == chain_id)
        .limit(1)
    )
    w = wrow.first()
    if not w:
        return None
    wrapped_token_id, v2_pool_id = int(w[0]), (int(w[1]) if w[1] is not None else None)
    if v2_pool_id is None:
        return None
    v2_pool = await session.execute(
        select(DefiPool).where(DefiPool.id == v2_pool_id).limit(1)
    )
    v2_pool = v2_pool.scalar_one_or_none()
    if not v2_pool:
        return None
    if v2_pool.created_block_number > block_number:
        return None

    rpc_row = await session.execute(select(Chain.rpc_url).where(Chain.id == chain_id))
    rpc_url = rpc_row.scalar_one_or_none()
    if not rpc_url:
        return None
    prow = await session.execute(select(DefiPool).where(DefiPool.id == v2_pool_id))
    pool = prow.scalars().first()
    if pool is None:
        return None
    # stable token decimals
    stable_token_id = pool.token1_id if pool.token0_id == wrapped_token_id else pool.token0_id
    sdec_row = await session.execute(select(Token.decimals).where(Token.id == stable_token_id))
    stable_decimals = int(sdec_row.scalar_one_or_none() or 6)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    pair = w3.eth.contract(address=Web3.to_checksum_address(pool.address), abi=UNISWAP_V2_PAIR_ABI)
    try:
        reserve0, reserve1, _ = pair.functions.getReserves().call(block_identifier=block_number)
        t0 = pair.functions.token0().call(block_identifier=block_number)
        t1 = pair.functions.token1().call(block_identifier=block_number)
    except Exception:
        return None
    wrapped_decimals = 18
    # pick wrapped address
    waddr_row = await session.execute(select(Token.address).where(Token.id == wrapped_token_id))
    wadd = waddr_row.scalar_one()
    if Web3.to_checksum_address(t0) == Web3.to_checksum_address(wadd):
        num = Decimal(reserve1) / (Decimal(10) ** stable_decimals)
        den = Decimal(reserve0) / (Decimal(10) ** wrapped_decimals)
    else:
        num = Decimal(reserve0) / (Decimal(10) ** stable_decimals)
        den = Decimal(reserve1) / (Decimal(10) ** wrapped_decimals)
    if den == 0:
        return None
    eth_usd = num / den
    return eth_usd, v2_pool_id, int(block_number)


async def get_ethusd_onchain(
    session: AsyncSession, chain_id: int, block_number: int
) -> Optional[tuple[Decimal, int, int]]:
    v3 = await get_ethusd_from_uniswap_v3(session, chain_id=chain_id, block_number=block_number)
    if v3 is not None:
        return v3
    return await get_ethusd_from_uniswap_v2(session, chain_id=chain_id, block_number=block_number)


WEI_PER_ETH = Decimal(10) ** 18


async def update_transaction_gas_price_usd(
    session: AsyncSession,
    transaction_id: int,
) -> bool:
    """
    Update a single transaction's gas_price_usd using on-chain ETHUSD at the tx block.

    Returns True if updated, False if skipped (e.g., missing gas_used/price or price not found).
    """
    # Fetch necessary fields
    row = await session.execute(
        select(
            Transaction.id,
            Transaction.chain_id,
            Transaction.block_number,
            Transaction.gas_used,
            Transaction.effective_gas_price_wei,
            Transaction.gas_price_wei,
        ).where(Transaction.id == transaction_id)
    )
    r = row.first()
    if not r:
        return False

    _tid, chain_id, block_number, gas_used, eff_price, legacy_price = r
    if gas_used is None:
        return False
    # Prefer effective price when available and > 0; else fall back to legacy gasPrice
    eff_val = int(eff_price) if eff_price is not None else 0
    leg_val = int(legacy_price) if legacy_price is not None else 0
    gas_price_wei = eff_val if eff_val > 0 else (leg_val if leg_val > 0 else None)
    if gas_price_wei is None:
        return False

    priced = await get_ethusd_onchain(session, chain_id=int(chain_id), block_number=int(block_number))
    if priced is None:
        return False
    eth_usd, _pool_id, _blk = priced

    gas_cost_usd = (Decimal(int(gas_used)) * Decimal(int(gas_price_wei)) / WEI_PER_ETH) * eth_usd

    from sqlalchemy import update

    stmt = (
        update(Transaction)
        .where(Transaction.id == transaction_id)
        .values(gas_price_usd=gas_cost_usd)
    )
    await session.execute(stmt)
    await session.flush()
    return True


async def update_swap_gas_price_usd(
    session: AsyncSession,
    swap_id: int,
) -> bool:
    """
    Update a single swap's transaction's gas_price_usd using on-chain ETHUSD at the tx block.

    Returns True if updated, False if skipped (e.g., missing gas_used/price or price not found).
    """
    # Fetch necessary fields
    swaps = await session.execute(
        select(
            Swap.id,
            Swap.transaction_id,
        )
        .where(Swap.id == swap_id)
    )
    swap = swaps.first()
    if not swap:
        return False
    return await update_transaction_gas_price_usd(session, transaction_id=int(swap.transaction_id))