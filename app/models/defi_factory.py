from typing import TYPE_CHECKING
from app.db.base import Base
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey

from app.models import defi_version

if TYPE_CHECKING:
    pass


class DefiFactory(TimestampMixin, Base):
    __tablename__ = "defi_factories"

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

    address: Mapped[str] = mapped_column(String, nullable=False)
    __table_args__ = (
        UniqueConstraint("chain_id", "address", name="uq_defi_factories_chain_address"),
    )