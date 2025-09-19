from typing import TYPE_CHECKING
from app.db.base import Base
from sqlalchemy import String, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey, UniqueConstraint, Index

if TYPE_CHECKING:
    from app.models.chain import Chain
    from app.models.swap import Swap
    from app.models.token import Token
    from app.models.defi_version import DefiVersion


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
    defi_version_id: Mapped[int] = mapped_column(
        ForeignKey("defi_versions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    attacker_address: Mapped[str] = mapped_column(String, nullable=False)
    victim_address: Mapped[str | None] = mapped_column(String, nullable=True)

    base_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True, index=True
    )

    revenue_base_raw: Mapped[int] = mapped_column(
        Numeric(78, 0), nullable=False, default=0
    )
    gas_fee_wei_attacker: Mapped[int] = mapped_column(
        Numeric(78, 0), nullable=False, default=0
    )
    profit_base_raw: Mapped[int] = mapped_column(
        Numeric(78, 0), nullable=False, default=0
    )
    harm_base_raw: Mapped[int] = mapped_column(
        Numeric(78, 0), nullable=False, default=0
    )

    revenue_usd: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)
    profit_usd: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)
    harm_usd: Mapped[float | None] = mapped_column(Numeric(38, 18), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "front_attack_swap_id",
            "victim_swap_id",
            "back_attack_swap_id",
            name="uq_sandwich_triplet",
        ),
        Index("idx_sandwich_chain", "chain_id"),
        Index("idx_sandwich_attacker", "attacker_address"),
        Index("idx_sandwich_victim", "victim_address"),
    )

    # Relationships
    chain: Mapped["Chain"] = relationship("Chain", back_populates="sandwich_attacks")
    front_attack_swap: Mapped["Swap"] = relationship(
        "Swap",
        foreign_keys=[front_attack_swap_id],
        back_populates="front_sandwich_attacks",
    )
    victim_swap: Mapped["Swap"] = relationship(
        "Swap", foreign_keys=[victim_swap_id], back_populates="victim_sandwich_attacks"
    )
    back_attack_swap: Mapped["Swap"] = relationship(
        "Swap",
        foreign_keys=[back_attack_swap_id],
        back_populates="back_sandwich_attacks",
    )
    base_token: Mapped["Token"] = relationship(
        "Token", back_populates="sandwich_attacks"
    )
    defi_version: Mapped["DefiVersion"] = relationship(
        "DefiVersion", back_populates="sandwich_attacks"
    )
