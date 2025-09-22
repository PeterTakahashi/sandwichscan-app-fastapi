import pytest_asyncio
from app.repositories.swap_repository import SwapRepository


@pytest_asyncio.fixture
async def swap_repository(async_session):
    return SwapRepository(async_session)
