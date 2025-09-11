from app.db.base import Base
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.mixin.timestamp import TimestampMixin


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

    usd_stable_coin_address: Mapped[str] = mapped_column(
        String, nullable=False, default=""
    )

    logo_url: Mapped[str] = mapped_column(String, nullable=False, default="")
