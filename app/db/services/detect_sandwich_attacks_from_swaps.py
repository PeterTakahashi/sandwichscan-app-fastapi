from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, asc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swap import Swap
from app.models.transaction import Transaction
from app.models.defi_pool import DefiPool
from app.models.defi_factory import DefiFactory
from app.models.defi_version import DefiVersion
from app.models.chain import Chain
from app.models.usd_stable_coin import UsdStableCoin
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter
from app.lib.utils.bq_client import bq_client
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.sandwich_attack import SandwichAttack

# from app.v1.services.sandwich_attack_service import (
#     create_sandwich_attack_if_pricable,
# )
from app.db.session import async_session_maker
import asyncio
from decimal import Decimal, getcontext

getcontext().prec = 60


# Uniswap V2 Pair Sync event topic
TOPIC_SYNC_V2 = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"

# Block scanning batch size for SQL windowing
BLOCK_BATCH = 100000


@dataclass
class SwapRow:
    id: int
    chain_id: int
    defi_pool_id: int
    sender: Optional[str]
    amount0_in_raw: int
    amount1_in_raw: int
    amount0_out_raw: int
    amount1_out_raw: int
    sell_token_id: Optional[int]
    buy_token_id: Optional[int]
    block_number: int
    log_index: int
    tx_from: Optional[str]
    gas_used: Optional[int]
    gas_price_wei_effective: Optional[int]
    gas_price_wei_legacy: Optional[int]


def _dir_token0_to_token1(s: SwapRow) -> bool:
    return (
        int(s.amount0_in_raw) > 0
        and int(s.amount1_out_raw) > 0
        and int(s.amount1_in_raw) == 0
        and int(s.amount0_out_raw) == 0
    )


def _dir_token1_to_token0(s: SwapRow) -> bool:
    return (
        int(s.amount1_in_raw) > 0
        and int(s.amount0_out_raw) > 0
        and int(s.amount0_in_raw) == 0
        and int(s.amount1_out_raw) == 0
    )


def _attacker_gas_fee_wei(
    front_attack_swap: SwapRow, back_attack_swap: SwapRow
) -> Optional[int]:
    def pick(p: Optional[int], q: Optional[int]) -> Optional[int]:
        return p if p is not None else q

    total = 0
    known = False
    for s in (front_attack_swap, back_attack_swap):
        if s.gas_used is not None:
            gp = pick(s.gas_price_wei_effective, s.gas_price_wei_legacy)
            if gp is not None:
                total += int(s.gas_used) * int(gp)
                known = True
    return total if known else None


def _get_amount_out(amount_in: int, reserve_in: int, reserve_out: int) -> int:
    FEE_NUM = 997
    FEE_DEN = 1000
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    amt_in_fee = amount_in * FEE_NUM
    num = amt_in_fee * reserve_out
    den = reserve_in * FEE_DEN + amt_in_fee
    return 0 if den == 0 else num // den


def _get_amount_out_with_fee(
    amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int
) -> int:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    fee_bps = int(fee_bps or 0)
    fee_den = 10_000
    fee_num = fee_den - fee_bps
    amt_in_fee = amount_in * fee_num
    num = amt_in_fee * reserve_out
    den = reserve_in * fee_den + amt_in_fee
    return 0 if den == 0 else num // den


