from typing import TYPE_CHECKING
from app.db.base import Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.mixin.timestamp import TimestampMixin
from sqlalchemy import ForeignKey
from typing import List

if TYPE_CHECKING:
    from app.models.defi_factory import DefiFactory
    from app.models.defi import Defi

class DefiVersion(TimestampMixin, Base):
    __tablename__ = "defi_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    defi_id: Mapped[int] = mapped_column(
        ForeignKey("defis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 'uniswap-<version>', 'sushiswap-<version>', ...
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    defi_factories: Mapped[List["DefiFactory"]] = relationship(
        "DefiFactory", back_populates="defi_version", cascade="all, delete-orphan"
    )
    defi: Mapped["Defi"] = relationship("Defi", back_populates="defi_versions")
