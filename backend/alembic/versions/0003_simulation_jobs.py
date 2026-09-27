"""add persistent simulation jobs

Revision ID: 0003_simulation_jobs
Revises: 0002_scenario_variants
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_simulation_jobs"
down_revision = "0002_scenario_variants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulation_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("variant_id", sa.String(length=36), nullable=False),
        sa.Column("model", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("current_step", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_s", sa.Float(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("working_directory", sa.Text(), nullable=True),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["scenario_variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, column in [
        ("ix_simulation_jobs_project_id", "project_id"),
        ("ix_simulation_jobs_scenario_id", "scenario_id"),
        ("ix_simulation_jobs_variant_id", "variant_id"),
        ("ix_simulation_jobs_model", "model"),
        ("ix_simulation_jobs_status", "status"),
    ]:
        op.create_index(index_name, "simulation_jobs", [column], unique=False)


def downgrade() -> None:
    for index_name in [
        "ix_simulation_jobs_status",
        "ix_simulation_jobs_model",
        "ix_simulation_jobs_variant_id",
        "ix_simulation_jobs_scenario_id",
        "ix_simulation_jobs_project_id",
    ]:
        op.drop_index(index_name, table_name="simulation_jobs")
    op.drop_table("simulation_jobs")
