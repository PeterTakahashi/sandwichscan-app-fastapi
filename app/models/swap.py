from typing import TYPE_CHECKING, List
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.mixin.timestamp import TimestampMixin

if TYPE_CHECKING:
    from app.models.chain import Chain
    from app.models.defi_pool import DefiPool
    from app.models.token import Token
    from app.models.transaction import Transaction
    from app.models.sandwich_attack import SandwichAttack


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

    # relationships
    chain: Mapped["Chain"] = relationship("Chain", back_populates="swaps")
    defi_pool: Mapped["DefiPool"] = relationship("DefiPool", back_populates="swaps")
    transaction: Mapped["Transaction"] = relationship(
        "Transaction", back_populates="swaps"
    )
    sell_token: Mapped["Token"] = relationship(
        "Token", foreign_keys=[sell_token_id], back_populates="swaps_as_sell_token"
    )
    buy_token: Mapped["Token"] = relationship(
        "Token", foreign_keys=[buy_token_id], back_populates="swaps_as_buy_token"
    )
    front_sandwich_attacks: Mapped[List["SandwichAttack"]] = relationship(
        "SandwichAttack",
        foreign_keys="[SandwichAttack.front_attack_swap_id]",
        back_populates="front_attack_swap",
        cascade="all, delete-orphan",
    )
    victim_sandwich_attacks: Mapped[List["SandwichAttack"]] = relationship(
        "SandwichAttack",
        foreign_keys="[SandwichAttack.victim_swap_id]",
        back_populates="victim_swap",
        cascade="all, delete-orphan",
    )
    back_sandwich_attacks: Mapped[List["SandwichAttack"]] = relationship(
        "SandwichAttack",
        foreign_keys="[SandwichAttack.back_attack_swap_id]",
        back_populates="back_attack_swap",
        cascade="all, delete-orphan",
    )
