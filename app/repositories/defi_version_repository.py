from sqlalchemy.ext.asyncio import AsyncSession
from app.models.defi_version import DefiVersion
from fastapi_repository import BaseRepository


class DefiVersionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DefiVersion)
