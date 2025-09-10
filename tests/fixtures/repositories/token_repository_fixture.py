import pytest_asyncio
from app.v1.repositories.token_repository import TokenRepository


@pytest_asyncio.fixture
async def token_repository(async_session):
    return TokenRepository(async_session)
