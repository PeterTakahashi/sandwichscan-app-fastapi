from faker import Faker
import pytest_asyncio
from app.lib.utils.convert_id import encode_id


@pytest_asyncio.fixture
def faker():
    return Faker()


@pytest_asyncio.fixture
async def fake_id() -> str:
    return encode_id(0)
