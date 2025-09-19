import pytest_asyncio
from app.repositories.wrapped_native_token_repository import (
    WrappedNativeTokenRepository,
)


@pytest_asyncio.fixture
async def wrapped_native_token_repository(async_session):
    return WrappedNativeTokenRepository(async_session)
