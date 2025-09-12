import asyncio
import time
import signal
import argparse
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Callable, Type

from eth_abi import decode as abi_decode
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from web3 import Web3

from app.db.session import async_session_maker
from app.lib.utils.bq_client import bq_client
from app.models import Chain, DefiFactory, DefiPool, DefiVersion, Token

from app.lib.utils.sanitize_symbol import sanitize_symbol

# ---------------- Tunables (sane defaults) ---------------- #
MAX_IN_PARAMS = 10_000
UPSERT_BATCH = 50  # 少し上げて往復回数減らす
MC_BATCH = 250
MINIMUM_CHUNK_BLOCKS = 100_000
MAXIMUM_CHUNK_BLOCKS = 1_000_000
DEFAULT_CONFIRMS = 20  # 先端からのreorgバッファ


def compute_chunk_blocks(chain_last: int, factory_created: int) -> int:
    if factory_created is None or factory_created <= 0:
        # created 未設定なら最低値で開始
        return MINIMUM_CHUNK_BLOCKS
    span = max(chain_last - factory_created, 0)
    dyn = span // 100
    if dyn <= 0:
        dyn = MINIMUM_CHUNK_BLOCKS
    # クランプ
    dyn = max(MINIMUM_CHUNK_BLOCKS, min(dyn, MAXIMUM_CHUNK_BLOCKS))
    return dyn


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ---------------- Signatures ---------------- #
SIG_PAIR_CREATED = Web3.keccak(
    text="PairCreated(address,address,address,uint256)"
).hex()
if not SIG_PAIR_CREATED.startswith("0x"):
    SIG_PAIR_CREATED = "0x" + SIG_PAIR_CREATED

SIG_POOL_CREATED = Web3.keccak(
    text="PoolCreated(address,address,uint24,int24,address)"
).hex()
if not SIG_POOL_CREATED.startswith("0x"):
    SIG_POOL_CREATED = "0x" + SIG_POOL_CREATED

# ---------------- Multicall3 ---------------- #
MULTICALL3 = Web3.to_checksum_address("0xcA11bde05977b3631167028862bE2a173976CA11")
SEL_DECIMALS = Web3.keccak(text="decimals()")[:4].hex()
SEL_SYMBOL = Web3.keccak(text="symbol()")[:4].hex()
MC3_SELECTOR = Web3.keccak(text="aggregate3((address,bool,bytes)[])")[:4].hex()


def _to_checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)


def _strip_0x(s: str) -> str:
    return s[2:] if s.startswith("0x") else s


