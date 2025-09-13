from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sandwich_attack import SandwichAttack
from fastapi_repository import BaseRepository


class SandwichAttackRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, SandwichAttack)
