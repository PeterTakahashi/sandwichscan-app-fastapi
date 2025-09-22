import argparse
import asyncio
import signal
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from eth_abi import decode as abi_decode
from google.cloud.bigquery import (
    QueryJobConfig,
    ScalarQueryParameter,
    ArrayQueryParameter,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session_maker
from app.lib.utils.bq_client import bq_client
from app.models import Chain, DefiPool, Swap, Transaction

# ---------------- Tunables ---------------- #
WINDOW_BLOCKS = 100_000  # 1回のスキャン窓（--stepで変更可）
POOLS_BATCH = 5_000  # BigQueryに投げるプール数のバッチ
SWAP_UPSERT_BATCH = 1_000  # DB UPSERT バッチ（32767 params 対策）
BQ_RETRY_ATTEMPTS = 5
BQ_RETRY_BASE_DELAY = 0.5

# event signatures
TOPIC_SWAP_V2 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
TOPIC_SWAP_V3 = "0xc42079a4f72e13aa39cc39dce8d3bb0d7d2cc3f3eaa062b1c9d2e6f5d97d0e00"


# ---------------- Helpers ---------------- #
_shutdown = False


def _install_signal_handlers():
    def handler(signum, frame):
        global _shutdown
        _shutdown = True
        print(f"[signal] received {signum}, stopping after current window...")

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, handler)
        except Exception:
            pass


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def retry_async(
    fn,
    *,
    attempts: int = BQ_RETRY_ATTEMPTS,
    base_delay: float = BQ_RETRY_BASE_DELAY,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    label: str = "op",
):
    last: Optional[BaseException] = None
    for i in range(attempts):
        try:
            return await fn()
        except retry_on as e:
            last = e
            delay = base_delay * (2**i)
            print(
                f"[retry] {label} failed: {e}. retry in {delay:.2f}s ({i+1}/{attempts})"
            )
            await asyncio.sleep(delay)
    if last:
        raise last


# ---------------- BigQuery ---------------- #

BQ_SQL_SWAP_LOGS = r"""
DECLARE from_block INT64 DEFAULT @from_block;
DECLARE to_block   INT64 DEFAULT @to_block;

DECLARE dataset    STRING DEFAULT @dataset;
DECLARE logs_table STRING DEFAULT CONCAT(dataset, ".logs");

DECLARE pools ARRAY<STRING> DEFAULT @pools;

DECLARE topic_swap_v2 STRING DEFAULT @topic_swap_v2;
DECLARE topic_swap_v3 STRING DEFAULT @topic_swap_v3;

EXECUTE IMMEDIATE (
  '''
    SELECT
      LOWER(l.address)                 AS pool,          -- プールアドレス（小文字）
      l.transaction_hash               AS tx_hash,
      l.log_index                      AS log_index,
      l.block_number                   AS block_number,
      l.topics                         AS topics,
      l.data                           AS data,
      l.topics[SAFE_OFFSET(0)]         AS topic0
    FROM ''' || logs_table || ''' AS l
    WHERE ARRAY_LENGTH(l.topics) >= 1
      AND l.topics[SAFE_OFFSET(0)] IN (@topic_swap_v2, @topic_swap_v3)
      AND LOWER(l.address) IN (SELECT p FROM UNNEST(@pools) AS p)
      AND l.block_number BETWEEN @from_block AND @to_block
    ORDER BY l.block_number ASC, l.log_index ASC
  '''
)
USING
  from_block AS from_block,
  to_block   AS to_block,
  dataset    AS dataset,
  pools      AS pools,
  topic_swap_v2 AS topic_swap_v2,
  topic_swap_v3 AS topic_swap_v3;
"""


@dataclass
class SwapLogRow:
    pool: str
    tx_hash: str
    log_index: int
    block_number: int
    topic0: str
    topics: List[str]
    data: str


