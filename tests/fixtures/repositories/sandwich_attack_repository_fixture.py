import pytest_asyncio
from app.repositories.sandwich_attack_repository import SandwichAttackRepository


@pytest_asyncio.fixture
async def sandwich_attack_repository(async_session):
    return SandwichAttackRepository(async_session)
