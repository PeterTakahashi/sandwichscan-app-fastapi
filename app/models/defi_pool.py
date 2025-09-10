from typing import TYPE_CHECKING
from app.db.base import Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey

if TYPE_CHECKING:
    pass


class DefiPool(TimestampMixin, Base):
    __tablename__ = "defi_pools"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    defi_version_id: Mapped[int] = mapped_column(
        ForeignKey("defi_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("chains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token0_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token1_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 'uniswap-<version>', 'sushiswap-<version>', ...
    address: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    swap_fee: Mapped[float] = mapped_column(nullable=False, default=0.003)
