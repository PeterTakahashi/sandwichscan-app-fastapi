from sqlalchemy.ext.asyncio import AsyncSession
from app.models.token import Token
from fastapi_repository import BaseRepository


class TokenRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Token)
