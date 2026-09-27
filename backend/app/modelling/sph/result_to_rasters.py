from __future__ import annotations

import csv
import json
import os
import re
import shutil
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import rasterio
from rasterio.transform import Affine

from app.core.config import get_settings


_FRAME_RE = re.compile(r"PartFluid(?:Ascii|Fallback|Recovered)?[_-]?(\d+)", re.IGNORECASE)
_NATIVE_FRAME_RE = re.compile(r"Part[_-]?(\d+)", re.IGNORECASE)
_COLUMN_ALIASES = {
    "x": {"x", "posx", "positionx", "pos.x", "position.x"},
    "y": {"y", "posy", "positiony", "pos.y", "position.y"},
    "z": {"z", "posz", "positionz", "pos.z", "position.z"},
    "vx": {"vx", "velx", "velocityx", "vel.x", "velocity.x"},
    "vy": {"vy", "vely", "velocityy", "vel.y", "velocity.y"},
    "vz": {"vz", "velz", "velocityz", "vel.z", "velocity.z"},
    "speed": {"velm", "vel.m", "speed", "velocitym", "velocity.m"},
}


def _normalise(name: str) -> str:
    # PartVTK CSVs can include units such as ``vel.x [m/s]`` and may use
    # punctuation/spacing variations. Normalize the physical quantity name
    # while deliberately discarding only bracketed unit annotations.
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", str(name).strip().lower())
    return re.sub(r"[^a-z0-9]", "", text)


def _find_column(columns: list[str], aliases: set[str]) -> str | None:
    lookup = {_normalise(column): column for column in columns}
    normalized_aliases = {_normalise(alias) for alias in aliases}
    for alias in normalized_aliases:
        if alias in lookup:
            return lookup[alias]
    return None


def _frame_number(path: Path) -> int:
    match = _FRAME_RE.search(path.stem)
    return int(match.group(1)) if match else -1


def _native_frame_number(path: Path) -> int:
    match = _NATIVE_FRAME_RE.search(path.stem)
    return int(match.group(1)) if match else -1


def discover_particle_frames(working_directory: Path) -> list[Path]:
    roots = [working_directory / "dual_sphysics", working_directory]
    files: set[Path] = set()
    for root in roots:
        if root.exists():
            files.update(path for path in root.rglob("PartFluid*.csv") if path.is_file())
    frames = sorted(files, key=lambda path: (_frame_number(path), str(path)))
    return [path for path in frames if _frame_number(path) >= 0]


