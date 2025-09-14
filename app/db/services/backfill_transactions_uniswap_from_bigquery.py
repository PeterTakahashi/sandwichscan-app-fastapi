import asyncio
import time
import signal
from dataclasses import dataclass
from typing import List, Optional, Tuple, Type

from google.cloud.bigquery import (
    QueryJobConfig,
    ScalarQueryParameter,
    ArrayQueryParameter,
)
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session_maker
from app.lib.utils.bq_client import bq_client
from app.models import Chain, DefiFactory, Transaction, DefiVersion, DefiPool

# ---------------------------------------
# Tunables
# ---------------------------------------
WINDOW_BLOCKS = 100_000  # 1回のスキャン窓
TX_UPSERT_BATCH = 2_500  # DB UPSERT バッチ
BQ_RETRY_ATTEMPTS = 5
BQ_RETRY_BASE_DELAY = 0.5
POOLS_BATCH = 5_000

# ---------------------------------------
# Helpers
# ---------------------------------------
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


@dataclass
class TxRow:
    block_number: int
    block_timestamp: str
    tx_index: int
    tx_hash: str
    from_address: str
    to_address: Optional[str]
    value_wei: int
    gas_used: Optional[int]
    gas_price_wei: Optional[int]
    effective_gas_price_wei: Optional[int]
    status: Optional[int]


