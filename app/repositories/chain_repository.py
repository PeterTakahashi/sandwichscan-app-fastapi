from sqlalchemy.ext.asyncio import AsyncSession
from app.models.chain import Chain
from fastapi_repository import BaseRepository


class ChainRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Chain)
