from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.swap import Swap
from app.models.transaction import Transaction
from app.models.defi_pool import DefiPool
# from app.v1.services.sandwich_attack_service import (
#     create_sandwich_attack_if_pricable,
# )
from app.db.session import async_session_maker
import argparse
import asyncio

@dataclass
class SwapRow:
    id: int
    chain_id: int
    defi_pool_id: int
    sender: Optional[str]
    amount0_in_raw: int
    amount1_in_raw: int
    amount0_out_raw: int
    amount1_out_raw: int
    sell_token_id: Optional[int]
    buy_token_id: Optional[int]
    block_number: int
    log_index: int
    tx_from: Optional[str]
    gas_used: Optional[int]
    gas_price_wei_effective: Optional[int]
    gas_price_wei_legacy: Optional[int]


def _dir_token0_to_token1(s: SwapRow) -> bool:
    return int(s.amount0_in_raw) > 0 and int(s.amount1_out_raw) > 0 and int(s.amount1_in_raw) == 0 and int(s.amount0_out_raw) == 0


def _dir_token1_to_token0(s: SwapRow) -> bool:
    return int(s.amount1_in_raw) > 0 and int(s.amount0_out_raw) > 0 and int(s.amount0_in_raw) == 0 and int(s.amount1_out_raw) == 0


def _dir_sign(s: SwapRow, *, base_is_token0: bool) -> int:
    if base_is_token0:
        if _dir_token0_to_token1(s):
            return -1  # sell base
        if _dir_token1_to_token0(s):
            return +1  # buy base
    else:
        if _dir_token1_to_token0(s):
            return -1
        if _dir_token0_to_token1(s):
            return +1
    return 0


def _attacker_gas_fee_wei(front_attack_swap: SwapRow, back_attack_swap: SwapRow) -> Optional[int]:
    def pick(p: Optional[int], q: Optional[int]) -> Optional[int]:
        return p if p is not None else q

    total = 0
    known = False
    for s in (front_attack_swap, back_attack_swap):
        if s.gas_used is not None:
            gp = pick(
                s.gas_price_wei_effective, s.gas_price_wei_legacy
            )
            if gp is not None:
                total += int(s.gas_used) * int(gp)
                known = True
    return total if known else None


async def _fetch_pool_swaps(
    session: AsyncSession,
    *,
    defi_pool_id: int,
    min_block_number: Optional[int] = None,
    max_block_number: Optional[int] = None,
) -> list[SwapRow]:
    stmt = (
        select(
            Swap.id,
            Swap.chain_id,
            Swap.defi_pool_id,
            Swap.sender,
            Swap.amount0_in_raw,
            Swap.amount1_in_raw,
            Swap.amount0_out_raw,
            Swap.amount1_out_raw,
            Swap.sell_token_id,
            Swap.buy_token_id,
            Transaction.block_number,
            Swap.log_index,
            Transaction.from_address,
            Transaction.gas_used,
            Transaction.effective_gas_price_wei,
            Transaction.gas_price_wei,
        )
        .join(Transaction, Transaction.id == Swap.transaction_id)
        .where(Swap.defi_pool_id == defi_pool_id)
        .order_by(asc(Transaction.block_number), asc(Swap.log_index))
    )
    if min_block_number is not None:
        stmt = stmt.where(Transaction.block_number >= min_block_number)
    if max_block_number is not None:
        stmt = stmt.where(Transaction.block_number <= max_block_number)

    rows = (await session.execute(stmt)).all()
    out: list[SwapRow] = []
    for r in rows:
        out.append(
            SwapRow(
                id=int(r[0]),
                chain_id=int(r[1]),
                defi_pool_id=int(r[2]),
                sender=r[3],
                amount0_in_raw=int(r[4]),
                amount1_in_raw=int(r[5]),
                amount0_out_raw=int(r[6]),
                amount1_out_raw=int(r[7]),
                sell_token_id=int(r[8]) if r[8] is not None else None,
                buy_token_id=int(r[9]) if r[9] is not None else None,
                block_number=int(r[10]),
                log_index=int(r[11]),
                tx_from=r[12],
                gas_used=int(r[13]) if r[13] is not None else None,
                gas_price_wei_effective=int(r[14]) if r[14] is not None else None,
                gas_price_wei_legacy=int(r[15]) if r[15] is not None else None,
            )
        )
    return out


