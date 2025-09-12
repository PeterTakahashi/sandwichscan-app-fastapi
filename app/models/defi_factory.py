from typing import TYPE_CHECKING
from app.db.base import Base
from sqlalchemy import String, UniqueConstraint, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey
from typing import List

if TYPE_CHECKING:
    from app.models.defi_version import DefiVersion
    from app.models.chain import Chain
    from app.models.defi_pool import DefiPool


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
    last_gotten_block_number: Mapped[int] = mapped_column(nullable=False, default=0)
    created_block_number: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    __table_args__ = (
        UniqueConstraint("chain_id", "address", name="uq_defi_factories_chain_address"),
    )

    defi_version: Mapped["DefiVersion"] = relationship("DefiVersion", back_populates="defi_factories")
    chain: Mapped["Chain"] = relationship("Chain", back_populates="defi_factories")
    defi_pools: Mapped[List["DefiPool"]] = relationship(
        "DefiPool", back_populates="defi_factory", cascade="all, delete-orphan"
    )
