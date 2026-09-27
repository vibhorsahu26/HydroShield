from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import uuid

from app.database.repositories.projects import ProjectRepository
from app.schemas.datasets import DatasetType
from app.services.dataset_validator import validate_dataset


@dataclass(frozen=True)
class StoredDataset:
    path: Path
    size_bytes: int
    sha256: str


class DatasetStorageService:
    def __init__(self, root: Path):
        self.root = root
        self.projects = ProjectRepository()

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
        if not name:
            raise ValueError("Filename is invalid after sanitization.")
        return name[:180]

    def store(self, project_id: str, filename: str, data: bytes, *, dataset_type: DatasetType) -> StoredDataset:
        if not project_id or Path(project_id).name != project_id:
            raise ValueError("Project identifier is invalid for storage.")
        target_dir = self.root / project_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_filename(filename)
        path = target_dir / f"{uuid.uuid4().hex}_{safe_name}"
        path.write_bytes(data)
        return StoredDataset(path.resolve(), len(data), sha256(data).hexdigest())

    def validate_and_store(
        self,
        project_id: str,
        filename: str,
        data: bytes,
        dataset_type: DatasetType,
        *,
        max_upload_bytes: int | None = None,
    ) -> tuple[dict, StoredDataset]:
        validation = validate_dataset(
            data,
            filename,
            dataset_type,
            max_upload_bytes=max_upload_bytes or 50 * 1024 * 1024,
        )
        if not validation.valid:
            raise ValueError(f"Dataset validation failed: {'; '.join(validation.errors)}")
        stored = self.store(project_id, filename, data, dataset_type=dataset_type)
        return validation.model_dump(mode="json"), stored
