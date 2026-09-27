from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database.repositories.datasets import DatasetRepository
from app.database.repositories.scenarios import ScenarioRepository
from app.services.project_service import ProjectService


class PersistenceService:
    def __init__(self):
        self.projects = ProjectService()
        self.datasets = DatasetRepository()
        self.scenarios = ScenarioRepository()

    def create_dataset(self, db: Session, project_id: str, **values):
        self.projects.get(db, project_id)
        return self.datasets.create(db, project_id=project_id, **values)

    def create_scenario(self, db: Session, project_id: str, **values):
        self.projects.get(db, project_id)
        return self.scenarios.create(db, project_id=project_id, **values)

    def get_dataset(self, db: Session, dataset_id: str):
        record = self.datasets.get(db, dataset_id)
        if not record:
            raise NotFoundError("Dataset not found.")
        return record
