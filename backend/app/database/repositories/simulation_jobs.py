from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SimulationJob


class SimulationJobRepository:
    def create(self, db: Session, **values: Any) -> SimulationJob:
        record = SimulationJob(**values)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get(self, db: Session, job_id: str) -> SimulationJob | None:
        return db.get(SimulationJob, job_id)

    def list_for_project(self, db: Session, project_id: str) -> list[SimulationJob]:
        stmt = (
            select(SimulationJob)
            .where(SimulationJob.project_id == project_id)
            .order_by(SimulationJob.created_at.desc())
        )
        return list(db.scalars(stmt).all())

    def update(self, db: Session, job: SimulationJob, **values: Any) -> SimulationJob:
        for key, value in values.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        return job

    def request_cancel(self, db: Session, job: SimulationJob) -> SimulationJob:
        job.cancel_requested = True
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        return job

    def recover_interrupted(self, db: Session) -> int:
        """Move non-terminal jobs from an interrupted process back to the queue."""
        stmt = select(SimulationJob).where(
            SimulationJob.status.in_(["running", "preparing", "processing", "cancel_requested"])
        )
        records = list(db.scalars(stmt).all())
        for job in records:
            job.status = "queued"
            job.progress = 0.0
            job.current_step = "recovered_after_process_restart"
            job.error_message = "Previous worker process ended before the simulation completed."
            job.cancel_requested = False
            job.updated_at = datetime.now(timezone.utc)
        db.commit()
        return len(records)
