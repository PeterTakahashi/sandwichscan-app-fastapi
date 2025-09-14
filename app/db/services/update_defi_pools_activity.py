import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from sqlalchemy import select, update, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.lib.utils.bq_client import bq_client
from app.models import Chain, DefiPool
from sqlalchemy.orm import aliased
from app.models import Token
import time

# ──────────────────────────────────────────────────────────────
# Tunables
# ──────────────────────────────────────────────────────────────
DB_POOL_PAGE_SIZE = 5_000
BQ_POOL_BATCH_SIZE = 1_000
DB_UPDATE_BATCH_SIZE = 1_000
CONCURRENCY_PER_CHAIN = 10
RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 0.5

# ──────────────────────────────────────────────────────────────
# BigQuery SQL（EXECUTE IMMEDIATE FORMAT を安全に）
#  外側は三重シングル。FORMAT() の中は単一引用符で囲む。
# ──────────────────────────────────────────────────────────────
_BQ_SQL = r"""
DECLARE dataset STRING DEFAULT @dataset;
DECLARE logs_table STRING   DEFAULT CONCAT(dataset, ".logs");
DECLARE tx_table   STRING   DEFAULT CONCAT(dataset, ".transactions");

DECLARE topic_swap_v2 STRING DEFAULT '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822';
DECLARE topic_swap_v3 STRING DEFAULT '0xc42079a4f72e13aa39cc39dce8d3bb0d7d2cc3f3eaa062b1c9d2e6f5d97d0e00';

DECLARE pools ARRAY<STRING> DEFAULT @pools;
DECLARE ts_24h_start TIMESTAMP DEFAULT @ts_24h_start;
DECLARE ts_7d_start  TIMESTAMP DEFAULT @ts_7d_start;

EXECUTE IMMEDIATE (
  '''
    WITH swap_logs AS (
        SELECT
            LOWER(l.address) AS pool,
            l.transaction_hash AS tx_hash,
            l.block_number AS block_number   -- ★ 追加
        FROM ''' || logs_table || ''' AS l
        WHERE ARRAY_LENGTH(l.topics) >= 1
            AND l.topics[SAFE_OFFSET(0)] IN (@topic_swap_v2, @topic_swap_v3)
            AND LOWER(l.address) IN (SELECT p FROM UNNEST(@pools) AS p)
    )
    SELECT
        s.pool,
        COUNTIF(t.block_timestamp >= @ts_24h_start) AS swaps_24h,
        COUNTIF(t.block_timestamp >= @ts_7d_start)  AS swaps_7d,
        MAX(s.block_number)                        AS last_swap_block,
        CAST(MAX(t.block_timestamp) AS STRING)     AS last_swap_at
    FROM swap_logs s
    JOIN ''' || tx_table || ''' AS t
        ON t.transaction_hash = s.tx_hash
    GROUP BY s.pool
   '''
)
USING
  dataset AS dataset,
  pools AS pools,
  ts_24h_start AS ts_24h_start,
  ts_7d_start AS ts_7d_start,
  topic_swap_v2 AS topic_swap_v2,
  topic_swap_v3 AS topic_swap_v3;
"""

# ──────────────────────────────────────────────────────────────
# Utility: リトライ
# ──────────────────────────────────────────────────────────────
async def retry_async(fn, *, attempts=RETRY_ATTEMPTS, base_delay=RETRY_BASE_DELAY, label="op"):
    last: Optional[BaseException] = None
    for i in range(attempts):
        try:
            return await fn()
        except Exception as e:
            last = e
            delay = base_delay * (2**i)
            print(f"[retry] {label} failed: {e} -> retry in {delay:.2f}s ({i+1}/{attempts})")
            await asyncio.sleep(delay)
    if last:
        raise last

