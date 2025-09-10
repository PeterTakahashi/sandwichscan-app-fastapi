from typing import TYPE_CHECKING
from app.db.base import Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey

if TYPE_CHECKING:
    pass


class DefiVersion(TimestampMixin, Base):
    __tablename__ = "defi_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    defi_id: Mapped[int] = mapped_column(
        ForeignKey("defis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("chains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 'uniswap-<version>', 'sushiswap-<version>', ...
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
