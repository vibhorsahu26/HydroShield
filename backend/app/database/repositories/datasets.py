from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Dataset


class DatasetRepository:
    def create(self, db: Session, **values) -> Dataset:
        values.setdefault("acquired_at", datetime.now(timezone.utc) if values.get("acquisition_run_id") else None)
        dataset = Dataset(**values)
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        return dataset

    def get(self, db: Session, dataset_id: str) -> Dataset | None:
        return db.get(Dataset, dataset_id)

    def list_for_project(self, db: Session, project_id: str) -> list[Dataset]:
        stmt = select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())
        return list(db.scalars(stmt).all())
