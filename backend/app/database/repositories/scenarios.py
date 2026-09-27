from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Scenario


class ScenarioRepository:
    def create(self, db: Session, **values) -> Scenario:
        scenario = Scenario(**values)
        db.add(scenario)
        db.commit()
        db.refresh(scenario)
        return scenario

    def get(self, db: Session, scenario_id: str) -> Scenario | None:
        return db.get(Scenario, scenario_id)

    def list_for_project(self, db: Session, project_id: str) -> list[Scenario]:
        stmt = select(Scenario).where(Scenario.project_id == project_id).order_by(Scenario.created_at.desc())
        return list(db.scalars(stmt).all())
