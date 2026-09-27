from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AnalysisResult, ResultComparison


class AnalysisResultRepository:
    def create(self, db: Session, **values) -> AnalysisResult:
        record = AnalysisResult(**values)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get(self, db: Session, result_id: str) -> AnalysisResult | None:
        return db.get(AnalysisResult, result_id)

    def list_for_job(self, db: Session, simulation_job_id: str) -> list[AnalysisResult]:
        stmt = select(AnalysisResult).where(AnalysisResult.simulation_job_id == simulation_job_id).order_by(AnalysisResult.created_at.desc())
        return list(db.scalars(stmt).all())


class ResultComparisonRepository:
    def create(self, db: Session, **values) -> ResultComparison:
        record = ResultComparison(**values)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get(self, db: Session, comparison_id: str) -> ResultComparison | None:
        return db.get(ResultComparison, comparison_id)
