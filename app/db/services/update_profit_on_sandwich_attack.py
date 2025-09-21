from __future__ import annotations
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session_maker
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

from typing import Optional
from decimal import Decimal, getcontext

from sqlalchemy import select

from app.models.swap import Swap
from app.models.chain import Chain
from app.lib.utils.bq_client import bq_client
from app.models.sandwich_attack import SandwichAttack
from app.repositories.sandwich_attack_repository import SandwichAttackRepository


getcontext().prec = 40  # 桁落ち回避

# Uniswap V2 Pair Sync event topic
TOPIC_SYNC_V2 = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"

UNIV2_USDC_WETH_POOL_BY_CHAIN = {
    1: "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc",  # Ethereum mainnet
    # 他チェーンが必要ならここに追加
}


async def _get_chain_dataset(session: AsyncSession, chain_id: int) -> Optional[str]:
    row = (
        await session.execute(
            select(Chain.big_query_table_id).where(Chain.id == chain_id)
        )
    ).first()
    return row[0] if row else None


async def _get_reserves_for_pool_before(
    session: AsyncSession,
    dataset: str,
    pool_address: str,
    block_number: int,
    tx_index: int,
    log_index: int,
    tx_hash: str,
) -> Optional[tuple[int, int]]:
    sql = r"""
DECLARE v_dataset    STRING;
DECLARE v_pool       STRING;
DECLARE v_blk        INT64;
DECLARE v_txi        INT64;
DECLARE v_logi       INT64;
DECLARE v_txh        STRING;
DECLARE v_topic_sync STRING;

SET v_dataset    = @dataset;
SET v_pool       = @pool;
SET v_blk        = @blk;
SET v_txi        = @txi;
SET v_logi       = @logi;
SET v_txh        = @txh;
SET v_topic_sync = @topic_sync;

EXECUTE IMMEDIATE (
  '''
    SELECT l.data
    FROM ''' || CONCAT(v_dataset, ".logs") || ''' AS l
    WHERE LOWER(l.address) = @pool
      AND l.topics[SAFE_OFFSET(0)] = @topic_sync
      AND (
        l.block_number < @blk
        OR (l.block_number = @blk AND l.transaction_index < @txi)
        OR (l.block_number = @blk AND l.transaction_index = @txi AND l.log_index < @logi)
      )
      AND NOT (l.block_number = @blk AND l.transaction_hash = @txh)
    ORDER BY l.block_number DESC, l.transaction_index DESC, l.log_index DESC
    LIMIT 1
  '''
)
USING v_pool AS pool, v_topic_sync AS topic_sync, v_blk AS blk, v_txi AS txi, v_logi AS logi, v_txh AS txh;
"""
    client = bq_client()
    job_config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("dataset", "STRING", dataset),
            ScalarQueryParameter("pool", "STRING", pool_address.lower()),
            ScalarQueryParameter("blk", "INT64", int(block_number)),
            ScalarQueryParameter("txi", "INT64", int(tx_index)),
            ScalarQueryParameter("logi", "INT64", int(log_index)),
            ScalarQueryParameter("txh", "STRING", tx_hash),
            ScalarQueryParameter("topic_sync", "STRING", TOPIC_SYNC_V2),
        ]
    )
    import asyncio as _asyncio

    try:
        job = await _asyncio.to_thread(lambda: client.query(sql, job_config=job_config))
    except Exception:
        return None
    it = iter(job)
    try:
        row = next(it)
    except StopIteration:
        return None
    data_hex = str(row["data"])
    if data_hex.startswith("0x"):
        data_hex = data_hex[2:]
    b = bytes.fromhex(data_hex)
    if len(b) < 64:
        return None
    r0 = int.from_bytes(b[0:32], "big")  # token0 reserve
    r1 = int.from_bytes(b[32:64], "big")  # token1 reserve
    return (r0, r1)


