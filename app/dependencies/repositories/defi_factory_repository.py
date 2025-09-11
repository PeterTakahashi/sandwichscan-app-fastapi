from app.repositories.defi_factory_repository import DefiFactoryRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_defi_factory_repository(
    session: AsyncSession = Depends(get_async_session),
) -> DefiFactoryRepository:
    return DefiFactoryRepository(session)
