"""Add persistent review decisions."""

from alembic import op
import sqlalchemy as sa

revision = "20260805_module5_reviews"
down_revision = "20260805_module4_copywriting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("subject_type", sa.String(30), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("subject_fingerprint", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(80), nullable=False, server_default="operator"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "subject_type", "subject_id", name="uq_review_subject"),
    )
    op.create_index("ix_review_decisions_product_id", "review_decisions", ["product_id"])
    op.create_index("ix_review_decisions_subject_type", "review_decisions", ["subject_type"])
    op.create_index("ix_review_decisions_subject_fingerprint", "review_decisions", ["subject_fingerprint"])
    op.create_index("ix_review_decisions_decision", "review_decisions", ["decision"])


def downgrade() -> None:
    op.drop_index("ix_review_decisions_decision", table_name="review_decisions")
    op.drop_index("ix_review_decisions_subject_fingerprint", table_name="review_decisions")
    op.drop_index("ix_review_decisions_subject_type", table_name="review_decisions")
    op.drop_index("ix_review_decisions_product_id", table_name="review_decisions")
    op.drop_table("review_decisions")
