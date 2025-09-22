from app.repositories.swap_repository import SwapRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_swap_repository(
    session: AsyncSession = Depends(get_async_session),
) -> SwapRepository:
    return SwapRepository(session)