# ──────────────────────────────────────────────────────────────
# Activity score
# ──────────────────────────────────────────────────────────────
def _activity_score(swaps_24h: int, swaps_7d: int, last_swap_at: Optional[datetime]) -> int:
    score = 3 * int(swaps_24h) + int(swaps_7d)
    if last_swap_at:
        age_s = max(0.0, (datetime.utcnow() - last_swap_at).total_seconds())
        if age_s <= 24*3600:
            score += 25
        elif age_s <= 72*3600:
            score += 10
    return score

# ──────────────────────────────────────────────────────────────
# BQ 実行（バッチ 1 回）
# ──────────────────────────────────────────────────────────────
async def _bq_fetch_activity(dataset: str, pool_addrs_lower: List[str]) -> Dict[str, Tuple[int, int, Optional[int], Optional[str]]]:
    if not pool_addrs_lower:
        return {}
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter, ArrayQueryParameter
    client = bq_client()
    now_utc = datetime.utcnow()
    job_config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("dataset", "STRING", dataset),
            ArrayQueryParameter("pools", "STRING", pool_addrs_lower),
            ScalarQueryParameter("ts_24h_start", "TIMESTAMP", now_utc - timedelta(days=1)),
            ScalarQueryParameter("ts_7d_start",  "TIMESTAMP", now_utc - timedelta(days=7)),
        ]
    )
    def _q():
        return client.query(_BQ_SQL, job_config=job_config)
    job = await retry_async(lambda: asyncio.to_thread(_q), label="bq.activity")
    out: Dict[str, Tuple[int, int, Optional[int], Optional[str]]] = {}
    for r in job:
        out[str(r["pool"])] = (
            int(r["swaps_24h"] or 0),
            int(r["swaps_7d"] or 0),
            int(r["last_swap_block"]) if r.get("last_swap_block") is not None else None,
            str(r["last_swap_at"]) if r.get("last_swap_at") is not None else None,
        )
    return out

# ──────────────────────────────────────────────────────────────
# DB: id > last_id でページング
# ──────────────────────────────────────────────────────────────
async def _iter_pools(session: AsyncSession, chain_id_db: int, page_size: int):
    last_id = 0
    t0 = aliased(Token)
    t1 = aliased(Token)
    while True:
        q = (
            select(DefiPool.id, DefiPool.address)
            .join(t0, t0.id == DefiPool.token0_id)
            .join(t1, t1.id == DefiPool.token1_id)
            .where(
                DefiPool.chain_id == chain_id_db,
                DefiPool.id > last_id,
                t0.decimals_invalid.is_(False),
                t1.decimals_invalid.is_(False),
            )
            .order_by(DefiPool.id.asc())
            .limit(page_size)
        )
        rows = (await session.execute(q)).all()
        if not rows:
            break
        yield rows
        last_id = rows[-1][0]

# ──────────────────────────────────────────────────────────────
# DB: bulk UPDATE（synchronize_session=False を明示）
# ──────────────────────────────────────────────────────────────
async def _bulk_update_pools(session: AsyncSession, updates: List[Dict]):
    if not updates:
        return
    stmt = (
        update(DefiPool)
        .where(DefiPool.id == bindparam("b_id"))
        .values(
            is_active=bindparam("is_active"),
            last_swap_block=bindparam("last_swap_block"),
            last_swap_at=bindparam("last_swap_at"),
            swaps_24h=bindparam("swaps_24h"),
            swaps_7d=bindparam("swaps_7d"),
            activity_score=bindparam("activity_score"),
        )
    ).execution_options(synchronize_session=False)  # ★ 重要
    await session.execute(stmt, updates)

