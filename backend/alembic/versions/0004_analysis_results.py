"""add result analysis and comparison persistence

Revision ID: 0004_analysis_results
Revises: 0003_simulation_jobs
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_analysis_results"
down_revision = "0003_simulation_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("simulation_job_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("variant_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_version", sa.String(length=32), nullable=False),
        sa.Column("flood_threshold_m", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("exposure", sa.JSON(), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["simulation_job_id"], ["simulation_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["scenario_variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in [
        ("ix_analysis_results_simulation_job_id", "simulation_job_id"),
        ("ix_analysis_results_project_id", "project_id"),
        ("ix_analysis_results_scenario_id", "scenario_id"),
        ("ix_analysis_results_variant_id", "variant_id"),
    ]:
        op.create_index(name, "analysis_results", [column], unique=False)

    op.create_table(
        "result_comparisons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("left_analysis_id", sa.String(length=36), nullable=False),
        sa.Column("right_analysis_id", sa.String(length=36), nullable=False),
        sa.Column("comparison_type", sa.String(length=32), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["left_analysis_id"], ["analysis_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_analysis_id"], ["analysis_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in [
        ("ix_result_comparisons_project_id", "project_id"),
        ("ix_result_comparisons_left_analysis_id", "left_analysis_id"),
        ("ix_result_comparisons_right_analysis_id", "right_analysis_id"),
        ("ix_result_comparisons_comparison_type", "comparison_type"),
    ]:
        op.create_index(name, "result_comparisons", [column], unique=False)


def downgrade() -> None:
    for name in [
        "ix_result_comparisons_comparison_type",
        "ix_result_comparisons_right_analysis_id",
        "ix_result_comparisons_left_analysis_id",
        "ix_result_comparisons_project_id",
    ]:
        op.drop_index(name, table_name="result_comparisons")
    op.drop_table("result_comparisons")
    for name in [
        "ix_analysis_results_variant_id",
        "ix_analysis_results_scenario_id",
        "ix_analysis_results_project_id",
        "ix_analysis_results_simulation_job_id",
    ]:
        op.drop_index(name, table_name="analysis_results")
    op.drop_table("analysis_results")
