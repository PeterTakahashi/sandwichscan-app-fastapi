from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sandwich_attack import SandwichAttack
from fastapi_repository import BaseRepository
from sqlalchemy import select, func, literal
from sqlalchemy.sql.elements import ColumnElement
from app.v1.schemas.sandwich_attack.read_by_month import SandwichAttackReadByMonth


month = func.date_trunc(literal("month"), SandwichAttack.block_timestamp).label("month")


class SandwichAttackRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, SandwichAttack)

    async def aggregate_by_month(
        self,
        **search_params,
    ) -> list[SandwichAttackReadByMonth]:
        model = self.model

        conditions: list[ColumnElement] = []
        conditions += await self._BaseRepository__get_conditions(**search_params)

        query = (
            select(
                month,
                func.count().label("total_attacks"),
                func.coalesce(func.sum(model.revenue_usd), 0).label(
                    "total_revenue_usd"
                ),
                func.coalesce(func.sum(model.profit_usd), 0).label("total_profit_usd"),
                func.coalesce(func.sum(model.harm_usd), 0).label("total_harm_usd"),
            )
            .select_from(model)
            .where(*conditions)
            .group_by(month)
            .order_by(month)
        )

        result = await self.session.execute(query)
        rows = result.mappings().all()
        return [SandwichAttackReadByMonth.model_validate(row) for row in rows]
