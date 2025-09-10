from app.repositories.defi_repository import DefiRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_defi_repository(
    session: AsyncSession = Depends(get_async_session),
) -> DefiRepository:
    return DefiRepository(session)
