from fastapi import Depends, Request
from app.v1.schemas.sandwich_attack import (
    SandwichAttackListRead,
    SandwichAttackRead,
    SandwichAttackSearchParams,
    SandwichAttackReadByMonth,
)
from app.v1.dependencies.models.sandwich_attack.get_sandwich_attack_by_id import (
    get_sandwich_attack_by_id,
)
from app.v1.dependencies.services.sandwich_attack_service import (
    get_sandwich_attack_service,
)
from app.v1.services.sandwich_attack_service import SandwichAttackService
from app.models.sandwich_attack import SandwichAttack
from app.v1.dependencies.query_params.get_sandwich_attack_search_params import (
    get_sandwich_attack_search_params,
)

from app.core.routers.api_router import APIRouter

router = APIRouter(prefix="/sandwich_attacks", tags=["Sandwich Attacks"])


@router.get(
    "",
    response_model=SandwichAttackListRead,
    name="sandwich_attacks:list_sandwich_attacks",
)
async def list_sandwich_attacks(
    request: Request,
    search_params: SandwichAttackSearchParams = Depends(
        get_sandwich_attack_search_params
    ),
    service: SandwichAttackService = Depends(get_sandwich_attack_service),
):
    """
    Retrieve a list of sandwich_attacks with filtering, sorting, and pagination.
    """
    return await service.get_list(search_params=search_params)


@router.get(
    "/by_month",
    response_model=list[SandwichAttackReadByMonth],
    name="sandwich_attacks:read_by_month",
)
async def read_sandwich_attacks_by_month(
    request: Request,
    search_params: SandwichAttackSearchParams = Depends(
        get_sandwich_attack_search_params
    ),
    service: SandwichAttackService = Depends(get_sandwich_attack_service),
):
    """
    Retrieve a list of sandwich_attacks with filtering, sorting, and pagination.
    """
    return await service.get_read_by_month(search_params=search_params)


@router.get(
    "/{sandwich_attack_id}",
    response_model=SandwichAttackRead,
    name="sandwich_attacks:get_sandwich_attack",
)
async def get_sandwich_attack(
    sandwich_attack: SandwichAttack = Depends(get_sandwich_attack_by_id),
):
    """
    Retrieve an sandwich_attack by its ID.
    """
    return SandwichAttackRead.model_validate(sandwich_attack)
