from sqlalchemy.ext.asyncio import AsyncSession
from app.models.swap import Swap
from fastapi_repository import BaseRepository


class SwapRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Swap)
