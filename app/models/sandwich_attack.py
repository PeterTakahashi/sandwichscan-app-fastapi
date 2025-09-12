from app.db.base import Base
from sqlalchemy import String, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey, UniqueConstraint, Index


class SandwichAttack(TimestampMixin, Base):
    __tablename__ = "sandwich_attacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chain_id: Mapped[int] = mapped_column(
        ForeignKey("chains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    front_attack_swap_id: Mapped[int] = mapped_column(
        ForeignKey("swaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    victim_swap_id: Mapped[int] = mapped_column(
        ForeignKey("swaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    back_attack_swap_id: Mapped[int] = mapped_column(
        ForeignKey("swaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    attacker_address: Mapped[str] = mapped_column(String, nullable=False)
    victim_address: Mapped[str | None] = mapped_column(String, nullable=True)

    base_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # 経済量（raw=整数、正規化=小数）
    victim_base_size_raw: Mapped[int | None] = mapped_column(Numeric(78, 0), nullable=True)
    profit_base_raw: Mapped[int | None] = mapped_column(Numeric(78, 0), nullable=True)
    profit_base: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)
    harm_base_raw: Mapped[int | None] = mapped_column(Numeric(78, 0), nullable=True)
    harm_base: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)

    # ガス（攻撃者負担/全体）
    gas_fee_wei_attacker: Mapped[int | None] = mapped_column(Numeric(78, 0), nullable=True)
    gas_fee_eth_attacker: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)
    gas_fee_usd_attacker: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)
    gas_fee_eth_total: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)
    gas_fee_usd_total: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)

    detected_by: Mapped[str | None] = mapped_column(String, nullable=True)  # 検出器名/バージョン
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "front_attack_swap_id", "victim_swap_id", "back_attack_swap_id",
            name="uq_sandwich_triplet",
        ),
        Index("idx_sandwich_chain", "chain_id"),
        Index("idx_sandwich_attacker", "attacker_address"),
        Index("idx_sandwich_victim", "victim_address"),
    )