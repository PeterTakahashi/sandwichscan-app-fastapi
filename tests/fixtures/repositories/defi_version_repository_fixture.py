import pytest_asyncio
from app.v1.repositories.defi_version_repository import DefiVersionRepository


@pytest_asyncio.fixture
async def defi_version_repository(async_session):
    return DefiVersionRepository(async_session)