async def _get_reserves_before_a1_placeholder(
    session: AsyncSession, *, defi_pool_id: int, block_number: int, log_index: int
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
DECLARE dataset    STRING DEFAULT @dataset;
DECLARE logs_table STRING DEFAULT CONCAT(dataset, ".logs");
DECLARE pool       STRING DEFAULT @pool;
DECLARE blk        INT64  DEFAULT @blk;
DECLARE logi       INT64  DEFAULT @logi;
DECLARE topic_sync STRING DEFAULT @topic_sync;

EXECUTE IMMEDIATE (
  '''
    SELECT
      l.data         AS data,
      l.block_number AS block_number,
      l.log_index    AS log_index
    FROM ''' || logs_table || ''' AS l
    WHERE LOWER(l.address) = @pool
      AND l.topics[SAFE_OFFSET(0)] = @topic_sync
      AND (
        l.block_number < @blk OR (l.block_number = @blk AND l.log_index < @logi)
      )
    ORDER BY l.block_number DESC, l.log_index DESC
    LIMIT 1
  '''
)
USING
  dataset    AS dataset,
  pool       AS pool,
  blk        AS blk,
  logi       AS logi,
  topic_sync AS topic_sync;
"""

    client = bq_client()
    job_config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("dataset", "STRING", str(dataset)),
            ScalarQueryParameter("pool", "STRING", str(pool_addr).lower()),
            ScalarQueryParameter("blk", "INT64", int(block_number)),
            ScalarQueryParameter("logi", "INT64", int(log_index)),
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
    front: SwapRow,
    victim: SwapRow,
) -> int:
    reserves = await _get_reserves_before_a1_placeholder(
        session,
        defi_pool_id=pool.id,
        block_number=front.block_number,
        log_index=front.log_index,
    )
    if reserves is None:
        return 0
    r0, r1 = reserves
    base_is_token0 = front.sell_token_id == pool.token0_id

    v_a0i = int(victim.amount0_in_raw)
    v_a1i = int(victim.amount1_in_raw)
    v_a0o = int(victim.amount0_out_raw)
    v_a1o = int(victim.amount1_out_raw)

    if v_a0i > 0 and v_a1o > 0 and v_a1i == 0 and v_a0o == 0:
        cf_token1 = _get_amount_out(v_a0i, int(r0), int(r1))
        delta_token1 = cf_token1 - v_a1o
        if base_is_token0:
            price0_per_1 = 0 if r1 == 0 else (Decimal(r0) / Decimal(r1))
            harm = int(
                (Decimal(delta_token1) * price0_per_1).to_integral_value(
                    rounding="ROUND_HALF_EVEN"
                )
            )
        else:
            harm = delta_token1
    elif v_a1i > 0 and v_a0o > 0 and v_a0i == 0 and v_a1o == 0:
        cf_token0 = _get_amount_out(v_a1i, int(r1), int(r0))
        delta_token0 = cf_token0 - v_a0o
        if base_is_token0:
            harm = delta_token0
        else:
            price0_per_1 = 0 if r1 == 0 else (Decimal(r0) / Decimal(r1))
            harm = (
                0
                if price0_per_1 == 0
                else int(
                    (Decimal(delta_token0) / price0_per_1).to_integral_value(
                        rounding="ROUND_HALF_EVEN"
                    )
                )
            )
    else:
        harm = 0
    return harm


async def detect_and_insert_for_pool(
    session: AsyncSession,
    defi_pool_id: int,
    stable_coin_token_id: int,
    max_block_gap: int = 2,
    min_block_number: Optional[int] = None,
    max_block_number: Optional[int] = None,
) -> int:
    # Use the SQL-based detector for performance
    return await detect_and_insert_for_pool_sql(
        session,
        defi_pool_id=defi_pool_id,
        stable_coin_token_id=stable_coin_token_id,
        max_block_gap=max_block_gap,
        min_block_number=min_block_number,
        max_block_number=max_block_number,
    )


async def detect_and_insert_for_pool_sql(
    session: AsyncSession,
    defi_pool_id: int,
    stable_coin_token_id: int,
    max_block_gap: int = 2,
    min_block_number: Optional[int] = None,
    max_block_number: Optional[int] = None,
) -> int:
    """
    Detect sandwich attacks within a single pool (front_attack -> victim -> back_attack).
    Returns number of detected rows (not inserting while testing).
    Conditions:
      - front_attack before victim, back_attack after victim, same attacker (EOA tx_from)
      - front/back are opposite directions relative to base (base = front_attack.sell_token_id)
      - victim lies between the two in block order, and block gap <= max_block_gap
      - victim base amount >= threshold
    Note: harm_base_raw is set to 0 for now (no reserve snapshots available).
    """
    # Ensure pool exists (and to get token0/token1 if we need later)
    pool_row = await session.execute(
        select(DefiPool).where(DefiPool.id == defi_pool_id)
    )
    pool = pool_row.scalars().first()
    if not pool:
        return 0

    # SQL template for candidate extraction
    from sqlalchemy import text

    sql = text(
        """
WITH s AS (
  SELECT
    s.id AS swap_id,
    s.defi_pool_id,
    t.block_number,
    s.log_index,
    LOWER(t.from_address) AS actor,
    s.sell_token_id, s.buy_token_id,
    s.amount0_in_raw, s.amount0_out_raw,
    s.amount1_in_raw, s.amount1_out_raw,
    CASE
      WHEN s.amount0_in_raw > 0 AND s.amount1_out_raw > 0 AND s.amount1_in_raw = 0 AND s.amount0_out_raw = 0 THEN -1
      WHEN s.amount1_in_raw > 0 AND s.amount0_out_raw > 0 AND s.amount0_in_raw = 0 AND s.amount1_out_raw = 0 THEN +1
      ELSE 0
    END AS dir_sign
  FROM swaps s
  JOIN transactions t ON t.id = s.transaction_id
  WHERE s.defi_pool_id = :pool_id
    AND t.chain_id = :chain_id
    AND t.block_number BETWEEN :min_block AND :max_block
    AND (
      (s.amount0_in_raw > 0 AND s.amount1_out_raw > 0 AND s.amount1_in_raw = 0 AND s.amount0_out_raw = 0) OR
      (s.amount1_in_raw > 0 AND s.amount0_out_raw > 0 AND s.amount0_in_raw = 0 AND s.amount1_out_raw = 0)
    )
),
pairs0 AS (
  SELECT
    s1.swap_id AS front_swap_id,
    s1.block_number AS front_block,
    s1.log_index AS front_log,
    s1.actor AS attacker_actor,
    s1.dir_sign AS dir_front,
    s1.sell_token_id AS front_sell_token_id,
    s1.buy_token_id  AS front_buy_token_id,
    s2.swap_id AS back_swap_id,
    s2.block_number AS back_block,
    s2.log_index AS back_log,
    ROW_NUMBER() OVER (PARTITION BY s1.swap_id ORDER BY s2.block_number, s2.log_index) AS rn
  FROM s s1
  JOIN s s2
    ON s2.defi_pool_id = s1.defi_pool_id
   AND s2.actor = s1.actor
   AND (s2.block_number > s1.block_number OR (s2.block_number = s1.block_number AND s2.log_index > s1.log_index))
   AND (s2.block_number - s1.block_number) <= :max_block_gap
   AND s2.dir_sign = -s1.dir_sign
   AND s1.sell_token_id = s2.buy_token_id
   AND s1.sell_token_id = :stable_coin_token_id
   AND s1.buy_token_id  = s2.sell_token_id
),
pairs AS (
  SELECT * FROM pairs0 WHERE rn = 1
),
victims AS (
  SELECT
    p.front_swap_id,
    p.back_swap_id,
    v.swap_id AS victim_swap_id,
    p.attacker_actor,
    v.actor AS victim_actor,
    p.front_block,
    v.block_number AS victim_block,
    p.back_block,
    p.dir_front,
    p.front_sell_token_id,
    p.front_buy_token_id
  FROM pairs p
  JOIN s v
    ON v.defi_pool_id = :pool_id
   AND (v.block_number > p.front_block OR (v.block_number = p.front_block AND v.log_index >= p.front_log))
   AND (v.block_number < p.back_block  OR (v.block_number = p.back_block  AND v.log_index <= p.back_log))
   AND v.actor <> p.attacker_actor
   AND v.dir_sign = p.dir_front
   AND v.sell_token_id = p.front_sell_token_id
   AND v.buy_token_id  = p.front_buy_token_id
)
SELECT * FROM victims
        """
    )

    async def _process_window(
        win_min: int, win_max: int, core_min: int, core_max: int
    ) -> int:
        rows = await session.execute(
            sql,
            {
                "pool_id": defi_pool_id,
                "stable_coin_token_id": stable_coin_token_id,
                "min_block": win_min,
                "max_block": win_max,
                "max_block_gap": max_block_gap,
                "chain_id": pool.chain_id,
            },
        )
        all_rows = rows.all()
        if not all_rows:
            return 0

        # Filter to keep only those with front_block within core window
        candidates = [r for r in all_rows if core_min <= int(r[5]) <= core_max]
        if not candidates:
            return 0

        # Load swaps for profit/gas
        swap_ids: set[int] = set()
        for r in candidates:
            swap_ids.update((int(r[0]), int(r[1]), int(r[2])))

        id_to_swap: dict[int, SwapRow] = {}
        ids_list = list(swap_ids)
        for i in range(0, len(ids_list), 1000):
            chunk = ids_list[i : i + 1000]
            stmt = (
                select(
                    Swap.id,
                    Swap.chain_id,
                    Swap.defi_pool_id,
                    Swap.sender,
                    Swap.amount0_in_raw,
                    Swap.amount1_in_raw,
                    Swap.amount0_out_raw,
                    Swap.amount1_out_raw,
                    Swap.sell_token_id,
                    Swap.buy_token_id,
                    Transaction.block_number,
                    Swap.log_index,
                    Transaction.from_address,
                    Transaction.gas_used,
                    Transaction.effective_gas_price_wei,
                    Transaction.gas_price_wei,
                )
                .join(Transaction, Transaction.id == Swap.transaction_id)
                .where(Swap.id.in_(chunk))
            )
            for r in (await session.execute(stmt)).all():
                id_to_swap[int(r[0])] = SwapRow(
                    id=int(r[0]),
                    chain_id=int(r[1]),
                    defi_pool_id=int(r[2]),
                    sender=r[3],
                    amount0_in_raw=int(r[4]),
                    amount1_in_raw=int(r[5]),
                    amount0_out_raw=int(r[6]),
                    amount1_out_raw=int(r[7]),
                    sell_token_id=int(r[8]) if r[8] is not None else None,
                    buy_token_id=int(r[9]) if r[9] is not None else None,
                    block_number=int(r[10]),
                    log_index=int(r[11]),
                    tx_from=r[12],
                    gas_used=int(r[13]) if r[13] is not None else None,
                    gas_price_wei_effective=int(r[14]) if r[14] is not None else None,
                    gas_price_wei_legacy=int(r[15]) if r[15] is not None else None,
                )

        rows_to_insert: list[dict] = []
        for r in candidates:
            front_id = int(r[0])
            back_id = int(r[1])
            victim_id = int(r[2])
            attacker_address = str(r[3])
            victim_address = str(r[4])
            front = id_to_swap.get(front_id)
            back = id_to_swap.get(back_id)
            victim = id_to_swap.get(victim_id)
            if not front or not back or not victim:
                continue

            base_token_id = front.sell_token_id
            if base_token_id is None:
                continue
            base_is_token0 = base_token_id == pool.token0_id

            # Matching method: pair only the quote amount that flows from front -> back
            if base_is_token0:
                base_in = Decimal(int(front.amount0_in_raw))
                base_out = Decimal(int(back.amount0_out_raw))
                q_front = Decimal(int(front.amount1_out_raw))
                q_back = Decimal(int(back.amount1_in_raw))
                if not (_dir_token0_to_token1(front) and _dir_token1_to_token0(back)):
                    continue
            else:
                base_in = Decimal(int(front.amount1_in_raw))
                base_out = Decimal(int(back.amount1_out_raw))
                q_front = Decimal(int(front.amount0_out_raw))
                q_back = Decimal(int(back.amount0_in_raw))
                if not (_dir_token1_to_token0(front) and _dir_token0_to_token1(back)):
                    continue

            if base_in <= 0 or base_out <= 0 or q_front <= 0 or q_back <= 0:
                continue

            r_back = base_out / q_back
            r_front = q_front / base_in
            pair_q = q_front if q_front <= q_back else q_back

            # Net trading P&L in base token for the matched portion
            base_out_matched = r_back * pair_q
            base_in_matched = (pair_q / r_front) if r_front != 0 else Decimal(0)
            pnl_trade_base = base_out_matched - base_in_matched
            revenue_base_raw = int(
                pnl_trade_base.to_integral_value(rounding="ROUND_FLOOR")
            )

            # Convert gas (wei) to base token raw (USD-stable) before subtracting
            gas_fee_wei_attacker = _attacker_gas_fee_wei(front, back) or 0
            harm_base_raw = await _compute_harm_base_raw(
                session, pool=pool, front=front, victim=victim
            )
            profit_base_raw = revenue_base_raw

            rows_to_insert.append(
                dict(
                    chain_id=front.chain_id,
                    front_attack_swap_id=front.id,
                    victim_swap_id=victim.id,
                    back_attack_swap_id=back.id,
                    attacker_address=attacker_address,
                    victim_address=victim_address,
                    base_token_id=base_token_id,
                    revenue_base_raw=int(revenue_base_raw),
                    gas_fee_wei_attacker=int(gas_fee_wei_attacker),
                    profit_base_raw=int(profit_base_raw),
                    harm_base_raw=int(harm_base_raw),
                )
            )

            # Bulk insert
        inserted = 0
        for i in range(0, len(rows_to_insert), 1000):
            chunk = rows_to_insert[i : i + 1000]
            if not chunk:
                continue
            stmt = (
                pg_insert(SandwichAttack)
                .values(chunk)
                .on_conflict_do_nothing(constraint="uq_sandwich_triplet")
            )
            res = await session.execute(stmt)
            inserted += int(res.rowcount or 0)
        return inserted

    # Iterate windows
    inserted = 0
    if min_block_number is not None and max_block_number is not None:
        cur = int(min_block_number)
        end = int(max_block_number)
        print(f"starting block scan for pool {defi_pool_id} from {cur} to {end}")
        while cur <= end:
            core_from = cur
            core_to = min(cur + BLOCK_BATCH - 1, end)
            # Expand window by max_block_gap on both ends to catch cross-window pairs
            win_min = max(core_from - max_block_gap, int(min_block_number))
            win_max = min(core_to + max_block_gap, end)
            inserted_in_window = await _process_window(
                win_min, win_max, core_from, core_to
            )
            if inserted_in_window:
                await session.commit()
            inserted += inserted_in_window
            print(
                f"Processed blocks {win_min}..{win_max}, core {core_from}..{core_to}, total {inserted} rows"
            )
            cur = core_to + 1
    else:
        # Fallback: single pass with broad range (if unspecified, use entire chain range may be large)
        # Use 0..INT_MAX sentinel; DB will naturally restrict by available rows
        import sys

        inserted += await _process_window(0, sys.maxsize, 0, sys.maxsize)

    return inserted


CHAIN_ID = 1  # Ethereum Mainnet


async def detect_and_insert_for_v2_pools(session: AsyncSession):
    # get all v2 pools on the chain
    usd_stable_coin_query = select(UsdStableCoin.token_id).where(
        UsdStableCoin.chain_id == CHAIN_ID
    )
    usd_stable_coin_rows = (await session.execute(usd_stable_coin_query)).all()
    usd_stable_coin_ids = [row[0] for row in usd_stable_coin_rows]
    for usd_stable_coin_token_id in usd_stable_coin_ids:
        print(
            f"Found USD stable coin token ID {usd_stable_coin_token_id} on chain {CHAIN_ID}"
        )
        q = (
            select(DefiPool)
            .join(DefiFactory, DefiFactory.id == DefiPool.defi_factory_id)
            .join(DefiVersion, DefiVersion.id == DefiFactory.defi_version_id)
            .where(DefiPool.is_active.is_(True))
            .where(DefiPool.chain_id == CHAIN_ID)
            .where(DefiVersion.name == "uniswap-v2")
            .where(
                or_(
                    DefiPool.token0_id == usd_stable_coin_token_id,
                    DefiPool.token1_id == usd_stable_coin_token_id,
                )
            )
            .order_by(asc(DefiPool.id))
        )
        pools = (await session.execute(q)).all()
        print(f"Found {len(pools)} v2 pools on chain {CHAIN_ID}")

        # Prepare lightweight pool info to avoid holding ORM instances across tasks
        pool_infos = [
            {
                "id": p[0].id,
                "created_block_number": p[0].created_block_number,
                "last_swap_block": p[0].last_swap_block,
            }
            for p in pools
        ]

        # Limit concurrent sessions/tasks to avoid DB/BQ overload
        MAX_CONCURRENCY = 2
        sem = asyncio.Semaphore(MAX_CONCURRENCY)

        async def run_pool(info: dict) -> int:
            async with sem:
                async with async_session_maker() as task_sess:
                    cnt = await detect_and_insert_for_pool(
                        task_sess,
                        defi_pool_id=info["id"],
                        stable_coin_token_id=usd_stable_coin_token_id,
                        min_block_number=info["created_block_number"],
                        max_block_number=info["last_swap_block"],
                    )
                    # Each inner call handles its own commits; nothing to commit here
                print(f"Pool {info['id']}: inserted {cnt} rows")
                return cnt

        results = await asyncio.gather(*(run_pool(info) for info in pool_infos))
        inserted = sum(int(x or 0) for x in results)
        return inserted


async def _main_async() -> int:
    async with async_session_maker() as session:
        inserted = await detect_and_insert_for_v2_pools(session)
        return inserted


def main():
    detected = asyncio.run(_main_async())
    print(f"Detected {detected} sandwich attacks")


if __name__ == "__main__":
    main()
