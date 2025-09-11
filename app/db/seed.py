import asyncio
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.db.session import async_session_maker
from app.models.chain import Chain
from app.models.defi import Defi

# --- 設定 ---
CSV_CHAINS = Path("app/db/data/chains.csv")
CSV_DEFIS  = Path("app/db/data/defis.csv")

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
        required = {"chain_id", "name", "native_symbol", "native_decimals", "rpc_url"}
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
        required = {"name"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV header missing: {missing}")

        for r in reader:
            name = r["name"].strip()
            if not name:
                continue
            rows.append({"name": name})

    if not rows:
        return 0

    async with async_session_maker() as session:
        stmt = (
            pg_insert(Defi)
            .values(rows)
            .on_conflict_do_update(
                index_elements=[Defi.name],   # ← name に UNIQUE/PK が必要
                set_={
                    "name": pg_insert(Defi).excluded.name,
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

if __name__ == "__main__":
    asyncio.run(main())
