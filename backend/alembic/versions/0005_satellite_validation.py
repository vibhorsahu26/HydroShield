"""add satellite validation persistence

Revision ID: 0005_satellite_validation
Revises: 0004_analysis_results
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_satellite_validation"
down_revision = "0004_analysis_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "satellite_validation_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("simulation_job_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_result_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("variant_id", sa.String(length=36), nullable=False),
        sa.Column("sensor", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("collection_id", sa.String(length=128), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("selected_image_ids", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("observed_extent_path", sa.Text(), nullable=False),
        sa.Column("difference_map_path", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["simulation_job_id"], ["simulation_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_result_id"], ["analysis_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["scenario_variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in [
        ("ix_satellite_validation_results_simulation_job_id", "simulation_job_id"),
        ("ix_satellite_validation_results_analysis_result_id", "analysis_result_id"),
        ("ix_satellite_validation_results_project_id", "project_id"),
        ("ix_satellite_validation_results_scenario_id", "scenario_id"),
        ("ix_satellite_validation_results_variant_id", "variant_id"),
        ("ix_satellite_validation_results_sensor", "sensor"),
        ("ix_satellite_validation_results_phase", "phase"),
    ]:
        op.create_index(name, "satellite_validation_results", [column], unique=False)


def downgrade() -> None:
    for name in [
        "ix_satellite_validation_results_phase",
        "ix_satellite_validation_results_sensor",
        "ix_satellite_validation_results_variant_id",
        "ix_satellite_validation_results_scenario_id",
        "ix_satellite_validation_results_project_id",
        "ix_satellite_validation_results_analysis_result_id",
        "ix_satellite_validation_results_simulation_job_id",
    ]:
        op.drop_index(name, table_name="satellite_validation_results")
    op.drop_table("satellite_validation_results")
