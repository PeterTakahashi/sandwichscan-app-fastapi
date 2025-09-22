from typing import List
from sqlalchemy import text, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.transaction import Transaction
from app.db.session import async_session_maker
import asyncio

BATCH = 50_000
MAX_TRANSACTIONS = 71_606_221

# 1) 孤立transactionsのIDだけを取る
SELECT_TX_SWAPS = text(
    """
SELECT t.id AS tx_id, s.id AS swap_id
FROM transactions t
LEFT JOIN swaps s ON s.transaction_id = t.id
LIMIT :limit
"""
)


async def find_orphan_tx_ids(session: AsyncSession, limit: int) -> List[int]:
    rows = (await session.execute(SELECT_TX_SWAPS, {"limit": limit})).mappings().all()
    orphans = [r["tx_id"] for r in rows if r["swap_id"] is None]
    return orphans


# 2a) ORM版（小〜中規模）
async def delete_transactions_by_ids(session: AsyncSession, ids: List[int]) -> int:
    if not ids:
        return 0
    result = await session.execute(
        delete(Transaction).where(Transaction.id.in_(ids)).returning(Transaction.id)
    )
    return len(result.scalars().all())


# 2b) text + ANY（PostgreSQL高速版）
DELETE_TX_BY_IDS = text(
    """
DELETE FROM transactions
WHERE id = ANY(:ids)
RETURNING id
"""
)


async def delete_transactions_by_ids_fast(session: AsyncSession, ids: List[int]) -> int:
    if not ids:
        return 0
    result = await session.execute(DELETE_TX_BY_IDS, {"ids": ids})
    return len(result.scalars().all())


# 3) ループで枯れるまで削除
async def purge_orphan_transactions_loop(
    session: AsyncSession,
    batch: int = BATCH,
    use_fast: bool = True,  # PostgreSQLなら True 推奨
) -> int:
    total = 0
    loops = 0
    deleter = (
        delete_transactions_by_ids_fast if use_fast else delete_transactions_by_ids
    )

    while True:
        loops += 1
        ids = await find_orphan_tx_ids(session, batch)
        if not ids:
            break

        deleted = await deleter(session, ids)
        await session.commit()
        total += deleted
        print(f"[tx-purge] loop={loops} deleted={deleted} total={total}")

        if total >= MAX_TRANSACTIONS:
            print(f"[tx-purge] reached MAX_TRANSACTIONS limit: {MAX_TRANSACTIONS}")
            break

    return total


async def _main():
    async with async_session_maker() as db_session:
        total = await purge_orphan_transactions_loop(db_session, batch=50_000)
        print(f"[tx-purge] finished. total deleted = {total}")


if __name__ == "__main__":
    asyncio.run(_main())
