"""Add automation schedules and runs."""

from alembic import op
import sqlalchemy as sa

revision = "20260805_module7_automation"
down_revision = "20260805_module6_publishing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_automation_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("price_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("visual_profile", sa.String(80), nullable=False, server_default="neutral-commerce"),
        sa.Column("max_daily", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_store_automation_configs_store_id", "store_automation_configs", ["store_id"])
    op.create_table(
        "automation_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("run_time", sa.String(5), nullable=False, server_default="02:00"),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("store_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("max_products", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("last_run_date", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_automation_schedules_active", "automation_schedules", ["active"])
    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schedule_id", sa.Integer(), sa.ForeignKey("automation_schedules.id"), nullable=True),
        sa.Column("trigger", sa.String(30), nullable=False, server_default="MANUAL"),
        sa.Column("status", sa.String(30), nullable=False, server_default="RUNNING"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_automation_runs_schedule_id", "automation_runs", ["schedule_id"])
    op.create_index("ix_automation_runs_status", "automation_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_automation_runs_status", table_name="automation_runs")
    op.drop_index("ix_automation_runs_schedule_id", table_name="automation_runs")
    op.drop_table("automation_runs")
    op.drop_index("ix_automation_schedules_active", table_name="automation_schedules")
    op.drop_table("automation_schedules")
    op.drop_index("ix_store_automation_configs_store_id", table_name="store_automation_configs")
    op.drop_table("store_automation_configs")
