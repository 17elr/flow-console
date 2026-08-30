"""Add deterministic image pipeline schema without losing module-one data."""

from alembic import op
import sqlalchemy as sa

from app.db import Base
from app import models  # noqa: F401

revision = "20260802_module2"
down_revision = None
branch_labels = None
depends_on = None

def _add_column_if_missing(table: str, column: sa.Column) -> None:
    inspector = sa.inspect(op.get_bind())
    if table in inspector.get_table_names() and column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)

def upgrade() -> None:
    bind = op.get_bind()
    if "products" not in sa.inspect(bind).get_table_names():
        Base.metadata.create_all(bind=bind)
        return
    _add_column_if_missing("products", sa.Column("image_readiness", sa.String(30), nullable=False, server_default="NOT_CHECKED"))
    for column in (
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(40), nullable=False, server_default="SPU_MAIN_SOURCE"),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("mime_type", sa.String(80), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("mirror_status", sa.String(30), nullable=False, server_default="PENDING"),
    ):
        _add_column_if_missing("assets", column)
    op.execute("UPDATE assets SET role = CASE WHEN asset_type = 'SKU_SOURCE' THEN 'SKU_SOURCE' ELSE 'SPU_MAIN_SOURCE' END")
    op.execute("UPDATE assets SET source_url = url WHERE source_url IS NULL")
    for table_name in ("image_batches", "asset_versions", "image_jobs", "sku_assets"):
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)

def downgrade() -> None:
    for table_name in ("sku_assets", "image_jobs", "asset_versions", "image_batches"):
        op.drop_table(table_name)
