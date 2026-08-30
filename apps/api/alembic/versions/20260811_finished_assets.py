"""Store original category parameters for finished-image imports."""

from alembic import op
import sqlalchemy as sa

revision = "20260811_finished_assets"
down_revision = "20260805_module7_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("import_parameters_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "import_parameters_json")
