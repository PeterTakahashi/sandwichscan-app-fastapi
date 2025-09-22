from sqlalchemy.ext.asyncio import AsyncSession
from app.models.transaction import Transaction
from fastapi_repository import BaseRepository


class TransactionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Transaction)