async def detect_and_insert_for_pool(
    session: AsyncSession,
    *,
    defi_pool_id: int,
    window_pre: int = 3,
    window_post: int = 3,
    max_block_gap: int = 2,
    min_victim_base_raw: int = 0,
    min_block_number: Optional[int] = None,
    max_block_number: Optional[int] = None,
) -> int:
    """
    Detect sandwich attacks within a single pool (front_attack -> victim -> back_attack).
    Returns number of detected rows (not inserting while testing).
    Conditions:
      - front_attack before victim, back_attack after victim, same attacker (EOA tx_from)
      - front/back are opposite directions relative to base (base = front_attack.sell_token_id)
      - victim lies between the two in block order, and block gap <= max_block_gap
      - victim base amount >= threshold
    Note: harm_base_raw is set to 0 for now (no reserve snapshots available).
    """
    # Ensure pool exists (and to get token0/token1 if we need later)
    pool_row = await session.execute(select(DefiPool).where(DefiPool.id == defi_pool_id))
    pool = pool_row.scalars().first()
    if not pool:
        return 0

    swaps = await _fetch_pool_swaps(
        session,
        defi_pool_id=defi_pool_id,
        min_block_number=min_block_number,
        max_block_number=max_block_number,
    )
    total_swaps = len(swaps)
    detected_count = 0

    for victim_idx in range(total_swaps):
        victim_swap = swaps[victim_idx]
        # scan window before and after
        pre_start = max(0, victim_idx - window_pre)
        post_end = min(total_swaps, victim_idx + 1 + window_post)

        for front_idx in range(pre_start, victim_idx):
            front_attack_swap = swaps[front_idx]
            # Determine EOA actors (prefer tx_from over event sender which is often a router)
            victim_actor = (victim_swap.tx_from or victim_swap.sender or "").lower()
            attacker_actor = (front_attack_swap.tx_from or front_attack_swap.sender or "").lower()
            # skip if victim and A1 are the same EOA
            if attacker_actor == victim_actor:
                continue

            # base definition
            base_token_id = front_attack_swap.sell_token_id
            if base_token_id is None:
                continue
            base_is_token0 = (base_token_id == pool.token0_id)
            if not base_is_token0 and base_token_id != pool.token1_id:
                # inconsistent data
                continue

            dir_front = _dir_sign(front_attack_swap, base_is_token0=base_is_token0)
            if dir_front == 0:
                continue

            # victim must be trading in the same direction as the front-run
            dir_victim = _dir_sign(victim_swap, base_is_token0=base_is_token0)
            if dir_victim == 0 or dir_victim != dir_front:
                continue

            # Ensure the actual token being bought matches when IDs are available
            if (
                front_attack_swap.buy_token_id is not None
                and victim_swap.buy_token_id is not None
                and front_attack_swap.buy_token_id != victim_swap.buy_token_id
            ):
                continue

            # Ensure the actual token being sold matches when IDs are available
            if (
                front_attack_swap.sell_token_id is not None
                and victim_swap.sell_token_id is not None
                and front_attack_swap.sell_token_id != victim_swap.sell_token_id
            ):
                continue

            for back_idx in range(victim_idx + 1, post_end):
                back_attack_swap = swaps[back_idx]
                back_actor = (back_attack_swap.tx_from or back_attack_swap.sender or "").lower()
                # attacker must match A1 EOA
                if back_actor != attacker_actor:
                    continue

                # block gap constraint
                if abs(int(back_attack_swap.block_number) - int(front_attack_swap.block_number)) > max_block_gap:
                    continue

                # V must be between A1 and A2 in block order
                if not (min(front_attack_swap.block_number, back_attack_swap.block_number) <= victim_swap.block_number <= max(front_attack_swap.block_number, back_attack_swap.block_number)):
                    continue

                dir_back = _dir_sign(back_attack_swap, base_is_token0=base_is_token0)
                if dir_back == 0 or dir_back != -dir_front:
                    continue

                # victim base size threshold
                victim_base_size_raw = max(victim_swap.amount0_in_raw, victim_swap.amount0_out_raw) if base_is_token0 else max(victim_swap.amount1_in_raw, victim_swap.amount1_out_raw)
                if int(victim_base_size_raw) <= int(min_victim_base_raw):
                    continue

                # profit calculation (closed round-trip)
                if base_is_token0:
                    if _dir_token0_to_token1(front_attack_swap) and _dir_token1_to_token0(back_attack_swap):
                        profit_base_raw = int(back_attack_swap.amount0_out_raw) - int(front_attack_swap.amount0_in_raw)
                    else:
                        continue
                else:
                    if _dir_token1_to_token0(front_attack_swap) and _dir_token0_to_token1(back_attack_swap):
                        profit_base_raw = int(back_attack_swap.amount1_out_raw) - int(front_attack_swap.amount1_in_raw)
                    else:
                        continue

                # gas for attacker legs
                gas_fee_wei_attacker = _attacker_gas_fee_wei(front_attack_swap, back_attack_swap)
                if gas_fee_wei_attacker is None:
                    # pricing requires ETHUSD; but we could still save if we choose.
                    # As per policy, skip if we cannot compute cost.
                    continue

                # victim harm not implemented yet (no reserves snapshot)
                harm_base_raw = 0

                attacker_address = attacker_actor
                victim_address = victim_actor

                # Insert only if pricing available
                # isolate each insert so duplicates don't rollback the whole batch

                detected_count += 1
                print(
                    "Detected sandwich attack: "
                    f"pool={defi_pool_id} "
                    f"front_attack_swap_id={front_attack_swap.id} "
                    f"victim_swap_id={victim_swap.id} "
                    f"back_attack_swap_id={back_attack_swap.id} "
                    f"attacker={attacker_address} victim={victim_address} "
                    f"profit_base_raw={profit_base_raw} harm_base_raw={harm_base_raw} "
                    f"gas_fee_wei_attacker={gas_fee_wei_attacker}"
                )
                # async with session.begin_nested():
                #     created = await create_sandwich_attack_if_pricable(
                #         session,
                #         chain_id=victim_swap.chain_id,
                #         front_attack_swap_id=front_attack_swap.id,
                #         victim_swap_id=victim_swap.id,
                #         back_attack_swap_id=back_attack_swap.id,
                #         attacker_address=attacker_address,
                #         victim_address=victim_address,
                #         victim_base_size_raw=int(victim_base_size_raw),
                #         profit_base_raw=int(profit_base_raw),
                #         harm_base_raw=int(harm_base_raw),
                #         gas_fee_wei_attacker=int(gas_fee_wei_attacker),
                #     )
                #     if created is not None:
                #         inserted += 1

    return detected_count