def _locate_particle_csv_header(path: Path, *, max_scan_lines: int = 64) -> tuple[
    list[str] | None,
    dict[str, str | None] | None,
    str | None,
    int | None,
    str,
]:
    """Locate the actual particle-table header in a DualSPHysics CSV.

    PartVTK uses the common DualSPHysics CSV writer, which may emit one or more
    metadata/header lines before the actual particle column header. Native output
    can therefore begin with timestep/particle-count metadata before x/y/z and
    velocity columns.
    """
    first_columns: list[str] | None = None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for line_no, raw in enumerate(handle, 1):
                if line_no > max_scan_lines:
                    break
                line = raw.rstrip("\r\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                delimiter = _sniff_delimiter(line)
                try:
                    columns = [str(column).strip() for column in next(csv.reader([line], delimiter=delimiter))]
                except (StopIteration, csv.Error):
                    continue
                if first_columns is None:
                    first_columns = columns
                resolved = {name: _find_column(columns, aliases) for name, aliases in _COLUMN_ALIASES.items()}
                if all(resolved[name] for name in ("x", "y", "z")) and any(
                    resolved[name] for name in ("vx", "vy", "vz", "speed")
                ):
                    return columns, resolved, delimiter, line_no, f"header_line={line_no}; columns={columns[:20]}"
    except Exception as exc:
        return None, None, None, None, f"unable to read: {exc}"
    if not first_columns:
        return None, None, None, None, "empty file"
    return None, None, None, None, f"columns={first_columns[:20]}"


def _particle_csv_header(path: Path) -> tuple[bool, str]:
    columns, resolved, delimiter, header_line, detail = _locate_particle_csv_header(path)
    return bool(columns and resolved and delimiter and header_line is not None), detail


def _valid_particle_csv_frames(working_directory: Path) -> tuple[list[Path], list[str]]:
    candidates = discover_particle_frames(working_directory)
    valid: list[Path] = []
    skipped: list[str] = []
    for path in candidates:
        ok, detail = _particle_csv_header(path)
        if ok:
            valid.append(path)
        else:
            skipped.append(f"{path.name}: {detail}")
    return valid, skipped


def _frame_ids(paths: list[Path]) -> list[int]:
    return sorted({_frame_number(path) for path in paths if _frame_number(path) >= 0})


def _native_frame_ids(paths: list[Path]) -> list[int]:
    return sorted({_native_frame_number(path) for path in paths if _native_frame_number(path) >= 0})


def _resolve_partvtk_executable(explicit: str | Path | None = None) -> str | None:
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return str(candidate)
        if isinstance(explicit, str) and " " in explicit:
            parts = shlex.split(explicit)
            if parts and Path(parts[0]).is_file():
                return explicit
        resolved = shutil.which(str(explicit))
        return resolved
    settings = get_settings()
    configured = settings.dual_sph_partvtk
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
    bin_dir = settings.dual_sph_bin_dir or Path("/opt/dualsphysics/bin")
    default = bin_dir / ("PartVTK_linux64" if os.name != "nt" else "PartVTK_win64.exe")
    if default.is_file():
        return str(default)
    return shutil.which(default.name)


def _run_partvtk_csv_recovery(
    *,
    working_directory: Path,
    output_directory: Path,
    partvtk_executable: str | Path | None = None,
    timeout_s: float | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    """Regenerate canonical particle CSV frames from authoritative DualSPHysics BI4 output.

    DualSPHysics documents PartVTK CSV as particle output and separately exposes
    ``-savestatscsv`` for statistics. A target run can nevertheless leave a misleading
    ``PartFluid_*.csv`` file behind, so we regenerate a clean ASCII representation directly
    from the authoritative ``Part_*.bi4`` files.
    """
    executable = _resolve_partvtk_executable(partvtk_executable)
    if not executable:
        raise ValueError(
            "No PartVTK executable is available for native SPH result recovery. "
            "Configure HYDROSHIELD_DUAL_SPH_PARTVTK or install PartVTK_linux64."
        )
    data_dir = working_directory / "dual_sphysics" / "HydroShieldCase_out" / "data"
    if not data_dir.is_dir():
        # Some custom cases store data directly under the native working directory.
        candidates = [p for p in working_directory.rglob("Part_*.bi4") if p.is_file()]
        if not candidates:
            raise ValueError(f"No DualSPHysics Part_*.bi4 frames were found under {working_directory}.")
        data_dir = candidates[0].parent
    xml_candidates = [
        working_directory / "dual_sphysics" / "HydroShieldCase_out" / "HydroShieldCase.xml",
        working_directory / "dual_sphysics" / "HydroShieldCase_out" / "Case.xml",
    ]
    xml_path = next((p for p in xml_candidates if p.is_file()), None)
    if xml_path is None:
        xml_found = next(working_directory.rglob("*.xml"), None)
        xml_path = xml_found

    fallback_dir = output_directory / "particle_csv_recovery"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    prefix = fallback_dir / "PartFluidRecovered"
    stdout_log = fallback_dir / "partvtk.stdout.log"
    stderr_log = fallback_dir / "partvtk.stderr.log"
    executable_parts = shlex.split(str(executable))
    # Match the normal HydroShield PartVTK command contract. The official PartVTK
    # help explicitly supports `-filexml AUTO`, `-savecsv`, `-onlytype:-all,+fluid`,
    # `-vars:+idp,+vel,+rhop,+press,+type`, `-csvsep` and `-threads`. Using AUTO
    # avoids depending on whether the generated XML is named Case.xml or
    # HydroShieldCase.xml inside the native output directory.
    command = [
        *executable_parts,
        "-dirdata",
        str(data_dir),
        "-filexml",
        "AUTO",
        "-savecsv",
        str(prefix),
        "-onlytype:-all,+fluid",
        "-vars:+idp,+vel,+rhop,+press,+type",
        "-csvsep:1",
        "-createdirs:1",
        "-threads:2",
    ]
    timeout = float(timeout_s if timeout_s is not None else get_settings().model_timeout_s)
    started = time.perf_counter()
    with stdout_log.open("w", encoding="utf-8") as out, stderr_log.open("w", encoding="utf-8") as err:
        process = subprocess.Popen(
            command,
            cwd=working_directory,
            stdout=out,
            stderr=err,
            text=True,
            shell=False,
            env=os.environ.copy(),
        )
        while process.poll() is None:
            if time.perf_counter() - started >= timeout:
                process.kill()
                process.wait(timeout=5)
                raise ValueError(
                    f"PartVTK CSV recovery exceeded {timeout:.0f}s. "
                    f"See {stderr_log} and {stdout_log}."
                )
            time.sleep(0.05)
    if process.returncode != 0:
        detail = stderr_log.read_text(encoding="utf-8", errors="replace")[-3000:]
        raise ValueError(
            f"PartVTK CSV recovery failed with exit code {process.returncode}. "
            f"stderr: {detail.strip() or '(empty)'}"
        )
    # PartVTK normally emits one `<prefix>_NNNN.csv` per BI4 frame. Be slightly
    # more permissive here and inspect every CSV created in the recovery directory
    # so a harmless naming variation does not become a false processing failure.
    candidates = sorted(
        [p for p in fallback_dir.rglob("*.csv") if _FRAME_RE.search(p.stem)],
        key=lambda p: (_frame_number(p), str(p)),
    )
    valid_frames: list[Path] = []
    invalid_details: list[str] = []
    for path in candidates:
        ok, detail = _particle_csv_header(path)
        if ok:
            valid_frames.append(path)
        else:
            invalid_details.append(f"{path.name}: {detail}")
    frames = valid_frames
    if not frames:
        stdout_tail = stdout_log.read_text(encoding="utf-8", errors="replace")[-2000:]
        stderr_tail = stderr_log.read_text(encoding="utf-8", errors="replace")[-2000:]
        discovered = [str(p.relative_to(fallback_dir)) for p in fallback_dir.rglob("*.csv") if p.is_file()]
        raise ValueError(
            "PartVTK CSV recovery completed successfully but produced no valid particle CSV frame files. "
            f"discovered_csv={discovered[:20]}; invalid={invalid_details[:10]}; "
            f"stdout_tail={stdout_tail.strip() or '(empty)'}; "
            f"stderr_tail={stderr_tail.strip() or '(empty)'}. "
            f"See {stdout_log} and {stderr_log}."
        )
    native_ids = sorted({_native_frame_number(p) for p in data_dir.glob("Part_*.bi4") if p.is_file() and _native_frame_number(p) >= 0})
    recovered_ids = sorted({_frame_number(p) for p in frames if _frame_number(p) >= 0})
    if native_ids and recovered_ids != native_ids:
        missing = [frame_id for frame_id in native_ids if frame_id not in recovered_ids]
        unexpected = [frame_id for frame_id in recovered_ids if frame_id not in native_ids]
        raise ValueError(
            "PartVTK recovery did not produce a complete frame set. "
            f"authoritative={native_ids[:25]}{'...' if len(native_ids) > 25 else ''}; "
            f"recovered={recovered_ids[:25]}{'...' if len(recovered_ids) > 25 else ''}; "
            f"missing={missing[:25]}{'...' if len(missing) > 25 else ''}; "
            f"unexpected={unexpected[:25]}{'...' if len(unexpected) > 25 else ''}."
        )
    return frames, {
        "command": command,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "data_directory": str(data_dir),
        "xml_file": str(xml_path) if xml_path else None,
        "frame_count": len(frames),
        "format": "csv",
    }


def _ascii_chunks(path: Path, *, chunk_size: int) -> Iterator[tuple[np.ndarray, ...]]:
    xs: list[float] = []; ys: list[float] = []; zs: list[float] = []
    vxs: list[float] = []; vys: list[float] = []; vzs: list[float] = []
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        for line_no, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part for part in re.split(r"[;,\s]+", line) if part]
            if len(parts) < 6:
                continue
            try:
                values = [float(value) for value in parts[:6]]
            except ValueError:
                # Header-like or informational lines are ignored because saveascii is documented
                # as headerless, but some patched vendor builds may add one informational line.
                if line_no <= 3:
                    continue
                raise ValueError(f"Malformed PartVTK ASCII row in {path.name} at line {line_no}: {line[:180]}")
            x, y, z, vx, vy, vz = values
            xs.append(x); ys.append(y); zs.append(z); vxs.append(vx); vys.append(vy); vzs.append(vz)
            if len(xs) >= chunk_size:
                yield tuple(np.asarray(values, dtype="float64") for values in (xs, ys, zs, vxs, vys, vzs))
                xs.clear(); ys.clear(); zs.clear(); vxs.clear(); vys.clear(); vzs.clear()
    if xs:
        yield tuple(np.asarray(values, dtype="float64") for values in (xs, ys, zs, vxs, vys, vzs))


def _sniff_delimiter(header: str) -> str:
    candidates = [";", ",", "\t"]
    counts = {delimiter: header.count(delimiter) for delimiter in candidates}
    return max(candidates, key=counts.get) if max(counts.values()) else ";"


def _particle_columns(path: Path) -> tuple[list[str], dict[str, str | None], str, int]:
    columns, resolved, delimiter, header_line, detail = _locate_particle_csv_header(path)
    if columns is None or resolved is None or delimiter is None or header_line is None:
        detected = detail.replace("columns=", "Detected columns: ")
        raise ValueError(
            f"DualSPHysics particle output {path.name} does not contain a valid particle-table header. "
            f"{detected}"
        )
    return columns, resolved, delimiter, header_line


def _float_or_nan(value: str) -> float:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return float("nan")


def _particle_chunks(
    path: Path,
    *,
    columns: list[str],
    resolved: dict[str, str | None],
    delimiter: str,
    header_line: int,
    chunk_size: int,
) -> Iterator[tuple[np.ndarray, ...]]:
    index = {name: i for i, name in enumerate(columns)}
    required_indices = {name: index[column] for name, column in resolved.items() if column is not None}
    x_i, y_i, z_i = required_indices["x"], required_indices["y"], required_indices["z"]
    vx_i = required_indices.get("vx")
    vy_i = required_indices.get("vy")
    vz_i = required_indices.get("vz")
    speed_i = required_indices.get("speed")
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    vxs: list[float] = []
    vys: list[float] = []
    vzs: list[float] = []
    speeds: list[float] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for csv_line_no, row in enumerate(reader, 1):
            if csv_line_no <= header_line:
                continue
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) < len(columns):
                row = [*row, *( [""] * (len(columns) - len(row)) )]
            xs.append(_float_or_nan(row[x_i]))
            ys.append(_float_or_nan(row[y_i]))
            zs.append(_float_or_nan(row[z_i]))
            if vx_i is not None:
                vxs.append(_float_or_nan(row[vx_i]))
            if vy_i is not None:
                vys.append(_float_or_nan(row[vy_i]))
            if vz_i is not None:
                vzs.append(_float_or_nan(row[vz_i]))
            if speed_i is not None:
                speeds.append(_float_or_nan(row[speed_i]))
            if len(xs) >= chunk_size:
                yield (
                    np.asarray(xs, dtype="float64"),
                    np.asarray(ys, dtype="float64"),
                    np.asarray(zs, dtype="float64"),
                    np.asarray(vxs, dtype="float64") if vx_i is not None else None,
                    np.asarray(vys, dtype="float64") if vy_i is not None else None,
                    np.asarray(vzs, dtype="float64") if vz_i is not None else None,
                    np.asarray(speeds, dtype="float64") if speed_i is not None else None,
                )
                xs.clear(); ys.clear(); zs.clear(); vxs.clear(); vys.clear(); vzs.clear(); speeds.clear()
    if xs:
        yield (
            np.asarray(xs, dtype="float64"), np.asarray(ys, dtype="float64"), np.asarray(zs, dtype="float64"),
            np.asarray(vxs, dtype="float64") if vx_i is not None else None,
            np.asarray(vys, dtype="float64") if vy_i is not None else None,
            np.asarray(vzs, dtype="float64") if vz_i is not None else None,
            np.asarray(speeds, dtype="float64") if speed_i is not None else None,
        )


