import pytest_asyncio
from app.v1.repositories.chain_repository import ChainRepository


@pytest_asyncio.fixture
async def chain_repository(async_session):
    return ChainRepository(async_session)
