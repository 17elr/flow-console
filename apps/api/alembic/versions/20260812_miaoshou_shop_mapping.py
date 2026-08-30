"""add Miaoshou shop mapping

Revision ID: 20260812_miaoshou_shop_mapping
Revises: 20260812_packaging_presets
"""
from alembic import op
import sqlalchemy as sa

revision = "20260812_miaoshou_shop_mapping"
down_revision = "20260812_packaging_presets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("stores") as batch:
        batch.add_column(sa.Column("external_shop_id", sa.String(length=160), nullable=True))
        batch.create_index("ix_stores_external_shop_id", ["external_shop_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("stores") as batch:
        batch.drop_index("ix_stores_external_shop_id")
        batch.drop_column("external_shop_id")
