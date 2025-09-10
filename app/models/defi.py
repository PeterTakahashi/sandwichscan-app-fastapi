from app.db.base import Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin


class Defi(TimestampMixin, Base):
    __tablename__ = "defis"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 'uniswap', 'sushiswap', ...
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
