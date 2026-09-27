from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Project


class ProjectRepository:
    def create(self, db: Session, *, name: str, description: str | None = None) -> Project:
        project = Project(name=name.strip(), description=description)
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    def get(self, db: Session, project_id: str) -> Project | None:
        return db.get(Project, project_id)

    def list(self, db: Session) -> list[Project]:
        return list(db.scalars(select(Project).order_by(Project.created_at.desc())).all())
