import asyncio
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Iterable, Any, Set

from google.cloud import bigquery
from web3 import Web3
from eth_abi import decode as abi_decode
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import async_session_maker
from app.models import Chain, DefiFactory, DefiVersion, DefiPool, Token

# ---------- BigQuery dataset mapping ----------
BQ_LOGS_TABLE = {
    "Ethereum":  "bigquery-public-data.crypto_ethereum.logs",
    "BNB Chain": "public-data-finance.crypto_bsc.logs",
    "Polygon":   "public-data-finance.crypto_polygon.logs",
    "Base":      "public-data-finance.crypto_base.logs",
    "Arbitrum":  "public-data-finance.crypto_arbitrum.logs",
    "Avalanche": "public-data-finance.crypto_avalanche.logs",
}
# ---------- Event signatures ----------
SIG_PAIR_CREATED = Web3.keccak(text="PairCreated(address,address,address,uint256)").hex()
SIG_POOL_CREATED = Web3.keccak(text="PoolCreated(address,address,uint24,int24,address)").hex()

# ---------- Multicall3（多くのチェーンで共通デプロイ） ----------
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"

ERC20_ABI_DECIMALS = Web3.keccak(text="decimals()")[:4].hex()
ERC20_ABI_SYMBOL   = Web3.keccak(text="symbol()")[:4].hex()
ERC20_ABI_NAME     = Web3.keccak(text="name()")[:4].hex()

# multicall3 aggregate3((target,allowFailure,callData)[])
MC3_FUNC = Web3.keccak(text="aggregate3((address,bool,bytes)[])")[:4].hex()

def _to_checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)

def _strip_0x(s: str) -> str:
    return s[2:] if s.startswith("0x") else s

# ------------------ BigQuery helpers ------------------ #
@dataclass
class BqLogRow:
    data: str           # hex string 0x...
    topics: List[str]   # ["0x...", ...]
    block_number: int
    tx_hash: str

def bq_client() -> bigquery.Client:
    # 認証は GOOGLE_APPLICATION_CREDENTIALS に設定されたサービスアカウント
    return bigquery.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))

