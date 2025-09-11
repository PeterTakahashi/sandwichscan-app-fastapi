import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from eth_abi import decode as abi_decode
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from web3 import Web3

from app.db.session import async_session_maker
from app.lib.utils.bq_client import bq_client
from app.models import Chain, DefiFactory, DefiPool, DefiVersion, Token

# ---------------- Tunables (バッチ設定) ---------------- #
MAX_IN_PARAMS = 10_000   # IN句の分割サイズ（asyncpgの32767上限に十分マージン）
UPSERT_BATCH  = 10    # tokens / pools のUPSERT単位
MC_BATCH      = 250      # Multicall1回のトークン数（RPCサイズ対策）

def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i+size]

# ---------------- BigQuery datasets (logs の完全修飾テーブル名) ---------------- #
BQ_LOGS_TABLE = {
    "Ethereum":  "bigquery-public-data.goog_blockchain_ethereum_mainnet_us.logs",
    "Arbitrum":  "bigquery-public-data.goog_blockchain_arbitrum_one_us.logs",
    "Avalanche": "bigquery-public-data.goog_blockchain_avalanche_mainnet_us.logs",
    "Polygon":   "bigquery-public-data.goog_blockchain_polygon_mainnet_us.logs",
    # Base/BNBなどは goog_blockchain_* に無いので必要なら public-data-finance.* を別途足す
}

# ---------------- Event signatures (0x付きで) ---------------- #
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
SEL_SYMBOL   = Web3.keccak(text="symbol()")[:4].hex()
MC3_SELECTOR = Web3.keccak(text="aggregate3((address,bool,bytes)[])")[:4].hex()

def _to_checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)

def _strip_0x(s: str) -> str:
    return s[2:] if s.startswith("0x") else s

@dataclass
class BqLogRow:
    data: str
    topics: List[str]
    block_number: int
    tx_hash: str

