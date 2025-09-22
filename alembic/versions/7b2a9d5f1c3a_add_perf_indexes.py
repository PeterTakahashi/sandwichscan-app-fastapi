"""add performance indexes for sandwich detection

Revision ID: 7b2a9d5f1c3a
Revises: 046b4afcd660
Create Date: 2025-09-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b2a9d5f1c3a"
down_revision: Union[str, None] = "046b4afcd660"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # For plans that start from transactions in a block range and join to swaps
    # on transaction_id, this index reduces lookups and enables ordered scans.
    op.create_index(
        "idx_swaps_tx_pool_log",
        "swaps",
        ["transaction_id", "defi_pool_id", "log_index"],
        unique=False,
    )

    # Functional index for LOWER(from_address) to avoid full expression scans
    # when queries normalize addresses. Include chain_id for partitioning.
    op.create_index(
        "idx_transactions_from_lower",
        "transactions",
        [sa.text("chain_id"), sa.text("LOWER(from_address)")],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_transactions_from_lower", table_name="transactions")
    op.drop_index("idx_swaps_tx_pool_log", table_name="swaps")
