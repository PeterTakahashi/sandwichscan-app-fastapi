import asyncio
import csv
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import async_session_maker
from app.models.chain import Chain
from app.models.defi import Defi
from app.models.defi_version import DefiVersion
from app.models.defi_factory import DefiFactory

# --- 設定 ---
CSV_CHAINS = Path("app/db/data/chains.csv")
CSV_DEFIS = Path("app/db/data/defis.csv")
CSV_DEFI_VERSIONS = Path("app/db/data/defi_versions.csv")
CSV_DEFI_FACTORIES = Path("app/db/data/defi_factories.csv")


# CSV -> DB（chains: idempotent upsert）
async def import_chains_from_csv(csv_path: Path = CSV_CHAINS) -> int:
    macros: Dict[str, Optional[str]] = {
        "ALCHEMY_API_KEY": getattr(settings, "ALCHEMY_API_KEY", None),
    }

    def expand_macros(s: str) -> str:
        out = s
        for k, v in macros.items():
            if v:
                out = out.replace(f"{{{k}}}", v)
        return out

    rows: List[Dict] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {
            "chain_id",
            "name",
            "native_symbol",
            "native_decimals",
            "rpc_url",
            "usd_stable_coin_address",
            "logo_url",
            "big_query_table_id",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV header missing: {missing}")

        for r in reader:
            rows.append(
                {
                    "chain_id": int(r["chain_id"]),
                    "name": r["name"].strip(),
                    "native_symbol": r["native_symbol"].strip(),
                    "native_decimals": int(r["native_decimals"]),
                    "rpc_url": expand_macros(r["rpc_url"].strip()),
                    "usd_stable_coin_address": r["usd_stable_coin_address"].strip(),
                    "logo_url": r["logo_url"].strip(),
                    "big_query_table_id": r["big_query_table_id"].strip(),
                }
            )

    if not rows:
        return 0

    async with async_session_maker() as session:
        stmt = (
            pg_insert(Chain)
            .values(rows)
            .on_conflict_do_update(
                index_elements=[Chain.chain_id],
                set_={
                    "name": pg_insert(Chain).excluded.name,
                    "native_symbol": pg_insert(Chain).excluded.native_symbol,
                    "native_decimals": pg_insert(Chain).excluded.native_decimals,
                    "rpc_url": pg_insert(Chain).excluded.rpc_url,
                    "usd_stable_coin_address": pg_insert(
                        Chain
                    ).excluded.usd_stable_coin_address,
                    "logo_url": pg_insert(Chain).excluded.logo_url,
                    "big_query_table_id": pg_insert(Chain).excluded.big_query_table_id,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


# CSV -> DB（defis: idempotent upsert）
async def import_defis_from_csv(csv_path: Path = CSV_DEFIS) -> int:
    rows: List[Dict] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"name", "logo_url"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV header missing: {missing}")

        for r in reader:
            name = r["name"].strip()
            if not name:
                continue
            rows.append({"name": name, "logo_url": r["logo_url"].strip()})

    if not rows:
        return 0

    async with async_session_maker() as session:
        stmt = (
            pg_insert(Defi)
            .values(rows)
            .on_conflict_do_update(
                index_elements=[Defi.name],  # name UNIQUE
                set_={"name": pg_insert(Defi).excluded.name},
            )
        )
        await session.execute(stmt)
        await session.commit()
    return len(rows)


# CSV -> DB（defi_versions: idempotent upsert）
# csv: "name"（例: uniswap-v2, sushiswap-v3 ...）
# -> name から先頭の "uniswap" 等を切り出して defis.name を解決し、defi_id を埋める
async def import_defi_versions_from_csv(csv_path: Path = CSV_DEFI_VERSIONS) -> int:
    version_names: List[str] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"name"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV header missing: {missing}")
        for r in reader:
            nm = r["name"].strip()
            if nm:
                version_names.append(nm)

    if not version_names:
        return 0

    async with async_session_maker() as session:
        # defis map: name -> id
        defi_rows = (await session.execute(select(Defi.id, Defi.name))).all()
        defi_name_to_id = {name: did for (did, name) in defi_rows}

        # build rows
        rows: List[Dict] = []
        for vn in version_names:
            # 例: "uniswap-v2" -> "uniswap"
            defi_name = vn.split("-")[0].strip().lower()
            if defi_name not in defi_name_to_id:
                raise ValueError(
                    f"Defi '{defi_name}' not found for version '{vn}'. Import defis first."
                )
            rows.append({"defi_id": defi_name_to_id[defi_name], "name": vn})

        stmt = (
            pg_insert(DefiVersion)
            .values(rows)
            .on_conflict_do_update(
                index_elements=[DefiVersion.name],  # name UNIQUE
                set_={
                    "defi_id": pg_insert(DefiVersion).excluded.defi_id,
                    "name": pg_insert(DefiVersion).excluded.name,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()
        return len(rows)


# CSV -> DB（defi_factories: idempotent upsert）
# csv: chain_name,factory_address,defi_name,defi_version_name
# -> chain_name -> chains.id, defi_version_name -> defi_versions.id, address はユニーク
async def import_defi_factories_from_csv(csv_path: Path = CSV_DEFI_FACTORIES) -> int:
    rows_csv: List[Dict] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"chain_name", "factory_address", "defi_name", "defi_version_name"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV header missing: {missing}")
        for r in reader:
            chain_name = r["chain_name"].strip()
            address = r["factory_address"].strip()
            defi_name = r["defi_name"].strip()
            version_name = r["defi_version_name"].strip()
            if not (chain_name and address and defi_name and version_name):
                continue
            rows_csv.append(
                {
                    "chain_name": chain_name,
                    "address": address,
                    "defi_name": defi_name,
                    "version_name": version_name,
                }
            )

    if not rows_csv:
        return 0

    async with async_session_maker() as session:
        # chain map: name -> id
        chain_rows = (await session.execute(select(Chain.id, Chain.name))).all()
        chain_name_to_id = {name: cid for (cid, name) in chain_rows}

        # version map: name -> id（事前に defi_versions を取り込み済み前提）
        ver_rows = (
            await session.execute(select(DefiVersion.id, DefiVersion.name))
        ).all()
        ver_name_to_id = {name: vid for (vid, name) in ver_rows}

        # （任意チェック）defi_name の存在確認（CSV品質担保）
        defi_rows = (await session.execute(select(Defi.id, Defi.name))).all()
        defi_name_set = {name for (_id, name) in defi_rows}

        rows: List[Dict] = []
        for r in rows_csv:
            if r["chain_name"] not in chain_name_to_id:
                raise ValueError(
                    f"Chain '{r['chain_name']}' not found. Import chains first."
                )
            if r["version_name"] not in ver_name_to_id:
                raise ValueError(
                    f"DefiVersion '{r['version_name']}' not found. Import defi_versions first."
                )
            if r["defi_name"] not in defi_name_set:
                raise ValueError(
                    f"Defi '{r['defi_name']}' not found. Import defis first."
                )

            rows.append(
                {
                    "defi_version_id": ver_name_to_id[r["version_name"]],
                    "chain_id": chain_name_to_id[r["chain_name"]],
                    "address": r["address"],
                }
            )

        stmt = (
            pg_insert(DefiFactory)
            .values(rows)
            .on_conflict_do_update(
                constraint="uq_defi_factories_chain_address",
                set_={
                    "defi_version_id": pg_insert(DefiFactory).excluded.defi_version_id,
                    "chain_id": pg_insert(DefiFactory).excluded.chain_id,
                    "address": pg_insert(DefiFactory).excluded.address,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()
        return len(rows)


async def main():
    chains = await import_chains_from_csv()
    print(f"⬆️  Chains upserted: {chains} from {CSV_CHAINS}")

    defis = await import_defis_from_csv()
    print(f"⬆️  Defis upserted: {defis} from {CSV_DEFIS}")

    versions = await import_defi_versions_from_csv()
    print(f"⬆️  DefiVersions upserted: {versions} from {CSV_DEFI_VERSIONS}")

    factories = await import_defi_factories_from_csv()
    print(f"⬆️  DefiFactories upserted: {factories} from {CSV_DEFI_FACTORIES}")


if __name__ == "__main__":
    asyncio.run(main())
