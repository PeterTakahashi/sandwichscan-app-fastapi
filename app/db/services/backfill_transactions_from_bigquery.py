import asyncio
import time
import signal
import argparse
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Type

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from web3 import Web3

from app.db.session import async_session_maker
from app.lib.utils.bq_client import bq_client
from app.models import Chain, DefiPool, Transaction

# ---------------- Tunables ---------------- #
MAX_IN_PARAMS = 10_000
UPSERT_BATCH = 500
LOGS_BATCH_ADDR = 3_000          # logs の address IN を分割
TXHASH_BATCH = 5_000             # tx_hash の UNNEST を分割
MINIMUM_CHUNK_BLOCKS = 50_000
MAXIMUM_CHUNK_BLOCKS = 1_000_000
DEFAULT_CONFIRMS = 20

# ---------------- Small helpers ---------------- #
def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]

async def retry_async(
    fn,
    *,
    attempts: int = 5,
    base_delay: float = 0.5,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    label: str = "op",
):
    last = None
    for i in range(attempts):
        try:
            return await fn()
        except retry_on as e:
            last = e
            delay = base_delay * (2**i)
            print(f"[retry] {label} failed: {e}, retry in {delay:.2f}s ({i+1}/{attempts})")
            await asyncio.sleep(delay)
    raise last  # type: ignore[misc]

# ---------------- Signatures ---------------- #
# Uniswap v2: Swap(address,uint256,uint256,uint256,uint256,address)
SIG_SWAP_V2 = Web3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex()
if not SIG_SWAP_V2.startswith("0x"):
    SIG_SWAP_V2 = "0x" + SIG_SWAP_V2

# Uniswap v3: Swap(address,address,int256,int256,uint160,uint128,int24)
SIG_SWAP_V3 = Web3.keccak(text="Swap(address,address,int256,int256,uint160,uint128,int24)").hex()
if not SIG_SWAP_V3.startswith("0x"):
    SIG_SWAP_V3 = "0x" + SIG_SWAP_V3

# 他 AMM を増やす場合は上に追加
SWAP_TOPIC0S = [SIG_SWAP_V2, SIG_SWAP_V3]

# ---------------- BQ SQL builders ---------------- #
def _where_block_range(from_block: Optional[int], to_block: Optional[int]) -> str:
    cond = []
    if from_block is not None:
        cond.append(f"block_number >= {from_block}")
    if to_block is not None:
        cond.append(f"block_number <= {to_block}")
    return " AND ".join(cond) if cond else "TRUE"

def build_swap_logs_sql_for_addresses(
    logs_table: str,
    pool_addrs_lower: List[str],
    topic0s: List[str],
    from_block: Optional[int],
    to_block: Optional[int],
) -> str:
    # addresses, topic0s は UNNEST でフィルタ
    return f"""
      DECLARE addrs ARRAY<STRING> DEFAULT {pool_addrs_lower};
      DECLARE t0s   ARRAY<STRING> DEFAULT {topic0s};

      SELECT DISTINCT transaction_hash AS tx_hash, block_number
      FROM `{logs_table}`
      WHERE address IN UNNEST(addrs)
        AND topics[OFFSET(0)] IN UNNEST(t0s)
        AND {_where_block_range(from_block, to_block)}
      ORDER BY block_number ASC
    """

def build_txs_join_sql(
    tx_table: str,
    rcpt_table: str,
    tx_hashes: List[str],
) -> str:
    # tx_hash を起点に transactions + receipts を結合
    return f"""
      DECLARE hashes ARRAY<STRING> DEFAULT {tx_hashes};

      WITH h AS (
        SELECT DISTINCT LOWER(x) AS h FROM UNNEST(hashes) AS x
      )
      SELECT
        t.block_number,
        t.block_timestamp,            -- TIMESTAMP
        t.transaction_index,
        t.transaction_hash,
        t.from_address,
        t.to_address,
        t.value,
        r.gas_used,
        r.gas_price,                  -- 一部チェーンは null のこともある
        r.effective_gas_price,
        r.status
      FROM `{tx_table}` AS t
      JOIN `{rcpt_table}` AS r
        ON r.transaction_hash = t.transaction_hash
      JOIN h ON LOWER(t.transaction_hash) = h.h
      ORDER BY t.block_number ASC, t.transaction_index ASC
    """

