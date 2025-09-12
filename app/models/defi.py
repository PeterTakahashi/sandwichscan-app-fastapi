from app.db.base import Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.mixin.timestamp import TimestampMixin
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.defi_version import DefiVersion


class Defi(TimestampMixin, Base):
    __tablename__ = "defis"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 'uniswap', 'sushiswap', ...
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    logo_url: Mapped[str] = mapped_column(String, nullable=False, default="")

    defi_versions: Mapped[List["DefiVersion"]] = relationship(
        "DefiVersion", back_populates="defi", cascade="all, delete-orphan"
    )
