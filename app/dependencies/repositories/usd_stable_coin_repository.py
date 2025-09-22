from app.repositories.usd_stable_coin_repository import UsdStableCoinRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_usd_stable_coin_repository(
    session: AsyncSession = Depends(get_async_session),
) -> UsdStableCoinRepository:
    return UsdStableCoinRepository(session)
