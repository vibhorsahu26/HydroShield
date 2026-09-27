from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.database.models import Project
from app.database.repositories.projects import ProjectRepository


class ProjectService:
    def __init__(self, repo: ProjectRepository | None = None):
        self.repo = repo or ProjectRepository()

    def create(self, db: Session, name: str, description: str | None) -> Project:
        existing = next((p for p in self.repo.list(db) if p.name.casefold() == name.strip().casefold()), None)
        if existing:
            raise ConflictError("A project with this name already exists.")
        return self.repo.create(db, name=name, description=description)

    def get(self, db: Session, project_id: str) -> Project:
        project = self.repo.get(db, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project
