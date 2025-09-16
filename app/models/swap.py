from app.db.base import Base
from sqlalchemy import String, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey, UniqueConstraint, Index
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class Swap(TimestampMixin, Base):
    __tablename__ = "swaps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chain_id: Mapped[int] = mapped_column(
        ForeignKey("chains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    defi_pool_id: Mapped[int] = mapped_column(
        ForeignKey("defi_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    log_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # 共通（v2/v3/v4を包括）
    sender: Mapped[str | None] = mapped_column(String, nullable=True)
    recipient: Mapped[str | None] = mapped_column(String, nullable=True)

    amount0_in_raw: Mapped[int] = mapped_column(
        Numeric(78, 0), nullable=False, default=0
    )
    amount1_in_raw: Mapped[int] = mapped_column(
        Numeric(78, 0), nullable=False, default=0
    )
    amount0_out_raw: Mapped[int] = mapped_column(
        Numeric(78, 0), nullable=False, default=0
    )
    amount1_out_raw: Mapped[int] = mapped_column(
        Numeric(78, 0), nullable=False, default=0
    )

    # v3系専用（存在しない場合はNULL）
    sqrt_price_x96: Mapped[int | None] = mapped_column(Numeric(78, 0), nullable=True)
    liquidity_raw: Mapped[int | None] = mapped_column(Numeric(78, 0), nullable=True)
    tick: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sell_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True, index=True
    )
    buy_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True, index=True
    )
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("transaction_id", "log_index", name="uq_swaps_tx_log_index"),
        Index("idx_swaps_sender", "chain_id", "sender"),
        Index("idx_swaps_recipient", "chain_id", "recipient"),
        Index(
            "idx_swaps_pool_sell_buy",
            "defi_pool_id",
            "sell_token_id",
            "buy_token_id",
        ),
        Index(
            "idx_swaps_pool_tx_log",
            "defi_pool_id",
            "transaction_id",
            "log_index",
        ),
    )