# ---------------- BQ row types ---------------- #
@dataclass
class TxMetaRow:
    block_number: int
    block_timestamp: str          # ISO化はアプリ側で
    tx_index: int
    tx_hash: str
    from_address: str
    to_address: Optional[str]
    value_wei: int
    gas_used: Optional[int]
    gas_price_wei: Optional[int]
    effective_gas_price_wei: Optional[int]
    status: Optional[int]

# ---------------- Fetchers ---------------- #
async def fetch_swap_tx_hashes_for_pools(
    chain_bq_dataset: str,
    pool_addrs: Iterable[str],
    from_block: Optional[int],
    to_block: Optional[int],
) -> List[Tuple[str, int]]:
    """
    returns list of (tx_hash, block_number)
    """
    logs_table = f"{chain_bq_dataset}.logs"
    topic0s = "[" + ",".join([f"'{t.lower()}'" for t in SWAP_TOPIC0S]) + "]"

    # IN の長さ制限を避けるためアドレスはバッチ分割
    out: List[Tuple[str, int]] = []
    addr_list = [a.lower() for a in pool_addrs]
    for chunk in chunked(addr_list, LOGS_BATCH_ADDR):
        addrs = "[" + ",".join([f"'{a}'" for a in chunk]) + "]"
        sql = build_swap_logs_sql_for_addresses(
            logs_table, addrs, topic0s, from_block, to_block
        )

        def _q():
            client = bq_client()
            return client.query(sql)

        job = await retry_async(lambda: asyncio.to_thread(_q), label="bq.query swap_logs")
        for r in job:
            out.append((r["tx_hash"], int(r["block_number"])))
    return out

async def fetch_transactions_by_hashes(
    chain_bq_dataset: str,
    tx_hashes: Iterable[str],
) -> List[TxMetaRow]:
    """
    受け取った tx_hash 群について、transactions + receipts を JOIN して取得
    """
    tx_table = f"{chain_bq_dataset}.transactions"
    rcpt_table = f"{chain_bq_dataset}.receipts"
    hashes = [h.lower() for h in tx_hashes]

    rows: List[TxMetaRow] = []
    for chunk in chunked(hashes, TXHASH_BATCH):
        arr = "[" + ",".join([f"'{h}'" for h in chunk]) + "]"
        sql = build_txs_join_sql(tx_table, rcpt_table, arr)

        def _q():
            client = bq_client()
            return client.query(sql)

        job = await retry_async(lambda: asyncio.to_thread(_q), label="bq.query txs+receipts")
        for r in job:
            rows.append(
                TxMetaRow(
                    block_number=int(r["block_number"]),
                    block_timestamp=str(r["block_timestamp"]),  # "2024-01-01 00:00:00+00"
                    tx_index=int(r["transaction_index"]),
                    tx_hash=r["transaction_hash"],
                    from_address=r["from_address"],
                    to_address=r.get("to_address"),
                    value_wei=int(r["value"]),
                    gas_used=int(r["gas_used"]) if r.get("gas_used") is not None else None,
                    gas_price_wei=int(r["gas_price"]) if r.get("gas_price") is not None else None,
                    effective_gas_price_wei=int(r["effective_gas_price"]) if r.get("effective_gas_price") is not None else None,
                    status=int(r["status"]) if r.get("status") is not None else None,
                )
            )
    return rows

# ---------------- Upsert ---------------- #
async def upsert_transactions(
    session,
    chain_id_db: int,
    tx_rows: List[TxMetaRow],
) -> int:
    if not tx_rows:
        return 0

    payload = [
        {
            "chain_id": chain_id_db,
            "block_number": r.block_number,
            "block_timestamp": r.block_timestamp,  # DB側が TIMESTAMPTZ の場合は型変換してもOK
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
    for chunk in chunked(payload, UPSERT_BATCH):
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
                    "effective_gas_price_wei": pg_insert(Transaction).excluded.effective_gas_price_wei,
                    "status": pg_insert(Transaction).excluded.status,
                },
            )
        )
        await session.execute(stmt)
        total += len(chunk)

    await session.commit()
    return total

# ---------------- graceful shutdown ---------------- #
_shutdown = False
def _install_signal_handlers():
    def handler(signum, frame):
        global _shutdown
        _shutdown = True
        print(f"[signal] received {signum}, will stop after current chunk...")
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, handler)
        except Exception:
            pass

# ---------------- Orchestrator ---------------- #
def _fmt_range(a: Optional[int], b: Optional[int]) -> str:
    if a is None and b is None:
        return "(all)"
    if a is None:
        return f"(..-{b})"
    if b is None:
        return f"({a}-..)"
    return f"({a}-{b})"

