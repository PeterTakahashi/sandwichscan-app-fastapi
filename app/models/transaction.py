from app.db.base import Base
from sqlalchemy import String, Integer, BigInteger, SmallInteger, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey, UniqueConstraint, Index
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chain import Chain

class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    chain_id: Mapped[int] = mapped_column(
        ForeignKey("chains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_timestamp: Mapped[str] = mapped_column(String, nullable=False)  # ISO文字列でもOK。TIMESTAMPTZを使う場合は型を切替

    tx_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String, nullable=False)

    from_address: Mapped[str] = mapped_column(String, nullable=False)
    to_address: Mapped[str | None] = mapped_column(String, nullable=True)

    value_wei: Mapped[int] = mapped_column(Numeric(78, 0), nullable=False, default=0)

    gas_used: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gas_price_wei: Mapped[int | None] = mapped_column(Numeric(78, 0), nullable=True)
    effective_gas_price_wei: Mapped[int | None] = mapped_column(Numeric(78, 0), nullable=True)

    status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)  # 1=成功, 0=失敗 など

    __table_args__ = (
        UniqueConstraint("chain_id", "tx_hash", name="uq_transactions_chain_txhash"),
        Index("idx_transactions_chain_block", "chain_id", "block_number"),
        Index("idx_transactions_from", "chain_id", "from_address"),
        Index("idx_transactions_to", "chain_id", "to_address"),
    )

    chain: Mapped["Chain"] = relationship("Chain", back_populates="transactions")
