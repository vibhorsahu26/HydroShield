from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import Project
from app.database.repositories.projects import ProjectRepository
from app.schemas.datasets import DatasetType
from app.services.dataset_storage import DatasetStorageService


def make_dem() -> bytes:
    buf = io.BytesIO()
    with rasterio.open(
        buf, "w", driver="GTiff", width=2, height=2, count=1, dtype="float32", crs="EPSG:4326",
        transform=from_origin(77, 28, 0.001, 0.001), nodata=-9999,
    ) as dst:
        dst.write(np.ones((2, 2), dtype="float32"), 1)
    return buf.getvalue()


def test_validated_upload_is_stored_safely(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'storage.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    project = ProjectRepository().create(db, name="Storage Project")
    storage = DatasetStorageService(tmp_path / "uploads")
    validation, stored = storage.validate_and_store(project.id, "../../terrain.tif", make_dem(), DatasetType.DEM)
    assert validation["valid"] is True
    assert stored.path.exists()
    assert stored.path.parent == (tmp_path / "uploads" / project.id).resolve()
    assert ".." not in stored.path.name
    assert stored.sha256
    db.close(); engine.dispose()
