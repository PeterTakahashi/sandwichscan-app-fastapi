from app.v1.repositories.token_repository import TokenRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_token_repository(
    session: AsyncSession = Depends(get_async_session),
) -> TokenRepository:
    return TokenRepository(session)