def build_logs_sql(
    table: str,
    factory: str,
    topic0: str,
    from_block: Optional[int],
    to_block: Optional[int],
) -> str:
    where = [
        f"address = '{factory.lower()}'",      # データは小文字格納なのでLOWER()不要
        f"topics[OFFSET(0)] = '{topic0}'",     # 0x付きのkeccakシグネチャ
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

async def fetch_factory_logs_from_bq(
    chain_name: str,
    factory_addr: str,
    is_v3: bool,
    from_block: Optional[int],
    to_block: Optional[int],
) -> List[BqLogRow]:
    table = BQ_LOGS_TABLE.get(chain_name)
    if not table:
        return []
    topic0 = SIG_POOL_CREATED if is_v3 else SIG_PAIR_CREATED
    sql = build_logs_sql(table, factory_addr, topic0, from_block, to_block)

    client = bq_client()
    job = client.query(sql)
    rows: List[BqLogRow] = []
    for r in job:  # RowIterator
        rows.append(
            BqLogRow(
                data=r["data"],
                topics=list(r["topics"]),
                block_number=int(r["block_number"]),
                tx_hash=r["transaction_hash"],
            )
        )
    return rows

# ---------------- Decoders ---------------- #
def decode_pair_created_v2(row: BqLogRow) -> Tuple[str, str, str]:
    # PairCreated(address indexed token0, address indexed token1, address pair, uint)
    token0 = "0x" + _strip_0x(row.topics[1])[-40:]
    token1 = "0x" + _strip_0x(row.topics[2])[-40:]
    data_hex = _strip_0x(row.data)
    pair = "0x" + data_hex[24:64]  # 先頭32Bの末尾20B
    return _to_checksum(token0), _to_checksum(token1), _to_checksum(pair)

def decode_pool_created_v3(row: BqLogRow) -> Tuple[str, str, int, int, str]:
    # PoolCreated(address token0, address token1, uint24 fee, int24 tickSpacing, address pool)
    data_bin = bytes.fromhex(_strip_0x(row.data))
    token0, token1, fee, tick, pool = abi_decode(
        ["address", "address", "uint24", "int24", "address"], data_bin
    )
    return (
        _to_checksum(token0),
        _to_checksum(token1),
        int(fee),
        int(tick),
        _to_checksum(pool),
    )

# ---------------- Token upsert via Multicall3 (分割対応) ---------------- #
async def upsert_tokens(
    session, chain_id_db: int, token_addrs: Iterable[str], rpc_url: str
) -> Dict[str, int]:
    addr_list = list({_to_checksum(a) for a in token_addrs})
    if not addr_list:
        return {}

    # 既存トークン取得（IN句を分割）
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
        encoded = abi_encode(['(address,bool,bytes)[]'], [tuples])
        return bytes.fromhex(_strip_0x(MC3_SELECTOR)) + encoded

    resolved: Dict[str, Tuple[int, str]] = {}

    # バッチで Multicall
    from eth_abi import decode as abi_decode_inner
    for tchunk in chunked(targets, MC_BATCH):
        # 1) decimals
        dec_calls = [(a, _encode(SEL_DECIMALS)) for a in tchunk]
        payload_dec = _build_aggregate3_payload(dec_calls)
        res_dec = w3.eth.call({"to": MULTICALL3, "data": payload_dec})
        dec_results = abi_decode_inner(['(bool,bytes)[]'], res_dec)[0]
        dec_map: Dict[str, Optional[int]] = {}
        for i, (ok, rdata) in enumerate(dec_results):
            d = None
            if ok and len(rdata) >= 32:
                try:
                    d = int.from_bytes(rdata[-32:], "big")
                except Exception:
                    d = None
            dec_map[tchunk[i]] = d

        # 2) symbol
        sym_calls = [(a, _encode(SEL_SYMBOL)) for a in tchunk]
        payload_sym = _build_aggregate3_payload(sym_calls)
        res_sym = w3.eth.call({"to": MULTICALL3, "data": payload_sym})
        sym_results = abi_decode_inner(['(bool,bytes)[]'], res_sym)[0]

        for i, (ok, rdata) in enumerate(sym_results):
            addr = tchunk[i]
            dec = dec_map.get(addr) if dec_map.get(addr) is not None else 18
            sym = "UNK"
            if ok and len(rdata) >= 32:
                try:
                    sym = abi_decode(["string"], rdata)[0]
                except Exception:
                    raw = rdata[-32:]
                    sym = raw.partition(b"\x00")[0].decode(errors="ignore") or "UNK"
            resolved[addr] = (int(dec), sym)

    # UPSERT（分割）
    rows = [
        {"chain_id": chain_id_db, "address": a, "symbol": s, "decimals": d}
        for a, (d, s) in resolved.items()
    ]
    for rchunk in chunked(rows, UPSERT_BATCH):
        stmt = (
            pg_insert(Token)
            .values(rchunk)
            .on_conflict_do_update(
                constraint="uq_tokens_chain_address",  # (chain_id, address)
                set_={
                    "symbol": pg_insert(Token).excluded.symbol,
                    "decimals": pg_insert(Token).excluded.decimals,
                },
            )
        )
        await session.execute(stmt)
    await session.commit()

    # 取り直し（IN句を分割）
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

# ---------------- Pools upsert (分割) ---------------- #
async def upsert_pools(session, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    total = 0
    for rchunk in chunked(rows, UPSERT_BATCH):
        stmt = (
            pg_insert(DefiPool)
            .values(rchunk)
            .on_conflict_do_update(
                constraint="uq_defi_pools_chain_address",  # (chain_id, address)
                set_={
                    "defi_factory_id": pg_insert(DefiPool).excluded.defi_factory_id,
                    "token0_id": pg_insert(DefiPool).excluded.token0_id,
                    "token1_id": pg_insert(DefiPool).excluded.token1_id,
                    "created_block_number": pg_insert(DefiPool).excluded.created_block_number,
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

# ---------------- Orchestrator ---------------- #
async def backfill_all(from_block: Optional[int] = None, to_block: Optional[int] = None):
    async with async_session_maker() as session:
        q = (
            select(
                DefiFactory.id,
                DefiFactory.address,
                DefiVersion.name,
                Chain.id,
                Chain.name,
                Chain.rpc_url,
            )
            .join(DefiVersion, DefiVersion.id == DefiFactory.defi_version_id)
            .join(Chain, Chain.id == DefiFactory.chain_id)
        )
        factories = (await session.execute(q)).all()

        for defi_factory_id, factory_addr, ver_name, chain_id_db, chain_name, rpc_url in factories:
            print(f"[{chain_name}] processing factory {factory_addr} ({ver_name}) ...")
            is_v3 = "v3" in ver_name.lower()

            logs = await fetch_factory_logs_from_bq(
                chain_name, factory_addr, is_v3, from_block, to_block
            )
            if not logs:
                print(f"[{chain_name}] no logs via BQ for factory {factory_addr} ({ver_name})")
                continue

            token_addrs: Set[str] = set()
            decoded: List[Dict[str, Any]] = []

            for row in logs:
                try:
                    if is_v3:
                        t0, t1, fee, tick, pool = decode_pool_created_v3(row)
                        fee_bps = fee // 100  # 500/3000/10000 -> 5/30/100 (bps単位)
                        decoded.append(
                            {
                                "t0": t0, "t1": t1, "addr": pool,
                                "blk": row.block_number, "tx": row.tx_hash,
                                "tick": int(tick), "fee_bps": int(fee_bps),
                            }
                        )
                        token_addrs.update([t0, t1])
                    else:
                        t0, t1, pair = decode_pair_created_v2(row)
                        decoded.append(
                            {
                                "t0": t0, "t1": t1, "addr": pair,
                                "blk": row.block_number, "tx": row.tx_hash,
                                "tick": 0, "fee_bps": 0,
                            }
                        )
                        token_addrs.update([t0, t1])
                except Exception as e:
                    print(f"decode error: {e} @ tx {row.tx_hash}")
                    continue

            addr_to_id = await upsert_tokens(session, chain_id_db, token_addrs, rpc_url)

            pool_rows: List[Dict[str, Any]] = []
            for r in decoded:
                t0_id = addr_to_id.get(_to_checksum(r["t0"]))
                t1_id = addr_to_id.get(_to_checksum(r["t1"]))
                if not (t0_id and t1_id):
                    continue
                pool_rows.append(
                    {
                        "defi_factory_id": defi_factory_id,
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

            n = await upsert_pools(session, pool_rows)
            print(f"[{chain_name}] {ver_name} factory {factory_addr}: pools upserted={n}")

if __name__ == "__main__":
    asyncio.run(backfill_all())
