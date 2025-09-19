from typing import TYPE_CHECKING, List
from app.db.base import Base
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.mixin.timestamp import TimestampMixin


if TYPE_CHECKING:
    from app.models.defi_factory import DefiFactory
    from app.models.defi_pool import DefiPool
    from app.models.token import Token
    from app.models.transaction import Transaction
    from app.models.usd_stable_coin import UsdStableCoin
    from app.models.swap import Swap
    from app.models.sandwich_attack import SandwichAttack


class Chain(TimestampMixin, Base):
    __tablename__ = "chains"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # EVM chainId (e.g. 1=Ethereum, 10=Optimism, 42161=Arbitrum)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)

    # 'ethereum', 'binance', ...
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    # 'ETH', 'BNB', ...
    native_symbol: Mapped[str] = mapped_column(String, nullable=False)

    # default 18 decimals
    native_decimals: Mapped[int] = mapped_column(Integer, nullable=False, default=18)

    rpc_url: Mapped[str] = mapped_column(String, nullable=False, default="")

    explorer_url: Mapped[str] = mapped_column(String, nullable=False, default="")

    last_block_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    big_query_table_id: Mapped[str] = mapped_column(String, nullable=False, default="")

    logo_url: Mapped[str] = mapped_column(String, nullable=False, default="")

    defi_factories: Mapped[List["DefiFactory"]] = relationship(
        "DefiFactory", back_populates="chain", cascade="all, delete-orphan"
    )
    defi_pools: Mapped[List["DefiPool"]] = relationship(
        "DefiPool", back_populates="chain", cascade="all, delete-orphan"
    )
    tokens: Mapped[List["Token"]] = relationship(
        "Token", back_populates="chain", cascade="all, delete-orphan"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="chain", cascade="all, delete-orphan"
    )
    usd_stable_coins: Mapped[List["UsdStableCoin"]] = relationship(
        "UsdStableCoin", back_populates="chain", cascade="all, delete-orphan"
    )
    usd_stable_coin_tokens: Mapped[List["Token"]] = relationship(
        "Token",
        secondary="usd_stable_coins",
        primaryjoin="Chain.id==UsdStableCoin.chain_id",
        secondaryjoin="Token.id==UsdStableCoin.token_id",
        viewonly=True,
    )
    swaps: Mapped[List["Swap"]] = relationship(
        "Swap", back_populates="chain", cascade="all, delete-orphan"
    )
    sandwich_attacks: Mapped[List["SandwichAttack"]] = relationship(
        "SandwichAttack", back_populates="chain", cascade="all, delete-orphan"
    )
