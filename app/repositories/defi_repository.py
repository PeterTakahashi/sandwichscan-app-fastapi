from sqlalchemy.ext.asyncio import AsyncSession
from app.models.defi import Defi
from fastapi_repository import BaseRepository


class DefiRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Defi)
