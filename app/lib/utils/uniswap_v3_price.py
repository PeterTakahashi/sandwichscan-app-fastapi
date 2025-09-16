from __future__ import annotations

from decimal import Decimal, getcontext

# Use high precision for price math
getcontext().prec = 60

Q96 = Decimal(2) ** 96


def price1_per_0_from_sqrt_price_x96(
    sqrt_price_x96: int | str, decimals0: int, decimals1: int
) -> Decimal:
    """
    Compute price of token1 denominated in token0 (1/0) using sqrtPriceX96.

    Adjusts for token decimals so that result is in human-readable units.
    price(1/0) = (sqrtPriceX96 / 2^96)^2 * 10^(decimals0 - decimals1)
    """
    sp = Decimal(int(sqrt_price_x96))
    ratio = (sp / Q96) ** 2
    adjustment = Decimal(10) ** Decimal(decimals0 - decimals1)
    return ratio * adjustment


def price1_per_0_from_tick(tick: int | str, decimals0: int, decimals1: int) -> Decimal:
    """
    Compute price of token1 denominated in token0 (1/0) using tick.

    price(1/0) = 1.0001^tick * 10^(decimals0 - decimals1)
    """
    ratio = Decimal(1.0001) ** Decimal(int(tick))
    adjustment = Decimal(10) ** Decimal(decimals0 - decimals1)
    return ratio * adjustment


def price_base_per_stable(
    *,
    base_is_token0: bool,
    decimals0: int,
    decimals1: int,
    tick: int | None,
    sqrt_price_x96: int | None,
) -> Decimal | None:
    """
    Given a Uniswap v3 pool price point and which side is the base token,
    compute the price of base in units of the other token (assumed stable/USD-like).

    Returns None if neither tick nor sqrt_price_x96 is available.
    """
    p1_per_0: Decimal | None = None
    if sqrt_price_x96 is not None:
        p1_per_0 = price1_per_0_from_sqrt_price_x96(sqrt_price_x96, decimals0, decimals1)
    elif tick is not None:
        p1_per_0 = price1_per_0_from_tick(tick, decimals0, decimals1)
    else:
        return None

    if base_is_token0:
        # Base = token0 → want USD per base = price(1/0)
        return p1_per_0
    else:
        # Base = token1 → want USD per base = price(0/1) = 1 / price(1/0)
        if p1_per_0 == 0:
            return None
        return Decimal(1) / p1_per_0