# ---------------------------------------
# BigQuery SQL（Uniswap限定：Factory→Pool→Swap→Tx+Receipts）
# ---------------------------------------
# 置換: BQ_SQL -> BQ_SQL_ACTIVE_POOLS
BQ_SQL_ACTIVE_POOLS = r"""
DECLARE from_block INT64 DEFAULT @from_block;
DECLARE to_block   INT64 DEFAULT @to_block;

DECLARE dataset    STRING DEFAULT @dataset;
DECLARE logs_table STRING DEFAULT CONCAT(dataset, ".logs");
DECLARE tx_table   STRING DEFAULT CONCAT(dataset, ".transactions");
DECLARE rcpt_table STRING DEFAULT CONCAT(dataset, ".receipts");

DECLARE pools ARRAY<STRING> DEFAULT @pools;

DECLARE topic_swap_v2 STRING DEFAULT '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822';
DECLARE topic_swap_v3 STRING DEFAULT '0xc42079a4f72e13aa39cc39dce8d3bb0d7d2cc3f3eaa062b1c9d2e6f5d97d0e00';

EXECUTE IMMEDIATE (
  '''
    WITH swap_txs AS (
      SELECT
        l.transaction_hash AS tx_hash,
        ANY_VALUE(l.block_number) AS block_number
      FROM ''' || logs_table || ''' AS l
      WHERE ARRAY_LENGTH(l.topics) >= 1
        AND l.topics[SAFE_OFFSET(0)] IN (@topic_swap_v2, @topic_swap_v3)
        AND LOWER(l.address) IN (SELECT p FROM UNNEST(@pools) AS p)
        AND l.block_number BETWEEN @from_block AND @to_block
      GROUP BY tx_hash
    ),
    tx_norm AS (
      SELECT
        t.transaction_hash,
        CAST(t.block_timestamp AS STRING) AS block_timestamp,
        t.transaction_index,
        t.from_address,
        t.to_address,
        COALESCE(
          SAFE_CAST(JSON_VALUE(TO_JSON_STRING(t.value), '$.bignumeric_value') AS BIGNUMERIC),
          SAFE_CAST(JSON_VALUE(TO_JSON_STRING(t.value), '$.string_value')     AS BIGNUMERIC),
          SAFE_CAST(TO_JSON_STRING(t.value)                                   AS BIGNUMERIC)
        ) AS value_wei,
        COALESCE(
          SAFE_CAST(JSON_VALUE(TO_JSON_STRING(t.gas_price), '$.bignumeric_value') AS BIGNUMERIC),
          SAFE_CAST(JSON_VALUE(TO_JSON_STRING(t.gas_price), '$.string_value')     AS BIGNUMERIC),
          SAFE_CAST(TO_JSON_STRING(t.gas_price)                                   AS BIGNUMERIC)
        ) AS gas_price_tx,
        r.gas_used,
        COALESCE(
          SAFE_CAST(JSON_VALUE(TO_JSON_STRING(r.effective_gas_price), '$.bignumeric_value') AS BIGNUMERIC),
          SAFE_CAST(JSON_VALUE(TO_JSON_STRING(r.effective_gas_price), '$.string_value')     AS BIGNUMERIC),
          SAFE_CAST(TO_JSON_STRING(r.effective_gas_price)                                   AS BIGNUMERIC)
        ) AS gas_price_rcpt,
        r.status
      FROM ''' || tx_table || ''' AS t
      JOIN ''' || rcpt_table || ''' AS r
        USING (transaction_hash)
    )
    SELECT
      s.block_number AS block_number,
      n.block_timestamp,
      n.transaction_index,
      s.tx_hash       AS transaction_hash,
      n.from_address,
      n.to_address,
      n.value_wei,
      n.gas_used,
      COALESCE(n.gas_price_tx, n.gas_price_rcpt) AS gas_price_wei,
      n.gas_price_rcpt                           AS effective_gas_price_wei,
      n.status
    FROM swap_txs s
    JOIN tx_norm n
      ON n.transaction_hash = s.tx_hash
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


# ---------------------------------------
# BigQuery 実行 → TxRow[]
# ---------------------------------------
async def bq_fetch_tx_rows_for_pools(
    dataset: str,
    pools_lower: List[str],
    from_block: int,
    to_block: int,
) -> List[TxRow]:
    if not pools_lower:
        return []
    client = bq_client()
    logs_table = f"{dataset}.logs"        # 使っていないが参照残し可
    tx_table   = f"{dataset}.transactions"
    rcpt_table = f"{dataset}.receipts"

    job_config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("from_block", "INT64", from_block),
            ScalarQueryParameter("to_block", "INT64", to_block),
            ScalarQueryParameter("dataset", "STRING", dataset),
            ArrayQueryParameter("pools", "STRING", pools_lower),
        ]
    )

    def _q():
        return client.query(BQ_SQL_ACTIVE_POOLS, job_config=job_config)

    t0 = time.time()
    job = await retry_async(lambda: asyncio.to_thread(_q), label="bq.tx_active_pools")
    rows: List[TxRow] = []
    for r in job:
        rows.append(
            TxRow(
                block_number=int(r["block_number"]),
                block_timestamp=str(r["block_timestamp"]),
                tx_index=int(r["transaction_index"]),
                tx_hash=r["transaction_hash"],
                from_address=r["from_address"],
                to_address=r.get("to_address"),
                value_wei=int(r["value_wei"]) if r.get("value_wei") is not None else 0,
                gas_used=int(r["gas_used"]) if r.get("gas_used") is not None else None,
                gas_price_wei=int(r["gas_price_wei"]) if r.get("gas_price_wei") is not None else None,
                effective_gas_price_wei=int(r["effective_gas_price_wei"]) if r.get("effective_gas_price_wei") is not None else None,
                status=int(r["status"]) if r.get("status") is not None else None,
            )
        )
    print(f"[BQ] (active pools) fetched rows={len(rows)} for {from_block}-{to_block} in {time.time()-t0:.2f}s")
    return rows
# ---------------------------------------
# UPSERT to transactions
# ---------------------------------------
async def upsert_transactions(session, chain_id_db: int, tx_rows: List[TxRow]) -> int:
    if not tx_rows:
        return 0

    payload = [
        {
            "chain_id": chain_id_db,
            "block_number": r.block_number,
            "block_timestamp": r.block_timestamp,
            "tx_index": r.tx_index,
            "tx_hash": r.tx_hash,
            "from_address": r.from_address,
            "to_address": r.to_address,
            "value_wei": r.value_wei,
            "gas_used": r.gas_used,
            "gas_price_wei": r.gas_price_wei,
            "effective_gas_price_wei": r.effective_gas_price_wei,
            "status": r.status,
        }
        for r in tx_rows
    ]

    total = 0
    for chunk in chunked(payload, TX_UPSERT_BATCH):
        stmt = (
            pg_insert(Transaction)
            .values(chunk)
            .on_conflict_do_update(
                constraint="uq_transactions_chain_txhash",
                set_={
                    "block_number": pg_insert(Transaction).excluded.block_number,
                    "block_timestamp": pg_insert(Transaction).excluded.block_timestamp,
                    "tx_index": pg_insert(Transaction).excluded.tx_index,
                    "from_address": pg_insert(Transaction).excluded.from_address,
                    "to_address": pg_insert(Transaction).excluded.to_address,
                    "value_wei": pg_insert(Transaction).excluded.value_wei,
                    "gas_used": pg_insert(Transaction).excluded.gas_used,
                    "gas_price_wei": pg_insert(Transaction).excluded.gas_price_wei,
                    "effective_gas_price_wei": pg_insert(
                        Transaction
                    ).excluded.effective_gas_price_wei,
                    "status": pg_insert(Transaction).excluded.status,
                },
            )
        )
        await session.execute(stmt.execution_options(synchronize_session=False))
        total += len(chunk)

    await session.commit()
    return total


# ---------------------------------------
# Orchestrator
#   - chains を取得
#   - 各 chain の defi_factories を取得
#   - factory.created_block_number .. chain.last_block_number を 10万刻みでBigQuery
# ---------------------------------------


async def backfill_transactions_uniswap(
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

            # ★ is_activeなプールを取得（address, created_block_number）
            pq = (
                select(
                    func.lower(DefiPool.address),
                    DefiPool.created_block_number,
                )
                .where(
                    DefiPool.chain_id == chain_id_db,
                    DefiPool.is_active.is_(True),
                )
            )
            pool_rows = (await session.execute(pq)).all()
            if not pool_rows:
                print(f"[{chain_name}] no active pools, skip")
                continue

            pools_lower = [addr for (addr, _cb) in pool_rows]
            start_blk = min(int(cb) for (_a, cb) in pool_rows if cb is not None) if any(cb for (_a, cb) in pool_rows) else 0
            end_blk = int(chain_last)

            print(f"[{chain_name}] active_pools={len(pools_lower)} scan {start_blk}-{end_blk} step={window_blocks}")

            # ウィンドウ×プールバッチで実行
            win_from = start_blk
            while win_from <= end_blk and not _shutdown:
                win_to = min(win_from + window_blocks - 1, end_blk)
                print(f"[{chain_name}] window {win_from}-{win_to} ...")

                total_upserted = 0
                for batch in chunked(pools_lower, POOLS_BATCH):
                    try:
                        tx_rows = await bq_fetch_tx_rows_for_pools(
                            dataset=dataset,
                            pools_lower=batch,
                            from_block=win_from,
                            to_block=win_to,
                        )
                        if tx_rows:
                            n = await upsert_transactions(session, chain_id_db, tx_rows)
                            total_upserted += n
                    except Exception as e:
                        print(f"[{chain_name}] window {win_from}-{win_to} pools_batch({len(batch)}) ERROR: {e} (skip batch)")

                print(f"[{chain_name}] window {win_from}-{win_to} upserted_total={total_upserted}")
                win_from = win_to + 1

    print(f"[DONE] total_elapsed={time.time()-t_all:.2f}s")


# ---------------------------------------
# CLI
# ---------------------------------------
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Backfill Uniswap swap transactions from BigQuery"
    )
    p.add_argument(
        "--chain", dest="only_chain", type=str, default=None, help="Chain.name filter"
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
        backfill_transactions_uniswap(
            only_chain=args.only_chain,
            window_blocks=args.window_blocks,
        )
    )
