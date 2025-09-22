from __future__ import annotations
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session_maker

from typing import Optional

from sqlalchemy import select

from app.models.swap import Swap
from app.models.defi_pool import DefiPool
from app.models.chain import Chain
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter
from app.lib.utils.bq_client import bq_client
from app.models.sandwich_attack import SandwichAttack
from app.repositories.sandwich_attack_repository import SandwichAttackRepository


# Uniswap V2 Pair Sync event topic
TOPIC_SYNC_V2 = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"


async def _get_reserves_before_a1_placeholder(
    session: AsyncSession,
    defi_pool_id: int,
    block_number: int,
    log_index: int,
    front_attack_swap: Swap,
) -> Optional[tuple[int, int]]:
    """Fetch reserves (r0,r1) just before a given swap (A1) for v2 pools.

    Strategy:
      - Query BigQuery logs for the latest UniswapV2 Pair Sync event for the pool
        strictly before (block_number, log_index).
      - Decode reserves from the event data and return as integers.

    Returns None when BigQuery is unavailable, dataset is missing, no prior Sync
    exists, or the pool is non‑v2 (no Sync events).
    """
    # Resolve pool address and chain dataset
    q = (
        select(DefiPool.address, Chain.big_query_table_id)
        .join(Chain, Chain.id == DefiPool.chain_id)
        .where(DefiPool.id == defi_pool_id)
    )
    row = (await session.execute(q)).first()
    if not row:
        return None
    pool_addr, dataset = row[0], row[1]
    if (
        not pool_addr
        or not dataset
        or not bq_client
        or not QueryJobConfig
        or not ScalarQueryParameter
    ):
        return None

    # Build BigQuery SQL to fetch the latest Sync before (block, log_index)
    sql = r"""
DECLARE v_dataset    STRING;
DECLARE v_pool       STRING;
DECLARE v_blk        INT64;
DECLARE v_txi        INT64;
DECLARE v_logi       INT64;
DECLARE v_txh        STRING;
DECLARE v_topic_sync STRING;

-- ここで“SET”してから使う
SET v_dataset    = @dataset;
SET v_pool       = @pool;
SET v_blk        = @blk;
SET v_txi        = @txi;
SET v_logi       = @logi;
SET v_txh        = @txh;
SET v_topic_sync = @topic_sync;

EXECUTE IMMEDIATE (
  '''
    SELECT
      l.data, l.block_number, l.transaction_index, l.log_index
    FROM ''' || CONCAT(v_dataset, ".logs") || ''' AS l
    WHERE LOWER(l.address) = @pool
      AND l.topics[SAFE_OFFSET(0)] = @topic_sync
      AND (
        l.block_number < @blk
        OR (l.block_number = @blk AND l.transaction_index < @txi)
        OR (l.block_number = @blk AND l.transaction_index = @txi AND l.log_index < @logi)
      )
      -- front と同一トランザクションの Sync を除外
      AND NOT (l.block_number = @blk AND l.transaction_hash = @txh)
    ORDER BY l.block_number DESC, l.transaction_index DESC, l.log_index DESC
    LIMIT 1
  '''
)
-- 動的SQL内の @pool/@blk/@txi/@logi/@txh/@topic_sync を “名前付き”でバインド
USING
  v_pool       AS pool,
  v_topic_sync AS topic_sync,
  v_blk        AS blk,
  v_txi        AS txi,
  v_logi       AS logi,
  v_txh        AS txh;
"""

    client = bq_client()
    job_config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("dataset", "STRING", str(dataset)),
            ScalarQueryParameter("pool", "STRING", str(pool_addr).lower()),
            ScalarQueryParameter("blk", "INT64", int(block_number)),
            ScalarQueryParameter(
                "txi", "INT64", int(front_attack_swap.transaction.tx_index)
            ),
            ScalarQueryParameter("logi", "INT64", int(log_index)),
            ScalarQueryParameter(
                "txh", "STRING", str(front_attack_swap.transaction.tx_hash)
            ),
            ScalarQueryParameter("topic_sync", "STRING", TOPIC_SYNC_V2),
        ]
    )

    def _run_query():
        return client.query(sql, job_config=job_config)

    # Run in thread to avoid blocking the event loop
    import asyncio as _asyncio

    try:
        job = await _asyncio.to_thread(_run_query)
    except Exception:
        return None

    row_it = iter(job)
    try:
        r = next(row_it)
    except StopIteration:
        return None

    data_hex = str(r["data"]) if "data" in r else str(r[0])
    if data_hex.startswith("0x"):
        data_hex = data_hex[2:]
    try:
        b = bytes.fromhex(data_hex)
    except ValueError:
        return None
    # V2 Sync: (uint112 reserve0, uint112 reserve1) left-padded to 32 bytes each
    if len(b) < 64:
        return None
    r0 = int.from_bytes(b[0:32], byteorder="big")
    r1 = int.from_bytes(b[32:64], byteorder="big")
    return (r0, r1)


