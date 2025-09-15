from typing import TYPE_CHECKING, List
from app.db.base import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import (
    ForeignKey,
    Enum as SQLAlchemyEnum,
    String,
    UniqueConstraint,
    Boolean,
)
from app.models.enums.token import TokenType


if TYPE_CHECKING:
    from app.models.chain import Chain
    from app.models.defi_pool import DefiPool


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
