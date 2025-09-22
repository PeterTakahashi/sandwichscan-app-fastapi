import pytest_asyncio
from app.repositories.defi_pool_repository import DefiPoolRepository


@pytest_asyncio.fixture
async def defi_pool_repository(async_session):
    return DefiPoolRepository(async_session)
