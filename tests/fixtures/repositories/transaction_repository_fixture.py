import pytest_asyncio
from app.repositories.transaction_repository import TransactionRepository


@pytest_asyncio.fixture
async def transaction_repository(async_session):
    return TransactionRepository(async_session)
