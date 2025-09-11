import pytest_asyncio
from app.repositories.defi_factory_repository import DefiFactoryRepository


@pytest_asyncio.fixture
async def defi_factory_repository(async_session):
    return DefiFactoryRepository(async_session)