async def backfill_transactions_for_swaps(
    *,
    from_block: Optional[int] = None,
    to_block: Optional[int] = None,
    only_chain: Optional[str] = None,
    only_pool: Optional[str] = None,    # ilike マッチ
    confirmations: int = DEFAULT_CONFIRMS,
    daily: bool = False,
):
    """
    1) 指定チェーンのプール群を取得（optional: address フィルタ）
    2) BQ logs から swap を含む tx_hash を抽出
    3) BQ transactions + receipts から tx メタを取得
    4) transactions に UPSERT
    """
    _install_signal_handlers()
    t0 = time.time()

    async with async_session_maker() as session:
        # チェーン一覧
        cq = select(Chain.id, Chain.name, Chain.big_query_table_id, Chain.last_block_number)
        if only_chain:
            cq = cq.where(Chain.name == only_chain)
        chains = (await session.execute(cq)).all()

        for chain_id_db, chain_name, chain_bq, chain_last in chains:
            if _shutdown:
                break
            if not chain_bq:
                print(f"[{chain_name}] big_query_table_id is empty, skip.")
                continue

            print(f"[{chain_name}] scanning pools ...")
            pq = select(DefiPool.address).where(DefiPool.chain_id == chain_id_db)
            if only_pool:
                pq = pq.where(DefiPool.address.ilike(only_pool))
            pool_addrs = [r[0] for r in (await session.execute(pq)).all()]
            if not pool_addrs:
                print(f"[{chain_name}] no pools, skip.")
                continue

            # 上限の確定
            hard_upper = to_block if to_block is not None else int(chain_last or 0)
            if daily:
                hard_upper = max(hard_upper - confirmations, 0)

            print(
                f"[{chain_name}] pools={len(pool_addrs)} "
                f"range={_fmt_range(from_block, hard_upper)}"
            )

            # 1) swap を含む tx_hash を logs から抽出
            t1 = time.time()
            pairs = await fetch_swap_tx_hashes_for_pools(
                chain_bq_dataset=chain_bq,
                pool_addrs=pool_addrs,
                from_block=from_block,
                to_block=hard_upper,
            )
            dt1 = time.time() - t1
            if not pairs:
                print(f"[{chain_name}] no swap txs found (in {dt1:.2f}s)")
                continue

            # 重複排除 & ソート
            uniq_tx = list({h.lower(): b for (h, b) in pairs}.keys())
            print(
                f"[{chain_name}] swap_tx_hashes={len(uniq_tx)} (found in {dt1:.2f}s)"
            )

            # 2) tx + receipts を取得
            t2 = time.time()
            tx_rows = await fetch_transactions_by_hashes(
                chain_bq_dataset=chain_bq, tx_hashes=uniq_tx
            )
            dt2 = time.time() - t2
            print(f"[{chain_name}] fetched tx metas={len(tx_rows)} (in {dt2:.2f}s)")

            # 3) UPSERT
            t3 = time.time()
            n = await upsert_transactions(session, chain_id_db, tx_rows)
            dt3 = time.time() - t3
            print(f"[{chain_name}] upserted transactions={n} (in {dt3:.2f}s)")

    print(f"[DONE] elapsed_total={time.time() - t0:.2f}s")

# ---------------- CLI ---------------- #
def _parse_args():
    p = argparse.ArgumentParser(description="Backfill transactions (swap-related) from BigQuery")
    p.add_argument("--from", dest="from_block", type=int, default=None, help="start block (inclusive)")
    p.add_argument("--to", dest="to_block", type=int, default=None, help="end block (inclusive)")
    p.add_argument("--chain", dest="only_chain", type=str, default=None, help="Chain.name filter (e.g. Ethereum)")
    p.add_argument("--pool", dest="only_pool", type=str, default=None, help="pool address filter (ilike match)")
    p.add_argument("--confirmations", dest="confirmations", type=int, default=DEFAULT_CONFIRMS, help="tip confirmations")
    p.add_argument("--daily", action="store_true", help="use (latest - confirmations) as upper bound")
    return p.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        backfill_transactions_for_swaps(
            from_block=args.from_block,
            to_block=args.to_block,
            only_chain=args.only_chain,
            only_pool=args.only_pool,
            confirmations=args.confirmations,
            daily=args.daily,
        )
    )