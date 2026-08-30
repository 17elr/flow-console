"""Add simplified publishing workflow records."""

from alembic import op
import sqlalchemy as sa

revision = "20260804_simple_workflow"
down_revision = "20260803_module3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "miaoshou_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("external_id", sa.String(160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("package_key", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_miaoshou_draft_key"),
    )
    op.create_index("ix_miaoshou_drafts_product_id", "miaoshou_drafts", ["product_id"])
    op.create_index("ix_miaoshou_drafts_store_id", "miaoshou_drafts", ["store_id"])
    op.create_index("ix_miaoshou_drafts_idempotency_key", "miaoshou_drafts", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_miaoshou_drafts_idempotency_key", table_name="miaoshou_drafts")
    op.drop_index("ix_miaoshou_drafts_store_id", table_name="miaoshou_drafts")
    op.drop_index("ix_miaoshou_drafts_product_id", table_name="miaoshou_drafts")
    op.drop_table("miaoshou_drafts")
