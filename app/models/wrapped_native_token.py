from typing import TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, UniqueConstraint, Index
from app.db.base import Base
from app.models.mixin.timestamp import TimestampMixin

if TYPE_CHECKING:
    from app.models.chain import Chain
    from app.models.token import Token
    from app.models.defi_pool import DefiPool
    from app.models.usd_stable_coin import UsdStableCoin


class WrappedNativeToken(TimestampMixin, Base):
    __tablename__ = "wrapped_native_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chain_id: Mapped[int] = mapped_column(
        ForeignKey("chains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usd_stable_coin_id: Mapped[int | None] = mapped_column(
        ForeignKey("usd_stable_coins.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    usd_pool_id: Mapped[int | None] = mapped_column(
        ForeignKey("defi_pools.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (
        UniqueConstraint("chain_id", name="uq_wrapped_native_tokens_chain"),
        Index("idx_wrapped_native_tokens_chain_pool", "chain_id", "usd_pool_id"),
    )

    # relations
    chain: Mapped["Chain"] = relationship("Chain")
    token: Mapped["Token"] = relationship("Token")
    usd_pool: Mapped["DefiPool"] = relationship("DefiPool")
    usd_stable_coin: Mapped["UsdStableCoin"] = relationship("UsdStableCoin")
    usd_stable_coin_token: Mapped["Token"] = relationship(
        "Token", viewonly=True, foreign_keys="[UsdStableCoin.token_id]"
    )
