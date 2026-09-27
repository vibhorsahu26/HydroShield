"""add generated scenario variants

Revision ID: 0002_scenario_variants
Revises: 0001_initial_persistence
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_scenario_variants"
down_revision = "0001_initial_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_variants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("base_scenario_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("preset", sa.String(length=80), nullable=False),
        sa.Column("breach_fraction", sa.Float(), nullable=True),
        sa.Column("model", sa.String(length=16), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["base_scenario_id"], ["scenarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("base_scenario_id", "code", name="uq_scenario_variants_base_code"),
    )
    op.create_index(
        "ix_scenario_variants_base_scenario_id",
        "scenario_variants",
        ["base_scenario_id"],
        unique=False,
    )
    op.create_index(
        "ix_scenario_variants_kind",
        "scenario_variants",
        ["kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scenario_variants_kind", table_name="scenario_variants")
    op.drop_index("ix_scenario_variants_base_scenario_id", table_name="scenario_variants")
    op.drop_table("scenario_variants")