async def bq_fetch_swap_logs_for_pools(
    dataset: str,
    pools_lower: List[str],
    from_block: int,
    to_block: int,
) -> List[SwapLogRow]:
    if not pools_lower:
        return []
    client = bq_client()
    job_config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("from_block", "INT64", from_block),
            ScalarQueryParameter("to_block", "INT64", to_block),
            ScalarQueryParameter("dataset", "STRING", dataset),
            ArrayQueryParameter("pools", "STRING", pools_lower),
            ScalarQueryParameter("topic_swap_v2", "STRING", TOPIC_SWAP_V2),
            ScalarQueryParameter("topic_swap_v3", "STRING", TOPIC_SWAP_V3),
        ]
    )

    def _q():
        return client.query(BQ_SQL_SWAP_LOGS, job_config=job_config)

    t0 = time.time()
    job = await retry_async(lambda: asyncio.to_thread(_q), label="bq.swap_logs")
    rows: List[SwapLogRow] = []
    for r in job:
        rows.append(
            SwapLogRow(
                pool=str(r["pool"]),
                tx_hash=str(r["tx_hash"]),
                log_index=int(r["log_index"]),
                block_number=int(r["block_number"]),
                topic0=str(r["topic0"]),
                topics=list(r["topics"]),
                data=str(r["data"]),
            )
        )
    print(
        f"[BQ] swaps rows={len(rows)} for {from_block}-{to_block} in {time.time()-t0:.2f}s"
    )
    return rows


# ---------------- Decoders ---------------- #


def _strip_0x(s: str) -> str:
    return s[2:] if s.startswith("0x") else s


def _addr_from_topic(t: str) -> str:
    # topic の右40桁
    return "0x" + _strip_0x(t)[-40:]


@dataclass
class DecodedSwap:
    pool_addr_lower: str
    tx_hash: str
    log_index: int
    sender: Optional[str]
    recipient: Optional[str]
    amount0_in_raw: int
    amount1_in_raw: int
    amount0_out_raw: int
    amount1_out_raw: int
    sqrt_price_x96: Optional[int]
    liquidity_raw: Optional[int]
    tick: Optional[int]


def decode_swap_v2(row: SwapLogRow) -> DecodedSwap:
    # topics: [sig, sender, to]
    sender = _addr_from_topic(row.topics[1]) if len(row.topics) > 1 else None
    recipient = _addr_from_topic(row.topics[2]) if len(row.topics) > 2 else None
    # data: (uint256 amount0In, uint256 amount1In, uint256 amount0Out, uint256 amount1Out)
    a0in, a1in, a0out, a1out = abi_decode(
        ["uint256", "uint256", "uint256", "uint256"],
        bytes.fromhex(_strip_0x(row.data)),
    )
    return DecodedSwap(
        pool_addr_lower=row.pool,
        tx_hash=row.tx_hash,
        log_index=row.log_index,
        sender=sender,
        recipient=recipient,
        amount0_in_raw=int(a0in),
        amount1_in_raw=int(a1in),
        amount0_out_raw=int(a0out),
        amount1_out_raw=int(a1out),
        sqrt_price_x96=None,
        liquidity_raw=None,
        tick=None,
    )


def decode_swap_v3(row: SwapLogRow) -> DecodedSwap:
    # topics: [sig, sender, recipient]
    sender = _addr_from_topic(row.topics[1]) if len(row.topics) > 1 else None
    recipient = _addr_from_topic(row.topics[2]) if len(row.topics) > 2 else None
    # data: (int256 amount0, int256 amount1, uint160 sqrtPriceX96, uint128 liquidity, int24 tick)
    amount0, amount1, sqrt_price_x96, liquidity, tick = abi_decode(
        ["int256", "int256", "uint160", "uint128", "int24"],
        bytes.fromhex(_strip_0x(row.data)),
    )
    # v3: 正負で in/out を振り分け
    a0_in = int(amount0) if int(amount0) > 0 else 0
    a0_out = -int(amount0) if int(amount0) < 0 else 0
    a1_in = int(amount1) if int(amount1) > 0 else 0
    a1_out = -int(amount1) if int(amount1) < 0 else 0

    return DecodedSwap(
        pool_addr_lower=row.pool,
        tx_hash=row.tx_hash,
        log_index=row.log_index,
        sender=sender,
        recipient=recipient,
        amount0_in_raw=a0_in,
        amount1_in_raw=a1_in,
        amount0_out_raw=a0_out,
        amount1_out_raw=a1_out,
        sqrt_price_x96=int(sqrt_price_x96),
        liquidity_raw=int(liquidity),
        tick=int(tick),
    )


# ---------------- DB helpers ---------------- #


