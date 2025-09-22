from app.repositories.defi_version_repository import DefiVersionRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_defi_version_repository(
    session: AsyncSession = Depends(get_async_session),
) -> DefiVersionRepository:
    return DefiVersionRepository(session)
