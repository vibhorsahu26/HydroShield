from __future__ import annotations

from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile
from stat import S_IFMT, S_IFLNK
import re
import uuid


class ModelInputStorageService:
    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def _safe_project_id(project_id: str) -> str:
        if not project_id or Path(project_id).name != project_id or not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
            raise ValueError("Project identifier is invalid for storage.")
        return project_id

    @staticmethod
    def _safe_member(name: str) -> str:
        normalized = name.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"Unsafe ZIP member path: {name}")
        return "/".join(path.parts)

    @staticmethod
    def _is_symlink(info) -> bool:
        return S_IFMT(info.external_attr >> 16) == S_IFLNK

    def store_zip(self, project_id: str, model: str, filename: str, data: bytes) -> tuple[Path, list[str]]:
        project_id = self._safe_project_id(project_id)
        if model not in {"sph", "delft3d"}:
            raise ValueError("Model input upload requires 'sph' or 'delft3d'.")
        if not filename.lower().endswith(".zip"):
            raise ValueError("Model input package must be a ZIP file.")

        target = (self.root / "inputs" / project_id / f"{uuid.uuid4().hex}_{model}").resolve()
        target.mkdir(parents=True, exist_ok=False)
        try:
            with __import__("io").BytesIO(data) as stream:
                try:
                    archive = ZipFile(stream)
                except BadZipFile as exc:
                    raise ValueError("Model input ZIP is invalid or corrupt.") from exc
                with archive:
                    members = []
                    for info in archive.infolist():
                        safe = self._safe_member(info.filename)
                        if not safe:
                            continue
                        if self._is_symlink(info):
                            raise ValueError("ZIP contains a symbolic link, which is not allowed.")
                        members.append(safe)
                        destination = (target / safe).resolve()
                        if target not in destination.parents and destination != target:
                            raise ValueError("ZIP member escapes the model-input directory.")
                    archive.extractall(target)

            extracted_files = [p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()]
            lowered = {name.lower() for name in extracted_files}
            if model == "sph":
                if not any(Path(name).name.lower() == "case_def.xml" for name in extracted_files):
                    raise ValueError("DualSPHysics package must contain Case_Def.xml.")
            else:
                has_mdu = any(Path(name).suffix.lower() == ".mdu" for name in extracted_files)
                has_dimr = any(Path(name).name.lower() in {"dimr_config.xml", "dimr_config.xml.in"} for name in extracted_files)
                if not (has_mdu or has_dimr):
                    raise ValueError("Delft3D package must contain an .mdu file or DIMR configuration.")
            return target, sorted(extracted_files)
        except Exception:
            import shutil
            shutil.rmtree(target, ignore_errors=True)
            raise
