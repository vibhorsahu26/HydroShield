"""automatic data acquisition provenance

Revision ID: 0006_automatic_data_acquisition
Revises: 0005_satellite_validation
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_automatic_data_acquisition"
down_revision = "0005_satellite_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "acquisition_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("provider_summary", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_acquisition_runs_project_id", "acquisition_runs", ["project_id"], unique=False)
    op.create_index("ix_acquisition_runs_status", "acquisition_runs", ["status"], unique=False)

    with op.batch_alter_table("datasets") as batch:
        batch.add_column(sa.Column("acquisition_run_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("provider", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("source_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("source_id", sa.String(length=256), nullable=True))
        batch.add_column(sa.Column("checksum_sha256", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("license", sa.String(length=256), nullable=True))
        batch.add_column(sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.create_index("ix_datasets_acquisition_run_id", ["acquisition_run_id"], unique=False)
        batch.create_foreign_key("fk_datasets_acquisition_run", "acquisition_runs", ["acquisition_run_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("datasets") as batch:
        batch.drop_constraint("fk_datasets_acquisition_run", type_="foreignkey")
        batch.drop_index("ix_datasets_acquisition_run_id")
        batch.drop_column("metadata")
        batch.drop_column("acquired_at")
        batch.drop_column("license")
        batch.drop_column("checksum_sha256")
        batch.drop_column("source_id")
        batch.drop_column("source_url")
        batch.drop_column("provider")
        batch.drop_column("acquisition_run_id")
    op.drop_index("ix_acquisition_runs_status", table_name="acquisition_runs")
    op.drop_index("ix_acquisition_runs_project_id", table_name="acquisition_runs")
    op.drop_table("acquisition_runs")
