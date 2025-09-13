from typing import TYPE_CHECKING
from app.db.base import Base
from sqlalchemy import String, UniqueConstraint, BigInteger
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey

if TYPE_CHECKING:
    from app.models.defi_factory import DefiFactory
    from app.models.chain import Chain
    from app.models.token import Token


class DefiPool(TimestampMixin, Base):
    __tablename__ = "defi_pools"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    defi_factory_id: Mapped[int] = mapped_column(
        ForeignKey("defi_factories.id", ondelete="CASCADE"),
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
    address: Mapped[str] = mapped_column(String, nullable=False)
    created_block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_tx_hash: Mapped[str] = mapped_column(String, nullable=False)
    tick_spacing: Mapped[int] = mapped_column(nullable=False, default=0)
    fee_tier_bps: Mapped[int] = mapped_column(nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("chain_id", "address", name="uq_defi_pools_chain_address"),
    )

    defi_factory: Mapped["DefiFactory"] = relationship(
        "DefiFactory", back_populates="defi_pools"
    )
    chain: Mapped["Chain"] = relationship("Chain", back_populates="defi_pools")
    token0: Mapped["Token"] = relationship(
        "Token", foreign_keys=[token0_id], back_populates="defi_pools_token0"
    )
    token1: Mapped["Token"] = relationship(
        "Token", foreign_keys=[token1_id], back_populates="defi_pools_token1"
    )
