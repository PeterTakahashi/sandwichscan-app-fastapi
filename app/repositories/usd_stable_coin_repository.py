from sqlalchemy.ext.asyncio import AsyncSession
from app.models.usd_stable_coin import UsdStableCoin
from fastapi_repository import BaseRepository


class UsdStableCoinRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, UsdStableCoin)
