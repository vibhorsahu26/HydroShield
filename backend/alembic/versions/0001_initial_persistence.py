"""initial HydroShield persistence schema

Revision ID: 0001_initial_persistence
Revises:
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_persistence"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_projects_name", "projects", ["name"], unique=False)

    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_type", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("validation_status", sa.String(length=16), nullable=False),
        sa.Column("crs", sa.String(length=64), nullable=True),
        sa.Column("geometry_types", sa.JSON(), nullable=False),
        sa.Column("shape", sa.JSON(), nullable=True),
        sa.Column("bounds", sa.JSON(), nullable=True),
        sa.Column("feature_count", sa.Integer(), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"], unique=False)
    op.create_index("ix_datasets_dataset_type", "datasets", ["dataset_type"], unique=False)

    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=16), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scenarios_project_id", "scenarios", ["project_id"], unique=False)

    op.create_table(
        "spatial_features",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=True),
        sa.Column("feature_type", sa.String(length=32), nullable=False),
        sa.Column("geom", sa.LargeBinary(), nullable=False),
        sa.Column("geometry_srid", sa.Integer(), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_spatial_features_project_id", "spatial_features", ["project_id"], unique=False)
    op.create_index("ix_spatial_features_dataset_id", "spatial_features", ["dataset_id"], unique=False)
    op.create_index("ix_spatial_features_feature_type", "spatial_features", ["feature_type"], unique=False)

    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE spatial_features ALTER COLUMN geom TYPE geometry(Geometry) "
            "USING ST_SetSRID(ST_GeomFromWKB(geom), geometry_srid)"
        )
        op.execute(
            "CREATE INDEX ix_spatial_features_geom_gist ON spatial_features USING GIST (geom)"
        )


def downgrade() -> None:
    op.drop_index("ix_spatial_features_feature_type", table_name="spatial_features")
    op.drop_index("ix_spatial_features_dataset_id", table_name="spatial_features")
    op.drop_index("ix_spatial_features_project_id", table_name="spatial_features")
    op.drop_table("spatial_features")

    op.drop_index("ix_scenarios_project_id", table_name="scenarios")
    op.drop_table("scenarios")

    op.drop_index("ix_datasets_dataset_type", table_name="datasets")
    op.drop_index("ix_datasets_project_id", table_name="datasets")
    op.drop_table("datasets")

    op.drop_index("ix_projects_name", table_name="projects")
    op.drop_table("projects")
