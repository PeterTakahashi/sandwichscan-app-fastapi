from typing import List, Optional
from sqlalchemy import text, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.swap import Swap
from app.db.session import async_session_maker
import asyncio

BATCH = 50_000

# 1) 孤立swapsのIDだけを取る
SELECT_ORPHAN_IDS = text(
    """
SELECT s.id
FROM swaps s
LEFT JOIN sandwich_attacks sa
  ON sa.front_attack_swap_id = s.id
  OR sa.victim_swap_id      = s.id
  OR sa.back_attack_swap_id = s.id
WHERE sa.id IS NULL
ORDER BY s.id
LIMIT :limit
"""
)


async def find_orphan_swap_ids(session: AsyncSession, limit: int) -> List[int]:
    rows = (await session.execute(SELECT_ORPHAN_IDS, {"limit": limit})).scalars().all()
    return list(rows)


# 2a) ORM版（小〜中規模）
async def delete_swaps_by_ids(session: AsyncSession, ids: List[int]) -> int:
    if not ids:
        return 0
    result = await session.execute(
        delete(Swap).where(Swap.id.in_(ids)).returning(Swap.id)
    )
    return len(result.scalars().all())


# 2b) text + ANY（PostgreSQL高速版）
DELETE_BY_IDS = text(
    """
DELETE FROM swaps
WHERE id = ANY(:ids)
RETURNING id
"""
)


async def delete_swaps_by_ids_fast(session: AsyncSession, ids: List[int]) -> int:
    if not ids:
        return 0
    result = await session.execute(DELETE_BY_IDS, {"ids": ids})
    return len(result.scalars().all())


# 3) ループで枯れるまで削除
async def purge_orphan_swaps_loop(
    session: AsyncSession,
    batch: int = BATCH,
    max_loops: Optional[int] = None,  # 保険で上限回数を入れられる
    use_fast: bool = True,  # PostgreSQLなら True 推奨
) -> int:
    total = 0
    loops = 0
    deleter = delete_swaps_by_ids_fast if use_fast else delete_swaps_by_ids

    while True:
        loops += 1
        ids = await find_orphan_swap_ids(session, batch)
        if not ids:
            # これ以上削除対象がない
            break

        deleted = await deleter(session, ids)
        await session.commit()
        total += deleted
        print(f"[purge] loop={loops} deleted={deleted} total={total}")

        # バッチ未満しか削除できなければ在庫切れ
        if deleted < batch:
            break

        # ループ上限（任意）
        if max_loops is not None and loops >= max_loops:
            print(f"[purge] reached max_loops={max_loops}, stop.")
            break

    return total


async def _main():
    async with async_session_maker() as db_session:
        total = await purge_orphan_swaps_loop(db_session, batch=50_000)
        print(f"[purge] finished. total deleted = {total}")


if __name__ == "__main__":
    asyncio.run(_main())
