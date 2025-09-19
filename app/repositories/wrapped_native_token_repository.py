from sqlalchemy.ext.asyncio import AsyncSession
from app.models.wrapped_native_token import WrappedNativeToken
from fastapi_repository import BaseRepository


class WrappedNativeTokenRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, WrappedNativeToken)
