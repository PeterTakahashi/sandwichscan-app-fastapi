from app.repositories.chain_repository import ChainRepository
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_async_session


def get_chain_repository(
    session: AsyncSession = Depends(get_async_session),
) -> ChainRepository:
    return ChainRepository(session)