async def get_ethusd_from_univ2_sync_at_front(
    session: AsyncSession, chain_id: int, front: Swap
) -> Optional[Decimal]:
    # 前提: mainnet では USDC(token0,6) / WETH(token1,18) の v2 ペア
    pool_addr = UNIV2_USDC_WETH_POOL_BY_CHAIN.get(chain_id)
    if not pool_addr:
        return None
    dataset = await _get_chain_dataset(session, chain_id)
    if not dataset:
        return None
    r = await _get_reserves_for_pool_before(
        session,
        dataset=dataset,
        pool_address=pool_addr,
        block_number=front.transaction.block_number,
        tx_index=front.transaction.tx_index,
        log_index=front.log_index,
        tx_hash=front.transaction.tx_hash,
    )
    if not r:
        return None
    r0, r1 = r  # r0=USDC(6), r1=WETH(18)
    if r0 == 0 or r1 == 0:
        return None
    # ETHUSD ≒ (r0/1e6) / (r1/1e18) = r0 * 1e12 / r1
    return (Decimal(r0) * Decimal(10) ** 12) / Decimal(r1)


def gas_wei_to_base_raw(total_gas_wei: int, base_decimals: int, ethusd: Decimal) -> int:
    if total_gas_wei <= 0 or ethusd <= 0:
        return 0
    eth = Decimal(total_gas_wei) / Decimal(10) ** 18
    base = eth * ethusd * (Decimal(10) ** base_decimals)
    return int(base)  # 切り捨て

def fetch_revenue_base_raw(sandwich_attack: SandwichAttack) -> int:
    front = sandwich_attack.front_attack_swap
    back = sandwich_attack.back_attack_swap

    front_amount_in_raw = front.amount0_in_raw + front.amount1_in_raw
    back_amount_out_raw = back.amount0_out_raw + back.amount1_out_raw

    return max(back_amount_out_raw - front_amount_in_raw, 0)

CHAIN_ID = 1  # mainnet

async def update_harm_on_sandwich_attack(session: AsyncSession):
    sandwich_attack_repo = SandwichAttackRepository(session)

    sandwich_attacks = await sandwich_attack_repo.where(
        limit=9999999,
        chain_id=CHAIN_ID,
        joinedload_models=[
            (SandwichAttack.front_attack_swap, Swap.sell_token),
            (SandwichAttack.front_attack_swap, Swap.buy_token),
            (SandwichAttack.front_attack_swap, Swap.transaction),
            (SandwichAttack.back_attack_swap, Swap.sell_token),
            (SandwichAttack.back_attack_swap, Swap.buy_token),
            (SandwichAttack.back_attack_swap, Swap.transaction),
            (SandwichAttack.victim_swap, Swap.sell_token),
            (SandwichAttack.victim_swap, Swap.buy_token),
            (SandwichAttack.victim_swap, Swap.transaction),
            SandwichAttack.defi_pool,
            SandwichAttack.chain,
        ],
    )

    for sandwich_attack in sandwich_attacks:
        ethusd = await get_ethusd_from_univ2_sync_at_front(
            session,
            chain_id=sandwich_attack.chain.id,
            front=sandwich_attack.front_attack_swap,
        )
        if ethusd is None:
            # フォールバックできなければ profit= revenue とする or スキップ
            ethusd = Decimal(0)
        front_gas_wei = int(
            sandwich_attack.front_attack_swap.transaction.gas_used
        ) * int(sandwich_attack.front_attack_swap.transaction.effective_gas_price_wei)
        back_gas_wei = int(sandwich_attack.back_attack_swap.transaction.gas_used) * int(
            sandwich_attack.back_attack_swap.transaction.effective_gas_price_wei
        )
        total_gas_wei = front_gas_wei + back_gas_wei

        base_decimals = (
            sandwich_attack.front_attack_swap.sell_token.decimals
        )  # USDCなら6
        gas_base_raw = gas_wei_to_base_raw(total_gas_wei, base_decimals, ethusd)

        revenue_base_raw = fetch_revenue_base_raw(sandwich_attack)
        profit_base_raw = revenue_base_raw - gas_base_raw

        await sandwich_attack_repo.update(
            id=sandwich_attack.id,
            gas_fee_wei_attacker=total_gas_wei,
            profit_base_raw=profit_base_raw,
            gas_fee_base_raw=gas_base_raw,
            revenue_base_raw=revenue_base_raw,
        )
        print(
            f"id: {sandwich_attack.id}, revenue: {revenue_base_raw}, gas_fee: {gas_base_raw}, profit: {profit_base_raw}"
        )


async def _main():
    async with async_session_maker() as db_session:
        await update_harm_on_sandwich_attack(db_session)


if __name__ == "__main__":
    asyncio.run(_main())
