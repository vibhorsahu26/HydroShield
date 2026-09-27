from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


_COLUMNS = {
    "x": {"x", "posx", "positionx", "pos.x", "position.x"},
    "y": {"y", "posy", "positiony", "pos.y", "position.y"},
    "z": {"z", "posz", "positionz", "pos.z", "position.z"},
    "vx": {"vx", "velx", "velocityx", "vel.x", "velocity.x"},
    "vy": {"vy", "vely", "velocityy", "vel.y", "velocity.y"},
    "vz": {"vz", "velz", "velocityz", "vel.z", "velocity.z"},
    "speed": {"velm", "vel.m", "speed", "velocitym", "velocity.m"},
}


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", name.strip().lower())


def _find_column(columns: list[str], aliases: set[str]) -> str | None:
    normalised = {_normalise(c): c for c in columns}
    for alias in aliases:
        if alias in normalised:
            return normalised[alias]
    return None


def _csv_files(working_directory: Path) -> list[Path]:
    search_roots = [working_directory / "dual_sphysics", working_directory]
    found: list[Path] = []
    for root in search_roots:
        if root.exists():
            found.extend(root.rglob("PartFluid*.csv"))
    return sorted(set(found))


def _parse_particle_csv(path: Path) -> tuple[int, float | None]:
    try:
        frame = pd.read_csv(path, sep=None, engine="python")
    except Exception as exc:
        raise ValueError(f"Unable to parse DualSPHysics particle CSV {path.name}: {exc}") from exc

    if frame.empty:
        return 0, None

    vx_col = _find_column(list(frame.columns), _COLUMNS["vx"])
    vy_col = _find_column(list(frame.columns), _COLUMNS["vy"])
    vz_col = _find_column(list(frame.columns), _COLUMNS["vz"])
    speed_col = _find_column(list(frame.columns), _COLUMNS["speed"])
    max_speed: float | None = None
    if vx_col or vy_col or vz_col:
        vx = pd.to_numeric(frame[vx_col], errors="coerce") if vx_col else 0.0
        vy = pd.to_numeric(frame[vy_col], errors="coerce") if vy_col else 0.0
        vz = pd.to_numeric(frame[vz_col], errors="coerce") if vz_col else 0.0
        speed = (vx * vx + vy * vy + vz * vz) ** 0.5
        if speed.notna().any():
            max_speed = float(speed.max())
    elif speed_col:
        speed = pd.to_numeric(frame[speed_col], errors="coerce")
        if speed.notna().any():
            max_speed = float(speed.max())

    return int(len(frame)), max_speed


def parse_results(working_directory: Path) -> tuple[dict[str, Any] | None, list[Path], list[str]]:
    warnings: list[str] = []
    all_files = [p for p in working_directory.rglob("*") if p.is_file()]
    csv_files = _csv_files(working_directory)
    if not csv_files:
        return None, all_files, [
            "DualSPHysics adapter found no PartFluid*.csv output. "
            "Run PartVTK after the solver to generate canonical particle analysis files."
        ]

    particle_counts: list[int] = []
    max_velocities: list[float] = []
    skipped_nonparticle: list[str] = []
    parse_failures: list[str] = []
    for path in csv_files:
        try:
            frame = pd.read_csv(path, sep=None, engine="python", nrows=0)
            columns = list(frame.columns)
            if not all(_find_column(columns, _COLUMNS[name]) for name in ("x", "y", "z")):
                skipped_nonparticle.append(f"{path.name}: columns={columns[:20]}")
                continue
            count, max_speed = _parse_particle_csv(path)
            particle_counts.append(count)
            if max_speed is not None:
                max_velocities.append(max_speed)
        except ValueError as exc:
            parse_failures.append(str(exc))
        except Exception as exc:
            parse_failures.append(f"Unable to inspect DualSPHysics particle CSV {path.name}: {exc}")

    if parse_failures:
        return None, all_files, parse_failures
    if not particle_counts:
        warnings = [
            "DualSPHysics produced PartFluid CSV files, but none are particle tables with X/Y/Z coordinates. "
            "The native result pipeline will recover particle data from the authoritative BI4 frames with PartVTK."
        ]
        if skipped_nonparticle:
            warnings.append("Skipped non-particle CSV outputs: " + "; ".join(skipped_nonparticle[:10]))
        return None, all_files, warnings

    summary: dict[str, Any] = {
        "time_steps": len(csv_files),
        "wet_cell_count": max(particle_counts),
        "particle_count": particle_counts[-1],
    }
    if max_velocities:
        summary["max_velocity_mps"] = max(max_velocities)

    warnings.append(
        "DualSPHysics particle output does not directly provide a DEM-relative water-depth raster or "
        "flood polygon. Maximum water depth, inundated area, and first-arrival time remain Phase 8 analysis outputs."
    )
    if skipped_nonparticle:
        warnings.append("Skipped non-particle CSV outputs: " + "; ".join(skipped_nonparticle[:10]))
    return summary, all_files, warnings
