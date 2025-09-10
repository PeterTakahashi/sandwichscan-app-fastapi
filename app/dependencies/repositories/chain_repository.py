from app.repositories.chain_repository import ChainRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_chain_repository(
    session: AsyncSession = Depends(get_async_session),
) -> ChainRepository:
    return ChainRepository(session)