async def _compute_harm_base_raw(
    session: AsyncSession,
    pool: DefiPool,
    front_attack_swap: Swap,
    victim_swap: Swap,
) -> int:
    """
    v2 の A1 直前リザーブ (r0,r1) を起点に victim の実入力を当てて
    「攻撃なし受取量 - 実受取量」を base(= front.sell_token) に換算して返す。
    base はステーブル想定。
    """
    # A1 直前のリザーブを取得（v2 Sync）
    reserves = await _get_reserves_before_a1_placeholder(
        session,
        defi_pool_id=pool.id,
        block_number=front_attack_swap.transaction.block_number,
        log_index=front_attack_swap.log_index,
        front_attack_swap=front_attack_swap,
    )
    if reserves is None:
        return 0

    r0, r1 = int(reserves[0]), int(reserves[1])

    # base は front の sell 側トークン（常に USD Stable 前提）
    base_is_token0: bool = front_attack_swap.sell_token_id == pool.token0_id

    print(f"r0: {r0}, r1: {r1}, base_is_token0: {base_is_token0}")

    # victim の入出力量（exact-in 前提）
    v0i = int(victim_swap.amount0_in_raw or 0)
    v1i = int(victim_swap.amount1_in_raw or 0)
    v0o = int(victim_swap.amount0_out_raw or 0)
    v1o = int(victim_swap.amount1_out_raw or 0)

    fee_num, fee_den = 3000, 1_000_000
    print(f"fee_num: {fee_num}, fee_den: {fee_den}")

    def swap_out_v2(r_in: int, r_out: int, x_in: int) -> int:
        # Uniswap v2: out = (x*(1-fee)*r_out) / (r_in + x*(1-fee))
        if x_in <= 0 or r_in <= 0 or r_out <= 0:
            return 0
        x_eff_num = x_in * (fee_den - fee_num)
        return (x_eff_num * r_out) // (r_in * fee_den + x_eff_num)

    def to_base_from_delta_out(delta_out: int, out_is_token0: bool) -> int:
        """小額差分はスポット比で base に換算"""
        if delta_out <= 0:
            return 0
        if base_is_token0:
            # base=token0（例: USDC=token0）
            if out_is_token0:
                return delta_out
            # token1 → token0
            return (delta_out * r0) // max(r1, 1)
        else:
            # base=token1（例: USDC=token1）
            if not out_is_token0:
                return delta_out
            # token0 → token1
            return (delta_out * r1) // max(r0, 1)

    harm_base_raw = 0

    # case A: token0 -> token1
    if base_is_token0:
        print("case A: token0 -> token1")
        out_noattack = swap_out_v2(r0, r1, v0i)
        print(f"out_noattack: {out_noattack}, v1o: {v1o}")
        harm_out_token1 = max(out_noattack - v1o, 0)
        harm_base_raw = to_base_from_delta_out(harm_out_token1, out_is_token0=False)

    # case B: token1 -> token0
    else:
        print("case B: token1 -> token0")
        out_noattack = swap_out_v2(r1, r0, v1i)
        harm_out_token0 = max(out_noattack - v0o, 0)
        print(
            f"out_noattack: {out_noattack}, v1i: {v1i}, v0o: {v0o}, harm_out_token0: {harm_out_token0}"
        )
        harm_base_raw = to_base_from_delta_out(harm_out_token0, out_is_token0=True)

    # 方向が判定不能（マルチホップや特殊ケース）は 0
    return int(harm_base_raw)


async def update_harm_on_sandwich_attack(session: AsyncSession):
    sandwich_attack_repo = SandwichAttackRepository(session)

    sandwich_attacks = await sandwich_attack_repo.where(
        limit=9999999,
        joinedload_models=[
            (SandwichAttack.front_attack_swap, Swap.sell_token),
            (SandwichAttack.front_attack_swap, Swap.buy_token),
            (SandwichAttack.front_attack_swap, Swap.transaction),
            SandwichAttack.victim_swap,
            SandwichAttack.defi_pool,
        ],
    )

    for sandwich_attack in sandwich_attacks:
        harm_base_raw = await _compute_harm_base_raw(
            session,
            pool=sandwich_attack.defi_pool,
            front_attack_swap=sandwich_attack.front_attack_swap,
            victim_swap=sandwich_attack.victim_swap,
        )
        print(f"harm_base_raw: {harm_base_raw}")
        print(
            f"usd price: {harm_base_raw / (10 ** sandwich_attack.front_attack_swap.buy_token.decimals)}"
        )
        await sandwich_attack_repo.update(
            id=sandwich_attack.id,
            harm_base_raw=harm_base_raw,
            harm_usd=harm_base_raw
            / (10**sandwich_attack.front_attack_swap.buy_token.decimals),
        )


async def _main():
    async with async_session_maker() as db_session:
        await update_harm_on_sandwich_attack(db_session)


if __name__ == "__main__":
    asyncio.run(_main())
