"""Add reusable packaging image presets and product selections."""

from alembic import op
import sqlalchemy as sa

revision = "20260812_packaging_presets"
down_revision = "20260811_finished_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "packaging_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slot", sa.Integer(), nullable=False, unique=True),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_packaging_presets_slot", "packaging_presets", ["slot"])
    op.create_index("ix_packaging_presets_sha256", "packaging_presets", ["sha256"])
    op.create_table(
        "product_packaging_selections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, unique=True),
        sa.Column("preset_id", sa.Integer(), sa.ForeignKey("packaging_presets.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_packaging_selections_product_id", "product_packaging_selections", ["product_id"])
    op.create_index("ix_product_packaging_selections_preset_id", "product_packaging_selections", ["preset_id"])


def downgrade() -> None:
    op.drop_table("product_packaging_selections")
    op.drop_table("packaging_presets")
