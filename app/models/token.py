from typing import TYPE_CHECKING
from app.db.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey, Enum as SQLAlchemyEnum, String, UniqueConstraint
from app.models.enums.token import TokenType


if TYPE_CHECKING:
    pass


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

    # 'uniswap-<version>', 'sushiswap-<version>', ...
    address: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    decimals: Mapped[int] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("chain_id", "address", name="uq_tokens_chain_address"),
    )
