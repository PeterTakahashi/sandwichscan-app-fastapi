from app.repositories.sandwich_attack_repository import SandwichAttackRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_sandwich_attack_repository(
    session: AsyncSession = Depends(get_async_session),
) -> SandwichAttackRepository:
    return SandwichAttackRepository(session)
