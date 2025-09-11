from sqlalchemy.ext.asyncio import AsyncSession
from app.models.defi_factory import DefiFactory
from fastapi_repository import BaseRepository


class DefiFactoryRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DefiFactory)
