from __future__ import annotations

from pathlib import Path
import re
import uuid


class AnalysisInputStorageService:
    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
        if not name:
            raise ValueError("Analysis input filename is invalid.")
        return name[:180]

    def store(self, job_id: str, field: str, filename: str, data: bytes) -> Path:
        if not job_id or Path(job_id).name != job_id:
            raise ValueError("Simulation job identifier is invalid for storage.")
        target = self.root / "analysis-inputs" / job_id
        target.mkdir(parents=True, exist_ok=True)
        path = (target / f"{field}_{uuid.uuid4().hex}_{self._safe_filename(filename)}").resolve()
        if target.resolve() not in path.parents:
            raise ValueError("Analysis input path escapes the job directory.")
        path.write_bytes(data)
        return path