# ---------------- Small retry helper ---------------- #
async def retry_async(
    fn: Callable[[], Any],
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
            print(
                f"[retry] {label} failed: {e}, retry in {delay:.2f}s ({i+1}/{attempts})"
            )
            await asyncio.sleep(delay)
    raise last  # type: ignore[misc]


# ---------------- BQ SQL builders ---------------- #
def build_logs_sql(
    table: str,
    factory: str,
    topic0: str,
    from_block: Optional[int],
    to_block: Optional[int],
) -> str:
    where = [
        f"address = '{factory.lower()}'",
        f"topics[OFFSET(0)] = '{topic0}'",
    ]
    if from_block is not None:
        where.append(f"block_number >= {from_block}")
    if to_block is not None:
        where.append(f"block_number <= {to_block}")
    where_sql = " AND ".join(where)
    return f"""
      SELECT data, topics, block_number, transaction_hash
      FROM `{table}`
      WHERE {where_sql}
      ORDER BY block_number ASC
    """


def build_min_block_sql(table: str, factory: str, topic0: str) -> str:
    return f"""
      SELECT MIN(block_number) AS min_block
      FROM `{table}`
      WHERE address = '{factory.lower()}'
        AND topics[OFFSET(0)] = '{topic0}'
    """


@dataclass
class BqLogRow:
    data: str
    topics: List[str]
    block_number: int
    tx_hash: str


async def fetch_factory_logs_from_bq(
    chain_big_query_table_id: str,
    factory_addr: str,
    is_v3: bool,
    from_block: Optional[int],
    to_block: Optional[int],
) -> List[BqLogRow]:
    if not chain_big_query_table_id:
        return []
    table = chain_big_query_table_id + ".logs"
    topic0 = SIG_POOL_CREATED if is_v3 else SIG_PAIR_CREATED
    sql = build_logs_sql(table, factory_addr, topic0, from_block, to_block)

    def _q():
        client = bq_client()
        return client.query(sql)

    job = await retry_async(lambda: asyncio.to_thread(_q), label="bq.query logs")
    rows: List[BqLogRow] = []
    for r in job:
        rows.append(
            BqLogRow(
                data=r["data"],
                topics=list(r["topics"]),
                block_number=int(r["block_number"]),
                tx_hash=r["transaction_hash"],
            )
        )
    return rows


async def fetch_factory_first_block(
    chain_big_query_table_id: str, factory_addr: str, is_v3: bool
) -> Optional[int]:
    if not chain_big_query_table_id:
        return None
    table = chain_big_query_table_id + ".logs"
    topic0 = SIG_POOL_CREATED if is_v3 else SIG_PAIR_CREATED
    sql = build_min_block_sql(table, factory_addr, topic0)

    def _q():
        client = bq_client()
        return client.query(sql)

    job = await retry_async(lambda: asyncio.to_thread(_q), label="bq.query min_block")
    for r in job:
        v = r.get("min_block")
        return int(v) if v is not None else None
    return None


# ---------------- Decoders ---------------- #
def decode_pair_created_v2(row: BqLogRow) -> Tuple[str, str, str]:
    token0 = "0x" + _strip_0x(row.topics[1])[-40:]
    token1 = "0x" + _strip_0x(row.topics[2])[-40:]
    data_hex = _strip_0x(row.data)
    pair = "0x" + data_hex[24:64]
    return _to_checksum(token0), _to_checksum(token1), _to_checksum(pair)


def decode_pool_created_v3(row: BqLogRow) -> Tuple[str, str, int, int, str]:
    # topics:
    #   [0] = keccak("PoolCreated(address,address,uint24,int24,address)")
    #   [1] = indexed token0
    #   [2] = indexed token1
    #   [3] = indexed fee (uint24)
    token0 = "0x" + _strip_0x(row.topics[1])[-40:]
    token1 = "0x" + _strip_0x(row.topics[2])[-40:]
    fee = int(row.topics[3], 16)  # 500 / 3000 / 10000 など（uint24だがtopicsは32B）

    # data: 非indexedパラメータのみ = (int24 tickSpacing, address pool)
    data_bin = bytes.fromhex(_strip_0x(row.data))
    tick, pool = abi_decode(["int24", "address"], data_bin)

    return (
        _to_checksum(token0),
        _to_checksum(token1),
        int(fee),
        int(tick),
        _to_checksum(pool),
    )


# ---------------- Token upsert ---------------- #
async def upsert_tokens(
    session, chain_id_db: int, token_addrs: Iterable[str], rpc_url: str
) -> Dict[str, int]:
    addr_list = list({_to_checksum(a) for a in token_addrs})
    if not addr_list:
        return {}

    existing: Dict[str, int] = {}
    for chunk in chunked(addr_list, MAX_IN_PARAMS):
        rows = (
            await session.execute(
                select(Token.id, Token.address).where(
                    Token.chain_id == chain_id_db,
                    Token.address.in_(chunk),
                )
            )
        ).all()
        existing.update({addr: tid for (tid, addr) in rows})

    targets = [a for a in addr_list if a not in existing]
    if not targets:
        return existing

    w3 = Web3(Web3.HTTPProvider(rpc_url))

    def _encode(selector_hex: str) -> bytes:
        return bytes.fromhex(_strip_0x(selector_hex))

    def _build_aggregate3_payload(calls: List[Tuple[str, bytes]]) -> bytes:
        from eth_abi import encode as abi_encode

        tuples = [(Web3.to_checksum_address(t), True, cd) for (t, cd) in calls]
        encoded = abi_encode(["(address,bool,bytes)[]"], [tuples])
        return bytes.fromhex(_strip_0x(MC3_SELECTOR)) + encoded

    def _parse_decimals(raw) -> tuple[int, bool]:
        """
        returns: (normalized_decimals, invalid_flag)
        - 正常: 0..36 -> (そのまま, False)
        - 異常/不明: None/例外/範囲外 -> (0, True)
        """
        try:
            v = int(raw)
        except Exception:
            return 0, True
        if 0 <= v <= 36:
            return v, False
        return 0, True

    resolved: Dict[str, Tuple[int, str]] = {}
    from eth_abi import decode as abi_decode_inner

    for tchunk in chunked(targets, MC_BATCH):
        # decimals
        dec_calls = [(a, _encode(SEL_DECIMALS)) for a in tchunk]
        payload_dec = _build_aggregate3_payload(dec_calls)
        res_dec = await retry_async(
            lambda: asyncio.to_thread(
                w3.eth.call, {"to": MULTICALL3, "data": payload_dec}
            ),
            label="rpc.call decimals",
        )
        dec_results = abi_decode_inner(["(bool,bytes)[]"], res_dec)[0]
        dec_map: Dict[str, Optional[int]] = {}
        for i, (ok, rdata) in enumerate(dec_results):
            d = None
            if ok and len(rdata) >= 32:
                try:
                    d = int.from_bytes(rdata[-32:], "big")
                except Exception:
                    d = None
            dec_map[tchunk[i]] = d

        # symbol
        sym_calls = [(a, _encode(SEL_SYMBOL)) for a in tchunk]
        payload_sym = _build_aggregate3_payload(sym_calls)
        res_sym = await retry_async(
            lambda: asyncio.to_thread(
                w3.eth.call, {"to": MULTICALL3, "data": payload_sym}
            ),
            label="rpc.call symbol",
        )
        sym_results = abi_decode_inner(["(bool,bytes)[]"], res_sym)[0]

        for i, (ok, rdata) in enumerate(sym_results):
            addr = tchunk[i]
            dec_raw = dec_map.get(addr)
            decimals, dec_invalid = _parse_decimals(dec_raw)
            sym = "UNK"
            if ok and len(rdata) >= 32:
                try:
                    sym = abi_decode(["string"], rdata)[0]
                except Exception:
                    raw = rdata[-32:]
                    # bytes32対策 + 不正UTF-8/NULは sanitize_symbol 側で吸収
                    sym = (
                        raw.partition(b"\x00")[0].decode("utf-8", errors="ignore")
                        or "UNK"
                    )
            sym = sanitize_symbol(sym)
            resolved[addr] = (decimals, sym, dec_invalid)
            if dec_invalid:
                print(
                    f"[warn] decimals invalid for {addr}: raw={dec_raw} -> saved=0, flag=True"
                )

    rows = [
        {
            "chain_id": chain_id_db,
            "address": a,
            "symbol": s,
            "decimals": d,
            "decimals_invalid": inv,
        }
        for a, (d, s, inv) in resolved.items()
    ]
    for rchunk in chunked(rows, UPSERT_BATCH):
        stmt = (
            pg_insert(Token)
            .values(rchunk)
            .on_conflict_do_update(
                constraint="uq_tokens_chain_address",
                set_={
                    "symbol": pg_insert(Token).excluded.symbol,
                    "decimals": pg_insert(Token).excluded.decimals,
                    "decimals_invalid": pg_insert(Token).excluded.decimals_invalid,
                },
            )
        )
        await session.execute(stmt)
    await session.commit()

    existing = {}
    for chunk in chunked(addr_list, MAX_IN_PARAMS):
        rows = (
            await session.execute(
                select(Token.id, Token.address).where(
                    Token.chain_id == chain_id_db,
                    Token.address.in_(chunk),
                )
            )
        ).all()
        existing.update({addr: tid for (tid, addr) in rows})
    return existing


# ---------------- Pools upsert ---------------- #
async def upsert_pools(session, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    total = 0
    for rchunk in chunked(rows, UPSERT_BATCH):
        stmt = (
            pg_insert(DefiPool)
            .values(rchunk)
            .on_conflict_do_update(
                constraint="uq_defi_pools_chain_address",
                set_={
                    "defi_factory_id": pg_insert(DefiPool).excluded.defi_factory_id,
                    "token0_id": pg_insert(DefiPool).excluded.token0_id,
                    "token1_id": pg_insert(DefiPool).excluded.token1_id,
                    "created_block_number": pg_insert(
                        DefiPool
                    ).excluded.created_block_number,
                    "created_tx_hash": pg_insert(DefiPool).excluded.created_tx_hash,
                    "tick_spacing": pg_insert(DefiPool).excluded.tick_spacing,
                    "fee_tier_bps": pg_insert(DefiPool).excluded.fee_tier_bps,
                },
            )
        )
        await session.execute(stmt)
        total += len(rchunk)
    await session.commit()
    return total


# ---------------- helpers ---------------- #
async def _update_last_gotten_block(session, factory_id: int, new_block: int):
    await session.execute(
        update(DefiFactory)
        .where(DefiFactory.id == factory_id)
        .values(last_gotten_block_number=new_block)
    )
    await session.commit()


async def _ensure_factory_start_block(
    session,
    chain: Chain,
    factory_id: int,
    factory_addr: str,
    ver_name: str,
    current_last: int,
) -> Tuple[int, int]:
    """
    戻り値: (last_gotten_block_number, created_block_number)
    - last が 0 の場合は BQ で最初の作成ブロック min_block を探し、last = min_block - 1 に更新
    - factory.created_block_number が 0 の場合は min_block を保存
    """
    is_v3 = "v3" in ver_name.lower()
    # 既存 factory 行を取得
    f = (
        await session.execute(select(DefiFactory).where(DefiFactory.id == factory_id))
    ).scalar_one()
    created = int(getattr(f, "created_block_number", 0) or 0)

    if current_last and current_last > 0 and created > 0:
        return current_last, created

    # BQ で factory の最初の作成ブロックを検索
    min_block = await fetch_factory_first_block(
        chain.big_query_table_id, factory_addr, is_v3
    )

    # last は min_block - 1 に、created は min_block に
    init_last = max((min_block - 1) if min_block is not None else 0, 0)
    new_created = max(min_block or 0, 0)

    # last を必要な場合のみ更新
    if not current_last or current_last <= 0:
        await session.execute(
            update(DefiFactory)
            .where(DefiFactory.id == factory_id)
            .values(last_gotten_block_number=init_last)
        )

    # created を必要な場合のみ更新
    if created <= 0 and new_created > 0:
        await session.execute(
            update(DefiFactory)
            .where(DefiFactory.id == factory_id)
            .values(created_block_number=new_created)
        )

    await session.commit()
    print(
        f"[{chain.name}] factory {factory_addr}: init last={init_last}, created={new_created}"
    )
    return (current_last if current_last and current_last > 0 else init_last), (
        created if created > 0 else new_created
    )


async def _refresh_chain_latest_block(session, chain_db_id: int, rpc_url: str) -> int:
    """RPC から最新ブロックを取得して chains.last_block_number を更新し、その値を返す"""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    latest = int(
        await retry_async(
            lambda: asyncio.to_thread(lambda: w3.eth.block_number),
            label="rpc.block_number",
        )
    )
    await session.execute(
        update(Chain).where(Chain.id == chain_db_id).values(last_block_number=latest)
    )
    await session.commit()
    return latest


def _fmt_range(a: Optional[int], b: Optional[int]) -> str:
    if a is None and b is None:
        return "(all)"
    if a is None:
        return f"(..-{b})"
    if b is None:
        return f"({a}-..)"
    return f"({a}-{b})"


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
async def backfill_all(
    from_block: Optional[int] = None,
    to_block: Optional[int] = None,
    *,
    only_chain: Optional[str] = None,
    only_factory: Optional[str] = None,
    confirmations: int = DEFAULT_CONFIRMS,
    daily: bool = False,
):
    start_time = time.time()
    _install_signal_handlers()

    async with async_session_maker() as session:
        q = (
            select(
                DefiFactory.id,
                DefiFactory.address,
                DefiFactory.last_gotten_block_number,
                DefiVersion.name,
                Chain.id,
                Chain.name,
                Chain.rpc_url,
                Chain.last_block_number,
            )
            .join(DefiVersion, DefiVersion.id == DefiFactory.defi_version_id)
            .join(Chain, Chain.id == DefiFactory.chain_id)
        )
        if only_chain:
            q = q.where(Chain.name == only_chain)
        if only_factory:
            q = q.where(DefiFactory.address.ilike(only_factory))
        factories = (await session.execute(q)).all()

        print(
            f"[INIT] factories={len(factories)}, cli_range={_fmt_range(from_block, to_block)} "
            f"confirms={confirmations} daily={daily}"
        )

        # チェーンごとに latest を先に更新しておく（同一チェーンが複数ファクトリを持つためキャッシュ）
        latest_cache: Dict[int, int] = {}

        for (
            factory_id,
            factory_addr,
            last_block,
            ver_name,
            chain_id_db,
            chain_name,
            rpc_url,
            chain_last,
        ) in factories:
            if _shutdown:
                break

            # チェーン最新ブロックをリフレッシュ（キャッシュ利用）
            if chain_id_db not in latest_cache:
                latest_cache[chain_id_db] = await _refresh_chain_latest_block(
                    session, chain_id_db, rpc_url
                )
            chain_latest = latest_cache[chain_id_db]

            # get chain row
            chain = (
                await session.execute(select(Chain).where(Chain.id == chain_id_db))
            ).scalar_one_or_none()
            if not chain:
                print(f"[{chain_name}] chain id {chain_id_db} not found, skipping")
                continue

            # 上限ブロックの決定
            hard_upper = to_block if to_block is not None else chain_latest
            if daily:
                hard_upper = max(hard_upper - confirmations, 0)

            # ファクトリの開始点初期化（必要なら BQ で探す）
            last_block, created_block = await _ensure_factory_start_block(
                session, chain, factory_id, factory_addr, ver_name, int(last_block or 0)
            )
            is_v3 = "v3" in ver_name.lower()

            # from は CLI 指定が最優先、無ければ last+1
            cur_from = from_block if from_block is not None else (last_block + 1)

            # ✅ ここで **ファクトリ毎** に CHUNK を決める
            chunk_blocks = compute_chunk_blocks(hard_upper, created_block)
            print(
                f"[{chain.name}] factory={factory_addr} ({ver_name}) start_last={last_block}; "
                f"upper={hard_upper}; created={created_block}; chunk={chunk_blocks}"
            )

            # すでに最新ならスキップ
            if cur_from > hard_upper:
                print(
                    f"[{chain.name}] factory={factory_addr} up-to-date (last={last_block}, upper={hard_upper})"
                )
                continue

            print(
                f"[{chain.name}] factory={factory_addr} ({ver_name}) start_last={last_block}; upper={hard_upper}"
            )

            processed_total_logs = 0
            processed_total_pools = 0
            processed_total_tokens = 0
            t0_all = time.time()

            while cur_from <= hard_upper and not _shutdown:
                cur_to = min(cur_from + chunk_blocks - 1, hard_upper)

                t_fetch0 = time.time()
                try:
                    logs = await fetch_factory_logs_from_bq(
                        chain.big_query_table_id, factory_addr, is_v3, cur_from, cur_to
                    )
                except Exception as e:
                    print(
                        f"[{chain.name}] fetch logs failed {cur_from}-{cur_to}: {e} (skip chunk)"
                    )
                    # それでも進める（無駄取得防止のため cur_to まで前進）
                    await _update_last_gotten_block(session, factory_id, cur_to)
                    cur_from = cur_to + 1
                    continue

                dt_fetch = time.time() - t_fetch0
                print(
                    f"[{chain.name}] blocks {cur_from}-{cur_to}: fetched_logs={len(logs)} (in {dt_fetch:.2f}s)"
                )

                # デコード
                token_addrs: Set[str] = set()
                decoded: List[Dict[str, Any]] = []
                for row in logs:
                    try:
                        # デコード(for row in logs:)
                        if is_v3:
                            t0a, t1a, fee, tick, pool = decode_pool_created_v3(row)
                            decoded.append(
                                {
                                    "t0": t0a,
                                    "t1": t1a,
                                    "addr": pool,
                                    "blk": row.block_number,
                                    "tx": row.tx_hash,
                                    "tick": int(tick),
                                    "fee_bps": int(fee),
                                }
                            )
                            token_addrs.update([t0a, t1a])
                        else:
                            t0a, t1a, pair = decode_pair_created_v2(row)
                            decoded.append(
                                {
                                    "t0": t0a,
                                    "t1": t1a,
                                    "addr": pair,
                                    "blk": row.block_number,
                                    "tx": row.tx_hash,
                                    "tick": 0,
                                    "fee_bps": 3000,  # ★ v2は常に0.3% = 30bps
                                }
                            )
                            token_addrs.update([t0a, t1a])
                    except Exception as e:
                        print(f"[{chain.name}] decode error: {e} @ tx {row.tx_hash}")

                print(
                    f"[{chain.name}] blocks {cur_from}-{cur_to}: decoded={len(decoded)} unique_tokens={len(token_addrs)}"
                )

                # Token upsert（失敗しても次チャンクへ）
                try:
                    t1 = time.time()
                    addr_to_id = await upsert_tokens(
                        session, chain_id_db, token_addrs, rpc_url
                    )
                    dt_tokens = time.time() - t1
                    processed_total_tokens += len(token_addrs)
                    print(
                        f"[{chain.name}] blocks {cur_from}-{cur_to}: upserted_tokens={len(token_addrs)} (in {dt_tokens:.2f}s)"
                    )
                except Exception as e:
                    print(
                        f"[{chain.name}] token upsert failed {cur_from}-{cur_to}: {e}"
                    )
                    addr_to_id = {}

                # Pool upsert（失敗しても次チャンクへ）
                n_pools = 0
                try:
                    pool_rows: List[Dict[str, Any]] = []
                    for r in decoded:
                        t0_id = addr_to_id.get(_to_checksum(r["t0"]))
                        t1_id = addr_to_id.get(_to_checksum(r["t1"]))
                        if not (t0_id and t1_id):
                            continue
                        pool_rows.append(
                            {
                                "defi_factory_id": factory_id,
                                "chain_id": chain_id_db,
                                "token0_id": t0_id,
                                "token1_id": t1_id,
                                "address": _to_checksum(r["addr"]),
                                "created_block_number": int(r["blk"]),
                                "created_tx_hash": r["tx"],
                                "tick_spacing": int(r["tick"]),
                                "fee_tier_bps": int(r["fee_bps"]),
                            }
                        )
                    t2 = time.time()
                    n_pools = await upsert_pools(session, pool_rows)
                    dt_pools = time.time() - t2
                    processed_total_pools += n_pools
                    print(
                        f"[{chain.name}] blocks {cur_from}-{cur_to}: pools_upserted={n_pools} (in {dt_pools:.2f}s)"
                    )
                except Exception as e:
                    print(f"[{chain.name}] pool upsert failed {cur_from}-{cur_to}: {e}")

                processed_total_logs += len(logs)

                # ✅ チャンク完了チェックポイント
                # デコードできたものが0でも、無駄取得回避のため cur_to で前進させる
                max_blk = max([r["blk"] for r in decoded], default=cur_to)
                try:
                    await _update_last_gotten_block(session, factory_id, max_blk)
                    print(
                        f"[{chain.name}] progress: last_gotten_block_number -> {max_blk}"
                    )
                except Exception as e:
                    print(
                        f"[{chain.name}] update last_gotten_block_number failed at {max_blk}: {e}"
                    )

                # 次チャンク or 終了
                cur_from = cur_to + 1

            print(
                f"[{chain.name}] factory {factory_addr} ({ver_name}) "
                f"total_logs={processed_total_logs} total_pools={processed_total_pools} "
                f"total_tokens_seen={processed_total_tokens} elapsed={time.time() - t0_all:.2f}s"
            )

    print(f"[DONE] elapsed_total={time.time() - start_time:.2f}s")


# -------------- CLI ---------------- #
def _parse_args():
    p = argparse.ArgumentParser(description="Backfill AMM pools from BigQuery")
    p.add_argument(
        "--from",
        dest="from_block",
        type=int,
        default=None,
        help="start block (inclusive)",
    )
    p.add_argument(
        "--to", dest="to_block", type=int, default=None, help="end block (inclusive)"
    )
    p.add_argument(
        "--chain",
        dest="only_chain",
        type=str,
        default=None,
        help="Chain.name filter (e.g. Ethereum)",
    )
    p.add_argument(
        "--factory",
        dest="only_factory",
        type=str,
        default=None,
        help="factory address filter (ilike match)",
    )
    p.add_argument(
        "--confirmations",
        dest="confirmations",
        type=int,
        default=DEFAULT_CONFIRMS,
        help="tip confirmations",
    )
    p.add_argument(
        "--daily",
        action="store_true",
        help="use (latest - confirmations) as upper bound",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        backfill_all(
            from_block=args.from_block,
            to_block=args.to_block,
            only_chain=args.only_chain,
            only_factory=args.only_factory,
            confirmations=args.confirmations,
            daily=args.daily,
        )
    )
