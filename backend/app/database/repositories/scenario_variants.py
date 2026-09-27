from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ScenarioVariant


class ScenarioVariantRepository:
    def create(self, db: Session, **values) -> ScenarioVariant:
        record = ScenarioVariant(**values)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get(self, db: Session, variant_id: str) -> ScenarioVariant | None:
        return db.get(ScenarioVariant, variant_id)

    def list_for_scenario(self, db: Session, scenario_id: str) -> list[ScenarioVariant]:
        stmt = (
            select(ScenarioVariant)
            .where(ScenarioVariant.base_scenario_id == scenario_id)
            .order_by(ScenarioVariant.created_at.asc())
        )
        return list(db.scalars(stmt).all())