async def _map_tx_hashes_to_ids(
    session, chain_id_db: int, tx_hashes: Iterable[str]
) -> Dict[str, int]:
    hs = list(set(tx_hashes))
    out: Dict[str, int] = {}
    for batch in chunked(hs, 10_000):  # IN句上限ケア
        rows = (
            await session.execute(
                select(Transaction.id, Transaction.tx_hash).where(
                    Transaction.chain_id == chain_id_db,
                    Transaction.tx_hash.in_(batch),
                )
            )
        ).all()
        out.update({h: tid for (tid, h) in rows})
    return out


# ---------------- UPSERT ---------------- #


def _decide_sell_buy(
    t0_id: Optional[int],
    t1_id: Optional[int],
    a0_in: int,
    a1_in: int,
    a0_out: int,
    a1_out: int,
) -> Tuple[Optional[int], Optional[int]]:
    sell_id = None
    buy_id = None
    # 「in 側 = 売り」「out 側 = 買い」
    if a0_in > 0:
        sell_id = t0_id
    if a1_in > 0:
        sell_id = t1_id if t1_id is not None else sell_id
    if a0_out > 0:
        buy_id = t0_id
    if a1_out > 0:
        buy_id = t1_id if t1_id is not None else buy_id
    return sell_id, buy_id


async def upsert_swaps(
    session,
    chain_id_db: int,
    pool_addr_to_id_lower: Dict[str, int],
    pool_tokens: Dict[int, Tuple[Optional[int], Optional[int]]],
    decoded: List[DecodedSwap],
) -> int:
    if not decoded:
        return 0

    # 1) tx_hash -> transaction_id 解決
    tx_map = await _map_tx_hashes_to_ids(
        session, chain_id_db, (d.tx_hash for d in decoded)
    )

    # 2) payload 構築
    payload: List[Dict[str, Any]] = []
    skipped = 0
    for d in decoded:
        tx_id = tx_map.get(d.tx_hash)
        pool_id = pool_addr_to_id_lower.get(d.pool_addr_lower)
        if not tx_id or not pool_id:
            skipped += 1
            continue
        t0_id, t1_id = pool_tokens.get(pool_id, (None, None))
        sell_id, buy_id = _decide_sell_buy(
            t0_id,
            t1_id,
            int(d.amount0_in_raw or 0),
            int(d.amount1_in_raw or 0),
            int(d.amount0_out_raw or 0),
            int(d.amount1_out_raw or 0),
        )

        payload.append(
            dict(
                chain_id=chain_id_db,
                defi_pool_id=pool_id,
                transaction_id=tx_id,
                log_index=d.log_index,
                sender=d.sender,
                recipient=d.recipient,
                amount0_in_raw=d.amount0_in_raw,
                amount1_in_raw=d.amount1_in_raw,
                amount0_out_raw=d.amount0_out_raw,
                amount1_out_raw=d.amount1_out_raw,
                sqrt_price_x96=d.sqrt_price_x96,
                liquidity_raw=d.liquidity_raw,
                tick=d.tick,
                sell_token_id=sell_id,
                buy_token_id=buy_id,
            )
        )

    if skipped:
        print(f"[DB] swaps skip(no tx_id or pool_id)={skipped}")

    total = 0
    for chunk in chunked(payload, SWAP_UPSERT_BATCH):
        stmt = (
            pg_insert(Swap)
            .values(chunk)
            .on_conflict_do_update(
                constraint="uq_swaps_tx_log_index",
                set_={
                    "chain_id": pg_insert(Swap).excluded.chain_id,
                    "defi_pool_id": pg_insert(Swap).excluded.defi_pool_id,
                    "sender": pg_insert(Swap).excluded.sender,
                    "recipient": pg_insert(Swap).excluded.recipient,
                    "amount0_in_raw": pg_insert(Swap).excluded.amount0_in_raw,
                    "amount1_in_raw": pg_insert(Swap).excluded.amount1_in_raw,
                    "amount0_out_raw": pg_insert(Swap).excluded.amount0_out_raw,
                    "amount1_out_raw": pg_insert(Swap).excluded.amount1_out_raw,
                    "sqrt_price_x96": pg_insert(Swap).excluded.sqrt_price_x96,
                    "liquidity_raw": pg_insert(Swap).excluded.liquidity_raw,
                    "tick": pg_insert(Swap).excluded.tick,
                    "sell_token_id": pg_insert(Swap).excluded.sell_token_id,
                    "buy_token_id": pg_insert(Swap).excluded.buy_token_id,
                },
            )
        )
        await session.execute(stmt.execution_options(synchronize_session=False))
        total += len(chunk)
    await session.commit()
    return total