# ──────────────────────────────────────────────────────────────
# チェーン 1 本分
# ──────────────────────────────────────────────────────────────
async def _process_chain(chain_id_db: int, chain_name: str, dataset: str):
    print(f"[{chain_name}] start activity update (dataset={dataset})")
    sem = asyncio.Semaphore(CONCURRENCY_PER_CHAIN)

    async with async_session_maker() as session:
        pages = 0
        total_updated = 0
        async for pool_rows in _iter_pools(session, chain_id_db, DB_POOL_PAGE_SIZE):
            pages += 1
            ids: List[int] = []
            addrs_lower: List[str] = []
            for pid, addr in pool_rows:
                ids.append(pid)
                addrs_lower.append(addr.lower())

            page_updates: List[Dict] = []
            for i in range(0, len(addrs_lower), BQ_POOL_BATCH_SIZE):
                batch_ids = ids[i : i + BQ_POOL_BATCH_SIZE]
                batch_addrs = addrs_lower[i : i + BQ_POOL_BATCH_SIZE]

                async with sem:
                    activity_map = await _bq_fetch_activity(dataset, batch_addrs)

                # 結果を更新レコードに変換
                for pid, addr_l in zip(batch_ids, batch_addrs):
                    rec = activity_map.get(addr_l)
                    if not rec:
                        page_updates.append(
                            dict(
                                b_id=pid,
                                id=pid,
                                is_active=False,
                                last_swap_block=None,
                                last_swap_at=None,
                                swaps_24h=0,
                                swaps_7d=0,
                                activity_score=0,
                            )
                        )
                    else:
                        swaps_24h, swaps_7d, last_blk, last_at_iso = rec
                        last_dt = None
                        if last_at_iso:
                            s = str(last_at_iso).replace("Z", "")
                            for token in ["+00:00", "+00", " UTC"]:
                                if s.endswith(token):
                                    s = s[: -len(token)]
                            try:
                                last_dt = datetime.fromisoformat(s)
                            except Exception:
                                last_dt = None
                        score = _activity_score(swaps_24h, swaps_7d, last_dt)
                        print(f"[{chain_name}] pool_id={pid} swaps_24h={swaps_24h} swaps_7d={swaps_7d} last_swap_at={last_dt} score={score}")
                        page_updates.append(
                            dict(
                                b_id=pid,
                                id=pid,
                                is_active=(swaps_7d > 0),
                                last_swap_block=last_blk,
                                last_swap_at=last_dt,
                                swaps_24h=swaps_24h,
                                swaps_7d=swaps_7d,
                                activity_score=score,
                            )
                        )

                # 小刻みに UPDATE & COMMIT
                if len(page_updates) >= DB_UPDATE_BATCH_SIZE:
                    await _bulk_update_pools(session, page_updates)
                    await session.commit()
                    total_updated += len(page_updates)
                    print(f"[{chain_name}] updated {total_updated} pools so far (page {pages})")
                    page_updates.clear()

            # ページ残りを flush
            if page_updates:
                await _bulk_update_pools(session, page_updates)
                await session.commit()
                total_updated += len(page_updates)
                print(f"[{chain_name}] updated {total_updated} pools so far (page {pages})")

    print(f"[{chain_name}] done. total_updated={total_updated}, pages={pages}")

# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────
async def update_defi_pools_activity(*, only_chain: Optional[str] = None):
    async with async_session_maker() as session:
        cq = select(Chain.id, Chain.name, Chain.big_query_table_id).where(
            Chain.big_query_table_id != ""
        )
        if only_chain:
            cq = cq.where(Chain.name == only_chain)
        chains = (await session.execute(cq)).all()

    for chain_id_db, chain_name, dataset in chains:
        await _process_chain(chain_id_db, chain_name, dataset)

# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Update DefiPool activity metrics from BigQuery (batched)")
    p.add_argument("--chain", dest="only_chain", type=str, default=None, help="Chain.name filter")
    p.add_argument("--db-page", dest="db_page", type=int, default=DB_POOL_PAGE_SIZE, help="DB page size")
    p.add_argument("--bq-batch", dest="bq_batch", type=int, default=BQ_POOL_BATCH_SIZE, help="BQ pools batch size")
    p.add_argument("--update-batch", dest="update_batch", type=int, default=DB_UPDATE_BATCH_SIZE, help="DB update batch size")
    p.add_argument("--concurrency", dest="concurrency", type=int, default=CONCURRENCY_PER_CHAIN, help="BQ concurrency per chain")
    args = p.parse_args()

    asyncio.run(update_defi_pools_activity(only_chain=args.only_chain))