def _coords_to_cells(xs: np.ndarray, ys: np.ndarray, transform: Affine, width: int, height: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if abs(transform.b) > 1e-9 or abs(transform.d) > 1e-9:
        # Automatic HydroShield DEMs are north-up, but handling a rotated grid here
        # avoids silently writing particles to incorrect cells for custom inputs.
        inv = ~transform
        cols_f, rows_f = np.asarray(inv * (xs, ys), dtype="float64")
    else:
        cols_f = (xs - transform.c) / transform.a
        rows_f = (ys - transform.f) / transform.e
    cols = np.floor(cols_f).astype("int64")
    rows = np.floor(rows_f).astype("int64")
    valid = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
    return rows, cols, valid


def _write_raster(path: Path, array: np.ndarray, *, reference: rasterio.DatasetReader, nodata: float = -9999.0) -> None:
    output = np.where(np.isfinite(array), array, nodata).astype("float32")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=reference.width,
        height=reference.height,
        count=1,
        dtype="float32",
        crs=reference.crs,
        transform=reference.transform,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(output, 1)


def build_sph_analysis_rasters(
    *,
    working_directory: str | Path,
    dem_path: str | Path,
    output_directory: str | Path,
    output_interval_s: float,
    flood_threshold_m: float = 0.05,
    chunk_size: int = 100_000,
    partvtk_executable: str | Path | None = None,
    fallback_timeout_s: float | None = None,
) -> dict[str, Any]:
    """Convert native DualSPHysics particle frames into common analysis rasters.

    The conversion is intentionally conservative: each raster cell takes the maximum
    fluid-particle elevation/speed observed in that cell. Water depth is then derived
    as maximum particle elevation minus the DEM. Arrival time is the first frame whose
    reconstructed depth exceeds the configured flood threshold.
    """
    if output_interval_s <= 0:
        raise ValueError("SPH output interval must be positive.")
    if flood_threshold_m < 0:
        raise ValueError("Flood threshold must be non-negative.")

    working_directory = Path(working_directory).resolve()
    dem_path = Path(dem_path).resolve()
    output_directory = Path(output_directory).resolve()
    frames, skipped_csv = _valid_particle_csv_frames(working_directory)
    fallback_provenance: dict[str, Any] | None = None
    particle_source_format = "csv"
    native_bi4 = sorted([p for p in working_directory.rglob("Part_*.bi4") if p.is_file()], key=lambda p: (_native_frame_number(p), str(p)))
    native_ids = _native_frame_ids(native_bi4)
    existing_ids = _frame_ids(frames)
    # If the normal simulation PartVTK step already produced a complete particle
    # frame set for the authoritative BI4 frames, reuse it. Running PartVTK a second
    # time is unnecessary and can turn a successful solver run into a post-processing
    # failure on hosts with stricter filesystem/runtime conditions.
    if native_bi4 and frames and existing_ids == native_ids:
        particle_source_format = "partvtk_csv"
    elif native_bi4:
        executable = _resolve_partvtk_executable(partvtk_executable)
        if executable:
            fallback_frames, fallback_provenance = _run_partvtk_csv_recovery(
                working_directory=working_directory,
                output_directory=output_directory,
                partvtk_executable=executable,
                timeout_s=fallback_timeout_s,
            )
            frames = fallback_frames
            particle_source_format = "partvtk_csv_recovery"
        elif not frames:
            raise ValueError(
                "Native DualSPHysics Part_*.bi4 frames exist, but PartVTK is unavailable and no valid particle CSV frames exist for recovery."
            )
    elif not frames:
        if skipped_csv:
            detail = skipped_csv[0].split(": ", 1)[1] if ": " in skipped_csv[0] else skipped_csv[0]
            detected = detail.replace("columns=", "Detected columns: ").replace("[", "").replace("]", "").replace("'", "")
            raise ValueError(
                "No valid native SPH particle frames were found and no authoritative Part_*.bi4 frames exist for recovery. "
                + f"The first PartFluid CSV was not particle data ({detected})."
            )
        raise ValueError(
            "No PartFluid particle frames were found in the completed SPH working directory and no Part_*.bi4 frames exist for recovery."
        )
    elif skipped_csv:
        skipped_csv = skipped_csv[:25]
    if not dem_path.is_file():
        raise ValueError(f"Preprocessed DEM for native SPH analysis does not exist: {dem_path}")

    output_directory.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dem_path) as dem_src:
        if dem_src.count != 1:
            raise ValueError("Preprocessed DEM for native SPH analysis must contain exactly one band.")
        if dem_src.crs is None or not bool(getattr(dem_src.crs, "is_projected", False)):
            raise ValueError("Preprocessed DEM for native SPH analysis must use a projected CRS.")
        dem = dem_src.read(1, masked=True).filled(np.nan).astype("float64")
        reference_profile = dem_src.profile.copy()
        width, height = dem_src.width, dem_src.height
        transform = dem_src.transform
        if abs(transform.a) <= 0 or abs(transform.e) <= 0:
            raise ValueError("Preprocessed DEM has an invalid cell size.")

        max_surface = np.full((height, width), np.nan, dtype="float64")
        max_speed = np.full((height, width), np.nan, dtype="float64")
        arrival_time = np.full((height, width), np.nan, dtype="float64")
        frame_particle_counts: list[dict[str, Any]] = []
        frames_with_outside_particles = 0
        total_particles = 0
        total_particles_in_dem_grid = 0
        particle_x_min = float("inf")
        particle_x_max = float("-inf")
        particle_y_min = float("inf")
        particle_y_max = float("-inf")
        particle_z_min = float("inf")
        particle_z_max = float("-inf")

        for frame_path in frames:
            frame_surface = np.full((height * width,), -np.inf, dtype="float64")
            frame_speed = np.full((height * width,), -np.inf, dtype="float64")
            frame_count = 0
            frame_valid_count = 0
            try:
                columns, resolved, delimiter, header_line = _particle_columns(frame_path)
                particle_iter = _particle_chunks(
                    frame_path,
                    columns=columns,
                    resolved=resolved,
                    delimiter=delimiter,
                    header_line=header_line,
                    chunk_size=chunk_size,
                )
                for x, y, z, vx, vy, vz, speed_values in particle_iter:
                    finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
                    frame_count += int(finite.sum())
                    if not np.any(finite):
                        continue

                    x = x[finite]; y = y[finite]; z = z[finite]
                    total_particles += int(x.size)
                    particle_x_min = min(particle_x_min, float(np.min(x)))
                    particle_x_max = max(particle_x_max, float(np.max(x)))
                    particle_y_min = min(particle_y_min, float(np.min(y)))
                    particle_y_max = max(particle_y_max, float(np.max(y)))
                    particle_z_min = min(particle_z_min, float(np.min(z)))
                    particle_z_max = max(particle_z_max, float(np.max(z)))
                    rows, cols, in_bounds = _coords_to_cells(x, y, transform, width, height)
                    if not np.any(in_bounds):
                        continue
                    rows = rows[in_bounds]; cols = cols[in_bounds]; z = z[in_bounds]
                    flat = rows * width + cols
                    np.maximum.at(frame_surface, flat, z)

                    if vx is not None or vy is not None or vz is not None:
                        vx_arr = vx[finite][in_bounds] if vx is not None else np.zeros_like(z)
                        vy_arr = vy[finite][in_bounds] if vy is not None else np.zeros_like(z)
                        vz_arr = vz[finite][in_bounds] if vz is not None else np.zeros_like(z)
                        speed = np.sqrt(vx_arr * vx_arr + vy_arr * vy_arr + vz_arr * vz_arr)
                    elif speed_values is not None:
                        speed = speed_values[finite][in_bounds]
                    else:
                        speed = np.zeros_like(z)
                    valid_speed = np.isfinite(speed)
                    if np.any(valid_speed):
                        np.maximum.at(frame_speed, flat[valid_speed], speed[valid_speed])
                    frame_valid_count += int(in_bounds.sum())
                    total_particles_in_dem_grid += int(in_bounds.sum())
            except Exception as exc:
                raise ValueError(f"Unable to process native SPH frame {frame_path.name}: {exc}") from exc

            surface = frame_surface.reshape(height, width)
            speed = frame_speed.reshape(height, width)
            surface_finite = np.isfinite(surface)
            valid_domain = surface_finite & np.isfinite(dem)
            frame_depth = np.where(valid_domain, np.maximum(surface - dem, 0.0), np.nan)

            max_surface = np.where(
                valid_domain,
                np.where(np.isfinite(max_surface), np.maximum(max_surface, surface), surface),
                max_surface,
            )
            finite_speed = np.isfinite(speed)
            max_speed = np.where(
                finite_speed,
                np.where(np.isfinite(max_speed), np.maximum(max_speed, speed), speed),
                max_speed,
            )

            arrived = ~np.isfinite(arrival_time)
            arrived &= frame_depth > flood_threshold_m
            time_s = _frame_number(frame_path) * output_interval_s
            arrival_time[arrived] = float(time_s)
            if frame_count and frame_valid_count == 0:
                frames_with_outside_particles += 1
            frame_particle_counts.append(
                {
                    "frame": _frame_number(frame_path),
                    "file": str(frame_path),
                    "time_s": float(time_s),
                    "particle_count": frame_count,
                    "particles_in_dem_grid": frame_valid_count,
                }
            )

        if total_particles == 0:
            raise ValueError(
                "Native SPH particle CSVs contain no finite XYZ positions. "
                "The solver completed, but there is no spatial data from which HydroShield can reconstruct flood fields."
            )
        if total_particles_in_dem_grid == 0:
            bounds = {
                "dem": {
                    "left": float(dem_src.bounds.left),
                    "bottom": float(dem_src.bounds.bottom),
                    "right": float(dem_src.bounds.right),
                    "top": float(dem_src.bounds.top),
                    "crs": dem_src.crs.to_string() if dem_src.crs else None,
                },
                "particles": {
                    "x_min": particle_x_min, "x_max": particle_x_max,
                    "y_min": particle_y_min, "y_max": particle_y_max,
                    "z_min": particle_z_min, "z_max": particle_z_max,
                },
            }
            raise ValueError(
                "Native SPH particles do not overlap the preprocessed DEM grid. "
                f"DEM bounds={bounds['dem']}; particle bounds={bounds['particles']}. "
                "This usually indicates a coordinate-system/origin mismatch between the native solver output and the DEM."
            )

        max_depth = np.where(np.isfinite(max_surface) & np.isfinite(dem), np.maximum(max_surface - dem, 0.0), np.nan)
        max_depth[~np.isfinite(dem)] = np.nan
        max_speed[~np.isfinite(max_depth) | (max_depth <= 0)] = np.nan
        arrival_time[~np.isfinite(max_depth) | (max_depth <= flood_threshold_m)] = np.nan

        depth_path = output_directory / "water_depth_max.tif"
        velocity_path = output_directory / "velocity_max.tif"
        arrival_path = output_directory / "arrival_time.tif"
        water_level_path = output_directory / "water_level_max.tif"
        _write_raster(depth_path, max_depth, reference=dem_src)
        _write_raster(velocity_path, max_speed, reference=dem_src)
        _write_raster(arrival_path, arrival_time, reference=dem_src)
        _write_raster(water_level_path, max_surface, reference=dem_src)

    finite_depth = max_depth[np.isfinite(max_depth)]
    flood_cells = int(np.count_nonzero(np.isfinite(max_depth) & (max_depth > flood_threshold_m)))
    max_depth_value = float(finite_depth.max()) if finite_depth.size else 0.0
    finite_velocity = max_speed[np.isfinite(max_speed)]
    max_velocity_value = float(finite_velocity.max()) if finite_velocity.size else 0.0
    arrival_values = arrival_time[np.isfinite(arrival_time)]
    frame_ids = [_frame_number(path) for path in frames]
    min_frame = min(frame_ids) if frame_ids else None
    max_frame = max(frame_ids) if frame_ids else None
    expected_frame_ids = list(range(min_frame, max_frame + 1)) if min_frame is not None and max_frame is not None else []
    missing_frame_ids = [frame_id for frame_id in expected_frame_ids if frame_id not in set(frame_ids)]
    valid_dem_cells = int(np.count_nonzero(np.isfinite(dem)))
    wet_cell_coverage_fraction = float(
        np.count_nonzero(np.isfinite(max_depth)) / valid_dem_cells
    ) if valid_dem_cells else 0.0

    warnings: list[str] = [
        "Native SPH analysis reconstructs raster fields from the maximum fluid-particle elevation/speed observed per DEM cell.",
        "Arrival time is derived from the first particle frame whose reconstructed water depth exceeds the configured flood threshold.",
    ]
    if skipped_csv:
        warnings.append(
            "Skipped non-particle PartFluid CSV outputs and used the authoritative BI4 frames for recovery: "
            + "; ".join(skipped_csv[:10])
        )
    if particle_source_format == "partvtk_csv_recovery":
        warnings.append(
            "HydroShield regenerated canonical particle CSV frames with PartVTK from the authoritative BI4 solver outputs."
        )
    elif particle_source_format == "partvtk_csv":
        warnings.append(
            "HydroShield used the complete PartVTK particle CSV frame set already generated from the authoritative BI4 solver outputs."
        )
    if frames_with_outside_particles:
        warnings.append(
            f"{frames_with_outside_particles} particle frame(s) had particles but none landed inside the preprocessed DEM grid."
        )
    if missing_frame_ids:
        warnings.append(
            "Native SPH frame sequence contains missing frame ids: "
            + ", ".join(str(value) for value in missing_frame_ids[:25])
            + (" ..." if len(missing_frame_ids) > 25 else "")
        )
    if wet_cell_coverage_fraction < 0.05:
        warnings.append(
            f"Native SPH particle coverage is sparse ({wet_cell_coverage_fraction:.1%} of valid DEM cells); raster values are only reported where particle support was observed."
        )
    if not flood_cells:
        warnings.append("No DEM cells exceeded the flood threshold in the reconstructed native SPH result.")
    if len(frame_ids) == 1:
        warnings.append("Only one native SPH output frame was available; arrival-time results are limited to that single observation time.")
    if native_bi4:
        authoritative_ids = sorted({_native_frame_number(path) for path in native_bi4 if _native_frame_number(path) >= 0})
        if authoritative_ids and frame_ids != authoritative_ids:
            warnings.append("Processed native SPH frame ids differ from the authoritative BI4 frame ids; inspect native_sph_result_manifest.json.")

    native_manifest = output_directory / "native_sph_result_manifest.json"
    manifest_payload = {
        "schema_version": "1.1",
        "particle_source_format": particle_source_format,
        "authoritative_bi4_frame_count": len(native_bi4),
        "authoritative_bi4_frame_ids": sorted({_native_frame_number(path) for path in native_bi4 if _native_frame_number(path) >= 0}),
        "processed_frame_count": len(frames),
        "processed_frame_ids": frame_ids,
        "missing_frame_ids": missing_frame_ids,
        "output_interval_s": float(output_interval_s),
        "flood_threshold_m": float(flood_threshold_m),
        "summary": {
            "max_water_depth_m": max_depth_value,
            "max_velocity_mps": max_velocity_value,
            "inundated_cell_count": flood_cells,
            "wet_cell_coverage_fraction": wet_cell_coverage_fraction,
            "first_arrival_time_s": float(arrival_values.min()) if arrival_values.size else None,
        },
        "provenance": fallback_provenance,
    }
    native_manifest.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "water_depth_raster": str(depth_path),
        "velocity_raster": str(velocity_path),
        "arrival_time_raster": str(arrival_path),
        "water_level_raster": str(water_level_path),
        "summary": {
            "time_steps": len(frames),
            "max_water_depth_m": max_depth_value,
            "max_velocity_mps": max_velocity_value,
            "inundated_cell_count": flood_cells,
            "first_arrival_time_s": float(arrival_values.min()) if arrival_values.size else None,
            "frames": frame_particle_counts,
            "frame_ids": frame_ids,
            "missing_frame_ids": missing_frame_ids,
            "wet_cell_coverage_fraction": wet_cell_coverage_fraction,
        },
        "warnings": warnings,
        "native_result_manifest": str(native_manifest),
        "provenance": {
            "dem_path": str(dem_path),
            "working_directory": str(working_directory),
            "output_interval_s": float(output_interval_s),
            "flood_threshold_m": float(flood_threshold_m),
            "frame_count": len(frames),
            "particle_source_format": particle_source_format,
            "skipped_particle_csvs": skipped_csv,
            "partvtk_fallback": fallback_provenance,
            "crs": reference_profile.get("crs").to_string() if reference_profile.get("crs") else None,
            "grid_shape": [height, width],
            "cell_size_m": [abs(float(transform.a)), abs(float(transform.e))],
            "particle_bounds": {
                "x_min": particle_x_min, "x_max": particle_x_max,
                "y_min": particle_y_min, "y_max": particle_y_max,
                "z_min": particle_z_min, "z_max": particle_z_max,
            },
            "particle_count_total": total_particles,
            "particle_count_in_dem_grid": total_particles_in_dem_grid,
        },
    }
