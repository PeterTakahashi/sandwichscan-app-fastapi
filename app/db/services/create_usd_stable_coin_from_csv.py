import asyncio
import csv
from pathlib import Path
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session_maker
from app.models import Chain, Token, UsdStableCoin

CSV_USD_STABLE_COINS = Path("app/db/data/usd_stable_coins.csv")


async def import_usd_stable_coins_from_csv(
    csv_path: Path = CSV_USD_STABLE_COINS,
) -> int:
    rows_csv: List[Dict] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"chain_name", "usd_stable_coin_address", "priority"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV header missing: {missing}")
        for r in reader:
            chain_name = r["chain_name"].strip()
            addr = r["usd_stable_coin_address"].strip()
            priority = int(r["priority"].strip())
            if not (chain_name and addr):
                continue
            rows_csv.append(
                {"chain_name": chain_name, "address": addr, "priority": priority}
            )

    if not rows_csv:
        return 0

    async with async_session_maker() as session:
        # chain map
        chain_rows = (await session.execute(select(Chain.id, Chain.name))).all()
        chain_name_to_id = {name: cid for (cid, name) in chain_rows}

        # token map: (chain_id, address_lower) -> id
        token_rows = (
            await session.execute(select(Token.id, Token.chain_id, Token.address))
        ).all()
        token_map = {(cid, addr.lower()): tid for (tid, cid, addr) in token_rows}

        inserts: List[Dict] = []
        for r in rows_csv:
            if r["chain_name"] not in chain_name_to_id:
                print(f"[warn] chain '{r['chain_name']}' not found, skip")
                continue
            chain_id = chain_name_to_id[r["chain_name"]]
            token_id = token_map.get((chain_id, r["address"].lower()))
            priority = r["priority"]
            if not token_id:
                print(
                    f"[warn] token {r['address']} not found for chain {r['chain_name']} "
                    f"(import tokens first)"
                )
                continue
            inserts.append(
                {"chain_id": chain_id, "token_id": token_id, "priority": priority}
            )

        if not inserts:
            return 0

        stmt = (
            pg_insert(UsdStableCoin)
            .values(inserts)
            .on_conflict_do_update(
                constraint="uq_usd_stable_coins_chain_token",
                set_={"priority": pg_insert(UsdStableCoin).excluded.priority},
            )
        )
        await session.execute(stmt)
        await session.commit()
        return len(inserts)


async def main():
    n = await import_usd_stable_coins_from_csv()
    print(f"⬆️  UsdStableCoins upserted: {n} from {CSV_USD_STABLE_COINS}")


if __name__ == "__main__":
    asyncio.run(main())
