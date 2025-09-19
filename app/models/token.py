from typing import TYPE_CHECKING, List
from sqlalchemy import (
    ForeignKey,
    Enum as SQLAlchemyEnum,
    String,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.mixin.timestamp import TimestampMixin
from app.models.enums.token import TokenType


if TYPE_CHECKING:
    from app.models.chain import Chain
    from app.models.defi_pool import DefiPool
    from app.models.swap import Swap
    from app.models.sandwich_attack import SandwichAttack


class Token(TimestampMixin, Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    token_type: Mapped[TokenType] = mapped_column(
        SQLAlchemyEnum(TokenType, native_enum=True),
        nullable=False,
        default=TokenType.ERC20,
    )

    chain_id: Mapped[int] = mapped_column(
        ForeignKey("chains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    address: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    decimals: Mapped[int] = mapped_column(nullable=False)
    decimals_invalid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        UniqueConstraint("chain_id", "address", name="uq_tokens_chain_address"),
    )
    chain: Mapped["Chain"] = relationship("Chain", back_populates="tokens")
    defi_pools_token0: Mapped[List["DefiPool"]] = relationship(
        "DefiPool", foreign_keys="[DefiPool.token0_id]", back_populates="token0"
    )
    defi_pools_token1: Mapped[List["DefiPool"]] = relationship(
        "DefiPool", foreign_keys="[DefiPool.token1_id]", back_populates="token1"
    )
    swaps_as_sell_token: Mapped[List["Swap"]] = relationship(
        "Swap",
        foreign_keys="[Swap.sell_token_id]",
        back_populates="sell_token",
        cascade="all, delete-orphan",
    )
    swaps_as_buy_token: Mapped[List["Swap"]] = relationship(
        "Swap",
        foreign_keys="[Swap.buy_token_id]",
        back_populates="buy_token",
        cascade="all, delete-orphan",
    )
    sandwich_attacks: Mapped[List["SandwichAttack"]] = relationship(
        "SandwichAttack", back_populates="base_token", cascade="all, delete-orphan"
    )
