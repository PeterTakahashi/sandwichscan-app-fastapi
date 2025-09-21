from typing import Optional
from fastapi import Query
from datetime import datetime
from app.v1.schemas.sandwich_attack.search_params import (
    SandwichAttackSearchParams,
)


def get_sandwich_attack_search_params(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sorted_by: str = Query("block_timestamp"),
    sorted_order: str = Query("desc"),
    chain_id__in: Optional[list[str]] = Query(None),
    defi_version_id__in: Optional[list[str]] = Query(None),
    victim_address__exact__or__attacker_address__exact: Optional[str] = Query(None),
    victim_address__exact: Optional[str] = Query(None),
    attacker_address__exact: Optional[str] = Query(None),
    revenue_base_raw__gte: Optional[int] = Query(None, ge=0),
    revenue_base_raw__lte: Optional[int] = Query(None, ge=0),
    profit_base_raw__gte: Optional[int] = Query(None, ge=0),
    profit_base_raw__lte: Optional[int] = Query(None, ge=0),
    harm_base_raw__gte: Optional[int] = Query(None, ge=0),
    harm_base_raw__lte: Optional[int] = Query(None, ge=0),
    gas_fee_wei_attacker__gte: Optional[int] = Query(None, ge=0),
    gas_fee_wei_attacker__lte: Optional[int] = Query(None, ge=0),
    created_at__gte: Optional[datetime] = Query(None),
    created_at__lte: Optional[datetime] = Query(None),
    updated_at__gte: Optional[datetime] = Query(None),
    updated_at__lte: Optional[datetime] = Query(None),
    block_timestamp__gte: Optional[datetime] = Query(None),
    block_timestamp__lte: Optional[datetime] = Query(None),
) -> SandwichAttackSearchParams:
    return SandwichAttackSearchParams(
        limit=limit,
        offset=offset,
        sorted_by=sorted_by,
        sorted_order=sorted_order,
        defi_version_id__in=defi_version_id__in,
        chain_id__in=chain_id__in,
        victim_address__exact__or__attacker_address__exact=victim_address__exact__or__attacker_address__exact,
        victim_address__exact=victim_address__exact,
        attacker_address__exact=attacker_address__exact,
        revenue_base_raw__gte=revenue_base_raw__gte,
        revenue_base_raw__lte=revenue_base_raw__lte,
        profit_base_raw__gte=profit_base_raw__gte,
        profit_base_raw__lte=profit_base_raw__lte,
        harm_base_raw__gte=harm_base_raw__gte,
        harm_base_raw__lte=harm_base_raw__lte,
        gas_fee_wei_attacker__gte=gas_fee_wei_attacker__gte,
        gas_fee_wei_attacker__lte=gas_fee_wei_attacker__lte,
        created_at__gte=created_at__gte,
        created_at__lte=created_at__lte,
        updated_at__gte=updated_at__gte,
        updated_at__lte=updated_at__lte,
        block_timestamp__gte=block_timestamp__gte,
        block_timestamp__lte=block_timestamp__lte,
    )
