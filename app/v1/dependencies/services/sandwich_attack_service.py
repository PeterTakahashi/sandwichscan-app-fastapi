from fastapi import Depends
from app.v1.services.sandwich_attack_service import SandwichAttackService
from app.repositories.sandwich_attack_repository import SandwichAttackRepository
from app.dependencies.repositories.sandwich_attack_repository import (
    get_sandwich_attack_repository,
)


def get_sandwich_attack_service(
    sandwich_attack_repository: SandwichAttackRepository = Depends(
        get_sandwich_attack_repository
    ),
) -> SandwichAttackService:
    return SandwichAttackService(
        sandwich_attack_repository=sandwich_attack_repository,
    )
