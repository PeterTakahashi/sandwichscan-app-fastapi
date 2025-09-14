from typing import TYPE_CHECKING
from app.db.base import Base
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, ForeignKey, UniqueConstraint, Index

if TYPE_CHECKING:
    from app.models.chain import Chain
    from app.models.token import Token


class UsdStableCoin(TimestampMixin, Base):
    __tablename__ = "usd_stable_coins"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chain_id: Mapped[int] = mapped_column(
        ForeignKey("chains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    __table_args__ = (
        UniqueConstraint(
            "chain_id", "token_id", name="uq_usd_stable_coins_chain_token"
        ),
        Index("idx_usd_stable_coins_chain_priority", "chain_id", "priority"),
    )

    # relations
    chain: Mapped["Chain"] = relationship("Chain", back_populates="usd_stable_coins")
    token: Mapped["Token"] = relationship("Token")
