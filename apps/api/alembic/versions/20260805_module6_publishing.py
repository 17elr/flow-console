"""Complete publishing records."""

from alembic import op
import sqlalchemy as sa

revision = "20260805_module6_publishing"
down_revision = "20260805_module5_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("store_listings", sa.Column("external_product_id", sa.String(160), nullable=True))
    op.add_column("store_listings", sa.Column("response_json", sa.Text(), nullable=True))
    op.add_column("store_listings", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("store_listings", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("miaoshou_drafts", sa.Column("request_id", sa.String(160), nullable=True))
    op.add_column("miaoshou_drafts", sa.Column("response_json", sa.Text(), nullable=True))
    op.add_column("miaoshou_drafts", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("miaoshou_drafts", "attempt_count")
    op.drop_column("miaoshou_drafts", "response_json")
    op.drop_column("miaoshou_drafts", "request_id")
    op.drop_column("store_listings", "updated_at")
    op.drop_column("store_listings", "error_message")
    op.drop_column("store_listings", "response_json")
    op.drop_column("store_listings", "external_product_id")
