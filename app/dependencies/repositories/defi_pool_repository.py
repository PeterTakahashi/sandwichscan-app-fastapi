from app.repositories.defi_pool_repository import DefiPoolRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_defi_pool_repository(
    session: AsyncSession = Depends(get_async_session),
) -> DefiPoolRepository:
    return DefiPoolRepository(session)
