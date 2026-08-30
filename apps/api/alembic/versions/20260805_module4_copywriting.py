"""Add platform listing copy records."""

from alembic import op
import sqlalchemy as sa

revision = "20260805_module4_copywriting"
down_revision = "20260804_simple_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_copies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("bullet_points_json", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sku_names_json", sa.Text(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("generator", sa.String(40), nullable=False, server_default="deterministic-template"),
        sa.Column("rules_version", sa.String(30), nullable=False, server_default="platform-rules-v1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("issues_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "platform", name="uq_product_listing_copy_platform"),
    )
    op.create_index("ix_listing_copies_product_id", "listing_copies", ["product_id"])
    op.create_index("ix_listing_copies_platform", "listing_copies", ["platform"])
    op.create_index("ix_listing_copies_input_fingerprint", "listing_copies", ["input_fingerprint"])
    op.create_index("ix_listing_copies_status", "listing_copies", ["status"])


def downgrade() -> None:
    op.drop_index("ix_listing_copies_status", table_name="listing_copies")
    op.drop_index("ix_listing_copies_input_fingerprint", table_name="listing_copies")
    op.drop_index("ix_listing_copies_platform", table_name="listing_copies")
    op.drop_index("ix_listing_copies_product_id", table_name="listing_copies")
    op.drop_table("listing_copies")
