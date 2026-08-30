"""Add GPT Image 2 scene pipeline metadata."""

from alembic import op
import sqlalchemy as sa

from app.db import Base
from app import models  # noqa: F401

revision = "20260803_module3"
down_revision = "20260802_module2"
branch_labels = None
depends_on = None


def _add(table: str, column: sa.Column) -> None:
    inspector = sa.inspect(op.get_bind())
    if column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    _add("products", sa.Column("scene_readiness", sa.String(30), nullable=False, server_default="NOT_CONFIGURED"))
    for column in (
        sa.Column("pipeline_kind", sa.String(30), nullable=False, server_default="DETERMINISTIC"),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=True),
        sa.Column("reference_sku_id", sa.Integer(), nullable=True),
    ):
        _add("image_batches", column)
    for column in (
        sa.Column("reference_asset_ids", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("provider_request_id", sa.String(120), nullable=True),
        sa.Column("provider_metadata_json", sa.Text(), nullable=True),
    ):
        _add("asset_versions", column)
    Base.metadata.tables["scene_profiles"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("scene_profiles")