# ---------------- Orchestrator ---------------- #


async def backfill_swaps_uniswap(
    *,
    only_chain: Optional[str] = None,
    window_blocks: int = WINDOW_BLOCKS,
):
    _install_signal_handlers()
    t_all = time.time()

    async with async_session_maker() as session:
        # チェーンごと
        cq = select(
            Chain.id, Chain.name, Chain.last_block_number, Chain.big_query_table_id
        )
        if only_chain:
            cq = cq.where(Chain.name == only_chain)
        chains = (await session.execute(cq)).all()

        for chain_id_db, chain_name, chain_last, dataset in chains:
            if _shutdown:
                break
            if not dataset:
                print(f"[{chain_name}] big_query_table_id is empty, skip")
                continue
            if not chain_last or int(chain_last) <= 0:
                print(f"[{chain_name}] no last_block_number, skip")
                continue

            # active pool を取得
            pq = select(
                DefiPool.id, DefiPool.address, DefiPool.token0_id, DefiPool.token1_id
            ).where(
                DefiPool.chain_id == chain_id_db,
                DefiPool.is_active.is_(True),
            )
            pools = (await session.execute(pq)).all()
            if not pools:
                print(f"[{chain_name}] no active pools, skip")
                continue

            pool_addr_to_id_lower: Dict[str, int] = {
                addr.lower(): pid for (pid, addr, _t0, _t1) in pools
            }
            pool_tokens: Dict[int, Tuple[Optional[int], Optional[int]]] = {
                pid: (t0, t1) for (pid, _addr, t0, t1) in pools
            }
            pools_lower = list(pool_addr_to_id_lower.keys())

            # スキャン範囲：もっとも古いcreated_block〜latest
            cb_rows = (
                (
                    await session.execute(
                        select(DefiPool.created_block_number).where(
                            DefiPool.chain_id == chain_id_db,
                            DefiPool.is_active.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )
            start_blk = (
                int(min(cb for cb in cb_rows if cb is not None)) if cb_rows else 0
            )
            end_blk = int(chain_last)

            print(
                f"[{chain_name}] pools={len(pools_lower)} scan {start_blk}-{end_blk} step={window_blocks}"
            )

            win_from = start_blk
            while win_from <= end_blk and not _shutdown:
                win_to = min(win_from + window_blocks - 1, end_blk)
                print(f"[{chain_name}] window {win_from}-{win_to} ...")

                decoded_all: List[DecodedSwap] = []
                for batch in chunked(pools_lower, POOLS_BATCH):
                    try:
                        logs = await bq_fetch_swap_logs_for_pools(
                            dataset=dataset,
                            pools_lower=batch,
                            from_block=win_from,
                            to_block=win_to,
                        )
                        for row in logs:
                            try:
                                if row.topic0 == TOPIC_SWAP_V3:
                                    decoded_all.append(decode_swap_v3(row))
                                else:
                                    decoded_all.append(decode_swap_v2(row))
                            except Exception as e:
                                print(
                                    f"[{chain_name}] decode error: {e} @ tx {row.tx_hash} log_index {row.log_index}"
                                )
                    except Exception as e:
                        print(
                            f"[{chain_name}] window {win_from}-{win_to} pools_batch({len(batch)}) ERROR: {e} (skip batch)"
                        )

                # DB upsert
                n = await upsert_swaps(
                    session,
                    chain_id_db,
                    pool_addr_to_id_lower,
                    pool_tokens,
                    decoded_all,
                )
                print(f"[{chain_name}] window {win_from}-{win_to} swaps_upserted={n}")

                win_from = win_to + 1

    print(f"[DONE] swaps backfill total_elapsed={time.time()-t_all:.2f}s")


# ---------------- CLI ---------------- #
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Backfill Uniswap swaps from BigQuery")
    p.add_argument(
        "--chain",
        dest="only_chain",
        type=str,
        default=None,
        help="Chain.name filter (e.g. Ethereum)",
    )
    p.add_argument(
        "--step",
        dest="window_blocks",
        type=int,
        default=WINDOW_BLOCKS,
        help="block window size",
    )
    args = p.parse_args()

    asyncio.run(
        backfill_swaps_uniswap(
            only_chain=args.only_chain,
            window_blocks=args.window_blocks,
        )
    )
