from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    datasets: Mapped[list[Dataset]] = relationship(back_populates="project", cascade="all, delete-orphan")
    scenarios: Mapped[list[Scenario]] = relationship(back_populates="project", cascade="all, delete-orphan")
    spatial_features: Mapped[list[SpatialFeature]] = relationship(back_populates="project", cascade="all, delete-orphan")
    acquisition_runs: Mapped[list[AcquisitionRun]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False, default="validated")
    crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geometry_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    shape: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    bounds: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    columns: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    acquisition_run_id: Mapped[str | None] = mapped_column(ForeignKey("acquisition_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license: Mapped[str | None] = mapped_column(String(256), nullable=True)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="datasets")
    spatial_features: Mapped[list[SpatialFeature]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(16), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="scenarios")
    variants: Mapped[list[ScenarioVariant]] = relationship(
        back_populates="base_scenario", cascade="all, delete-orphan"
    )


class ScenarioVariant(Base):
    __tablename__ = "scenario_variants"
    __table_args__ = (UniqueConstraint("base_scenario_id", "code", name="uq_scenario_variants_base_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    base_scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    preset: Mapped[str] = mapped_column(String(80), nullable=False)
    breach_fraction: Mapped[float | None] = mapped_column(nullable=True)
    model: Mapped[str] = mapped_column(String(16), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    base_scenario: Mapped[Scenario] = relationship(back_populates="variants")


class SpatialFeature(Base):
    """Generic vector feature storage.

    The ORM uses WKB so SQLite can run the same application tests. The PostgreSQL
    migration converts ``geom`` to a native PostGIS geometry column and the
    repository uses PostGIS functions for spatial writes/queries there.
    """

    __tablename__ = "spatial_features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True)
    feature_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    geom: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    geometry_srid: Mapped[int] = mapped_column(Integer, nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="spatial_features")
    dataset: Mapped[Dataset | None] = relationship(back_populates="spatial_features")

class SimulationJob(Base):
    __tablename__ = "simulation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("scenario_variants.id", ondelete="CASCADE"), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="queued")
    progress: Mapped[float] = mapped_column(nullable=False, default=0.0)
    current_step: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timeout_s: Mapped[float] = mapped_column(nullable=False, default=3600.0)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    working_directory: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(nullable=False, default=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped[Project] = relationship()
    scenario: Mapped[Scenario] = relationship()
    variant: Mapped[ScenarioVariant] = relationship()

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    simulation_job_id: Mapped[str] = mapped_column(ForeignKey("simulation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("scenario_variants.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_version: Mapped[str] = mapped_column(String(32), nullable=False)
    flood_threshold_m: Mapped[float] = mapped_column(nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    exposure: Mapped[dict] = mapped_column(JSON, nullable=False)
    artifacts: Mapped[dict] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    simulation_job: Mapped[SimulationJob] = relationship()


class ResultComparison(Base):
    __tablename__ = "result_comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    left_analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_results.id", ondelete="CASCADE"), nullable=False, index=True)
    right_analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_results.id", ondelete="CASCADE"), nullable=False, index=True)
    comparison_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    artifacts: Mapped[dict] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class SatelliteValidationResult(Base):
    __tablename__ = "satellite_validation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    simulation_job_id: Mapped[str] = mapped_column(ForeignKey("simulation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_result_id: Mapped[str] = mapped_column(ForeignKey("analysis_results.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("scenario_variants.id", ondelete="CASCADE"), nullable=False, index=True)
    sensor: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    collection_id: Mapped[str] = mapped_column(String(128), nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_image_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    observed_extent_path: Mapped[str] = mapped_column(Text, nullable=False)
    difference_map_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AcquisitionRun(Base):
    __tablename__ = "acquisition_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    request: Mapped[dict] = mapped_column(JSON, nullable=False)
    provider_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="acquisition_runs")
