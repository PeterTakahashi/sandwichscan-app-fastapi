from app.db.base import Base
from sqlalchemy import String, Integer, BigInteger, SmallInteger, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey, UniqueConstraint, Index


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

    log_index: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # (tx_hash, log_index)で一意

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

    # 解析補助（UI/検出アルゴ用）
    base_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    base_is_token0: Mapped[bool | None] = mapped_column(nullable=True)
    direction: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )  # 1=base買い, -1=base売り, 0/NULL=不明

    # 冗長（JOIN削減）
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("tx_hash", "log_index", name="uq_swaps_txhash_logindex"),
        Index("idx_swaps_pool_block", "defi_pool_id", "block_number"),
        Index("idx_swaps_chain_block", "chain_id", "block_number"),
        Index("idx_swaps_sender", "chain_id", "sender"),
        Index("idx_swaps_recipient", "chain_id", "recipient"),
        Index("idx_swaps_base_direction", "base_token_id", "direction"),
    )
