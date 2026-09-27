from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SatelliteValidationResult


class SatelliteValidationRepository:
    def create(self, db: Session, **values) -> SatelliteValidationResult:
        record = SatelliteValidationResult(**values)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get(self, db: Session, result_id: str) -> SatelliteValidationResult | None:
        return db.get(SatelliteValidationResult, result_id)

    def list_for_analysis(self, db: Session, analysis_result_id: str) -> list[SatelliteValidationResult]:
        stmt = select(SatelliteValidationResult).where(
            SatelliteValidationResult.analysis_result_id == analysis_result_id
        ).order_by(SatelliteValidationResult.created_at.desc())
        return list(db.scalars(stmt).all())
