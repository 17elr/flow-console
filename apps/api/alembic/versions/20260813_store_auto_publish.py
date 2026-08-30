"""Add automatic publish switch to store automation config."""

from alembic import op
import sqlalchemy as sa

revision = "20260813_store_auto_publish"
down_revision = "20260812_miaoshou_shop_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "store_automation_configs",
        sa.Column("auto_publish", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("store_automation_configs", "auto_publish")
