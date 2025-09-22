from app.repositories.transaction_repository import TransactionRepository
from app.db.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends


def get_transaction_repository(
    session: AsyncSession = Depends(get_async_session),
) -> TransactionRepository:
    return TransactionRepository(session)