def build_bq_sql(logs_table: str, factory: str, topic0: str, from_block: Optional[int], to_block: Optional[int]) -> str:
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
    FROM `{logs_table}`
    WHERE {where_sql}
    ORDER BY block_number ASC
    """

async def fetch_factory_logs_from_bq(chain_name: str, factory_addr: str, is_v3: bool, from_block: Optional[int], to_block: Optional[int]) -> List[BqLogRow]:
    table = BQ_LOGS_TABLE.get(chain_name)
    if not table:
        return []
    sql = build_bq_sql(table, factory_addr, SIG_POOL_CREATED if is_v3 else SIG_PAIR_CREATED, from_block, to_block)
    client = bq_client()
    rs = client.query(sql)
    rows: List[BqLogRow] = []
    for r in rs:
        rows.append(BqLogRow(
            data=r["data"],
            topics=list(r["topics"]),
            block_number=int(r["block_number"]),
            tx_hash=r["transaction_hash"],
        ))
    return rows

# ------------------ Decoders ------------------ #
def decode_pair_created_v2(row: BqLogRow) -> Tuple[str, str, str]:
    """
    UniswapV2 PairCreated(address indexed token0, address indexed token1, address pair, uint)
    topics[1]=token0, topics[2]=token1, data= pair(32) + uint(32)
    """
    token0 = "0x" + _strip_0x(row.topics[1])[-40:]
    token1 = "0x" + _strip_0x(row.topics[2])[-40:]
    data = _strip_0x(row.data)
    # ABI: address is right-padded 32 bytes
    pair = "0x" + data[24:64]  # first 32 bytes, last 20 bytes are the address
    return _to_checksum(token0), _to_checksum(token1), _to_checksum(pair)

def decode_pool_created_v3(row: BqLogRow) -> Tuple[str, str, int, str]:
    """
    UniswapV3 PoolCreated(address token0, address token1, uint24 fee, int24 tickSpacing, address pool)
    all non-indexed -> topics[0] only. Decode `data`.
    """
    data_bin = bytes.fromhex(_strip_0x(row.data))
    token0, token1, fee, tick, pool = abi_decode(
        ["address", "address", "uint24", "int24", "address"], data_bin
    )
    return _to_checksum(token0), _to_checksum(token1), int(fee), _to_checksum(pool)

# ------------------ DB upsert helpers ------------------ #
async def upsert_tokens(session, chain_id_db: int, token_addrs: Iterable[str], rpc_url: str) -> Dict[str, int]:
    """
    token アドレス集合について decimals/symbol を Multicall3 で解決して tokens に upsert。
    return: {address -> token_id}
    """
    # 既存の tokens を引いて未解決を絞る
    addr_list = list({_to_checksum(a) for a in token_addrs})
    if not addr_list:
        return {}

    exist_rows = (await session.execute(
        select(Token.id, Token.address).where(Token.chain_id == chain_id_db, Token.address.in_(addr_list))
    )).all()
    existing = {addr: tid for (tid, addr) in exist_rows}

    targets = [a for a in addr_list if a not in existing]
    meta: Dict[str, Tuple[int, str]] = {}  # addr -> (decimals, symbol)

    if targets:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        mc = Web3.to_checksum_address(MULTICALL3)

        def encode_call(addr: str, selector_hex: str) -> bytes:
            return bytes.fromhex(_strip_0x(selector_hex))

        # aggregate3 calldata: function selector + abi-encoding of tuple[]
        # ここでは簡易に aggregate3 を 2 ラウンド（decimals, symbol）で呼ぶ
        def build_aggregate3_payload(calls: List[Tuple[str, bytes]]) -> bytes:
            # (address target, bool allowFailure, bytes callData)[]
            # ABI 手組みは煩雑なので、低依存にしたい場合は web3.py の Contract を使う実装に差し替えてOK
            from eth_abi import encode as abi_encode
            tuples = [(Web3.to_checksum_address(t), True, cd) for (t, cd) in calls]
            encoded = abi_encode([{"components":[
                {"name":"target","type":"address"},
                {"name":"allowFailure","type":"bool"},
                {"name":"callData","type":"bytes"}],
                "type":"tuple[]"}], [tuples])
            return bytes.fromhex(_strip_0x(MC3_FUNC)) + encoded

        # 1) decimals
        dec_calls = [(a, encode_call(a, ERC20_ABI_DECIMALS)) for a in targets]
        payload = build_aggregate3_payload(dec_calls)
        res = w3.eth.call({"to": mc, "data": payload})
        # decode: (success,bool, returnData,bytes)[]  -> aggregate3 returns (bool success, bytes returnData)[]
        from eth_abi import decode as abi_decode_
        results = abi_decode_([{"components":[
            {"name":"success","type":"bool"},
            {"name":"returnData","type":"bytes"}],
            "type":"tuple[]"}], res)[0]

        decimals_map: Dict[str, Optional[int]] = {}
        for i, (success, rdata) in enumerate(results):
            d = None
            if success and len(rdata) >= 32:
                try:
                    d = int.from_bytes(rdata[-32:], "big")  # uint8/uint256 どちらでもOK
                except Exception:
                    d = None
            decimals_map[targets[i]] = d

        # 2) symbol（文字列 or bytes32 の両対応）
        sym_calls = [(a, encode_call(a, ERC20_ABI_SYMBOL)) for a in targets]
        payload2 = build_aggregate3_payload(sym_calls)
        res2 = w3.eth.call({"to": mc, "data": payload2})
        results2 = abi_decode_([{"components":[
            {"name":"success","type":"bool"},
            {"name":"returnData","type":"bytes"}],
            "type":"tuple[]"}], res2)[0]

        for i, (success, rdata) in enumerate(results2):
            addr = targets[i]
            dec = decimals_map.get(addr)
            sym = "UNK"
            if success and len(rdata) >= 32:
                try:
                    # 動的 bytes の場合
                    # bytes の先頭 32 にオフセット、次に length、その後にデータ（左詰め）という典型
                    # 簡易に decode(string) をトライ
                    sym = abi_decode(["string"], rdata)[0]
                except Exception:
                    # bytes32 フォーマットの可能性
                    raw = rdata[-32:]
                    sym = raw.partition(b"\x00")[0].decode(errors="ignore") or "UNK"
            if dec is None:
                dec = 18  # 最低限のフォールバック
            meta[addr] = (int(dec), sym or "UNK")

        # upsert
        rows = [{"chain_id": chain_id_db, "address": a, "symbol": s, "decimals": d} for a,(d,s) in meta.items()]
        if rows:
            stmt = (
                pg_insert(Token)
                .values(rows)
                .on_conflict_do_update(
                    index_elements=[Token.address],  # 現行スキーマは address UNIQUE（将来は (chain_id,address) 推奨）
                    set_={"symbol": pg_insert(Token).excluded.symbol, "decimals": pg_insert(Token).excluded.decimals}
                )
            )
            await session.execute(stmt)
            await session.commit()

        # 取り直し
        exist_rows = (await session.execute(
            select(Token.id, Token.address).where(Token.chain_id == chain_id_db, Token.address.in_(addr_list))
        )).all()
        existing = {addr: tid for (tid, addr) in exist_rows}

    return existing  # address -> token_id

async def upsert_pools(session, pools: List[Dict[str, Any]]) -> int:
    if not pools:
        return 0
    stmt = (
        pg_insert(DefiPool)
        .values(pools)
        .on_conflict_do_nothing()  # address UNIQUE（将来は (chain_id,address) にするとより安全）
    )
    await session.execute(stmt)
    await session.commit()
    return len(pools)

# ------------------ Orchestrator ------------------ #
async def backfill_all(from_block: Optional[int] = None, to_block: Optional[int] = None):
    async with async_session_maker() as session:
        # join して Factory 情報を取得（どのチェーン/バージョンか）
        q = (
            select(DefiFactory.id, DefiFactory.address, DefiVersion.name, Chain.id, Chain.name, Chain.rpc_url)
            .join(DefiVersion, DefiVersion.id == DefiFactory.defi_version_id)
            .join(Chain, Chain.id == DefiFactory.chain_id)
        )
        factories = (await session.execute(q)).all()

        for defi_factory_id, factory_addr, ver_name, chain_id_db, chain_name, rpc_url in factories:
            is_v3 = "v3" in ver_name.lower()
            logs = await fetch_factory_logs_from_bq(chain_name, factory_addr, is_v3, from_block, to_block)
            if not logs:
                print(f"[{chain_name}] no logs via BQ for factory {factory_addr} ({ver_name})")
                continue

            token_addrs: Set[str] = set()
            decoded_rows: List[Tuple[str,str,Optional[int],str]] = []  # (t0,t1,fee_or_None,pool_addr)

            for row in logs:
                try:
                    if is_v3:
                        t0,t1,fee,pool = decode_pool_created_v3(row)
                        decoded_rows.append((t0,t1,fee,pool))
                        token_addrs.update([t0,t1])
                    else:
                        t0,t1,pair = decode_pair_created_v2(row)
                        decoded_rows.append((t0,t1,None,pair))
                        token_addrs.update([t0,t1])
                except Exception as e:
                    print(f"decode error: {e} @ tx {row.tx_hash}")
                    continue

            # Token を解決 & upsert
            addr_to_id = await upsert_tokens(session, chain_id_db, token_addrs, rpc_url)

            # Pool upsert rows
            pool_rows: List[Dict[str,Any]] = []
            for t0,t1,fee_or_none,pool_addr in decoded_rows:
                t0_id = addr_to_id.get(t0)
                t1_id = addr_to_id.get(t1)
                if not (t0_id and t1_id):
                    continue
                swap_fee = (fee_or_none / 1_000_000) if fee_or_none is not None else 0.003
                pool_rows.append({
                    "defi_factory_id": defi_factory_id,
                    "chain_id": chain_id_db,
                    "token0_id": t0_id,
                    "token1_id": t1_id,
                    "address": _to_checksum(pool_addr),
                    "swap_fee": swap_fee,
                })

            inserted = await upsert_pools(session, pool_rows)
            print(f"[{chain_name}] {ver_name} factory {factory_addr}: pools upserted={inserted}")

if __name__ == "__main__":
    # 例: 全期間（from_block/to_block を必要に応じて指定）
    asyncio.run(backfill_all())