def _build_arg_parser():
    ap = argparse.ArgumentParser(description="Detect and insert sandwich attacks for a pool")
    ap.add_argument("--pool-id", type=int, required=True, help="Target defi_pool.id")
    ap.add_argument("--window-pre", type=int, default=3, help="Search window size before victim")
    ap.add_argument("--window-post", type=int, default=3, help="Search window size after victim")
    ap.add_argument("--max-block-gap", type=int, default=2, help="Max block gap between A1 and A2")
    ap.add_argument("--min-victim-base-raw", type=int, default=0, help="Min victim base size (raw)")
    ap.add_argument("--min-block", type=int, default=None, help="Min block number to scan")
    ap.add_argument("--max-block", type=int, default=None, help="Max block number to scan")
    return ap


async def _main_async(args) -> int:
    async with async_session_maker() as session:
        inserted = await detect_and_insert_for_pool(
            session,
            defi_pool_id=args.pool_id,
            window_pre=args.window_pre,
            window_post=args.window_post,
            max_block_gap=args.max_block_gap,
            min_victim_base_raw=args.min_victim_base_raw,
            min_block_number=args.min_block,
            max_block_number=args.max_block,
        )
        await session.commit()
        return inserted


def main():
    ap = _build_arg_parser()
    args = ap.parse_args()
    detected = asyncio.run(_main_async(args))
    print(f"Detected {detected} sandwich attacks for pool {args.pool_id}")


if __name__ == "__main__":
    main()
