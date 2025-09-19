from app.repositories.wrapped_native_token_repository import (
    WrappedNativeTokenRepository,
)
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_wrapped_native_token_repository(
    session: AsyncSession = Depends(get_async_session),
) -> WrappedNativeTokenRepository:
    return WrappedNativeTokenRepository(session)
