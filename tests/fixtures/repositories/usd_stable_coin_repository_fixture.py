import pytest_asyncio
from app.repositories.usd_stable_coin_repository import UsdStableCoinRepository


@pytest_asyncio.fixture
async def usd_stable_coin_repository(async_session):
    return UsdStableCoinRepository(async_session)
