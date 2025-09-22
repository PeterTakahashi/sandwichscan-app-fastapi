import pytest_asyncio
from app.repositories.defi_repository import DefiRepository


@pytest_asyncio.fixture
async def defi_repository(async_session):
    return DefiRepository(async_session)
