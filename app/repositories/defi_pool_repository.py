from sqlalchemy.ext.asyncio import AsyncSession
from app.models.defi_pool import DefiPool
from fastapi_repository import BaseRepository


class DefiPoolRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DefiPool)
