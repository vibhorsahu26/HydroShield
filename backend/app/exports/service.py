from __future__ import annotations

import csv
import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import rasterio
from shapely.geometry import mapping


class ExportError(ValueError):
    pass


RASTER_ARTIFACT_KEYS = {
    "water_depth": "water_depth_raster",
    "flood_mask": "flood_mask_raster",
    "velocity": "velocity_raster",
    "arrival_time": "arrival_time_raster",
    "water_level": "water_level_raster",
}


def _existing_path(path_value: str | None, label: str) -> Path:
    if not path_value:
        raise ExportError(f"Analysis result does not contain the '{label}' artifact.")
    path = Path(path_value).resolve()
    if not path.exists() or not path.is_file():
        raise ExportError(f"Artifact does not exist: {path}")
    return path


def _write_metrics_csv(result: Any, path: Path) -> None:
    metrics = result.metrics or {}
    exposure = result.exposure or {}
    rows: list[dict[str, Any]] = []
    for key, value in metrics.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True)
        rows.append({"section": "metrics", "key": key, "value": value})
    rows.append({"section": "exposure", "key": "exposed_area_m2", "value": exposure.get("exposed_area_m2")})
    for layer_name, layer_data in (exposure.get("layers") or {}).items():
        for key, value in layer_data.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, sort_keys=True)
            rows.append({"section": f"exposure:{layer_name}", "key": key, "value": value})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["section", "key", "value"])
        writer.writeheader()
        writer.writerows(rows)


def _write_json(result: Any, path: Path) -> None:
    payload = {
        "id": result.id,
        "simulation_job_id": result.simulation_job_id,
        "project_id": result.project_id,
        "scenario_id": result.scenario_id,
        "variant_id": result.variant_id,
        "analysis_version": result.analysis_version,
        "flood_threshold_m": result.flood_threshold_m,
        "metrics": result.metrics,
        "exposure": result.exposure,
        "artifacts": result.artifacts,
        "warnings": result.warnings,
        "assumptions": result.assumptions,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_geojson(source: Path, destination: Path) -> None:
    gdf = gpd.read_file(source)
    if gdf.crs is None:
        raise ExportError("Vector artifact has no CRS.")
    # GeoJSON served to the browser must use geographic WGS84 coordinates.
    # Keep stored analysis artifacts in their native/project CRS, but make the
    # export boundary explicit so Leaflet receives the coordinate system it expects.
    gdf = gdf.to_crs("EPSG:4326")
    destination.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(destination, driver="GeoJSON")


def _write_shapefile_zip(source: Path, destination: Path) -> None:
    gdf = gpd.read_file(source)
    if gdf.crs is None:
        raise ExportError("Vector artifact has no CRS.")
    with tempfile.TemporaryDirectory(prefix="hydroshield-shp-") as tmp:
        shp_dir = Path(tmp) / "flood_extent"
        shp_dir.mkdir(parents=True)
        shp_path = shp_dir / "flood_extent.shp"
        gdf.to_file(shp_path, driver="ESRI Shapefile")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(shp_dir.iterdir()):
                archive.write(file, arcname=file.name)


def _write_kml(source: Path, destination: Path) -> None:
    gdf = gpd.read_file(source)
    if gdf.crs is None:
        raise ExportError("Vector artifact has no CRS.")
    gdf = gdf.to_crs("EPSG:4326")
    destination.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(destination, driver="KML", layer="flood_extent")


def _copy_geotiff(source: Path, destination: Path) -> None:
    with rasterio.open(source) as src:
        if src.crs is None:
            raise ExportError("Raster artifact has no CRS.")
        profile = src.profile.copy()
        profile.update(driver="GTiff", compress="deflate")
        if not profile.get("tiled", False):
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(destination, "w", **profile) as dst:
            dst.write(src.read())


def export_analysis(result: Any, export_format: str, artifact: str | None, work_dir: Path) -> tuple[Path, str]:
    export_format = export_format.lower()
    work_dir.mkdir(parents=True, exist_ok=True)
    stamp = result.id[:8]

    if export_format == "geojson":
        source = _existing_path(result.artifacts.get("flood_extent_geojson"), "flood extent")
        destination = work_dir / f"hydroshield_{stamp}_flood_extent.geojson"
        _write_geojson(source, destination)
        return destination, "application/geo+json"

    if export_format == "shp":
        source = _existing_path(result.artifacts.get("flood_extent_geojson"), "flood extent")
        destination = work_dir / f"hydroshield_{stamp}_flood_extent_shapefile.zip"
        _write_shapefile_zip(source, destination)
        return destination, "application/zip"

    if export_format == "kml":
        source = _existing_path(result.artifacts.get("flood_extent_geojson"), "flood extent")
        destination = work_dir / f"hydroshield_{stamp}_flood_extent.kml"
        _write_kml(source, destination)
        return destination, "application/vnd.google-earth.kml+xml"

    if export_format == "geotiff":
        key = RASTER_ARTIFACT_KEYS.get((artifact or "").lower())
        if not key:
            raise ExportError("For GeoTIFF export, artifact must be one of: water_depth, flood_mask, velocity, arrival_time, water_level.")
        source = _existing_path(result.artifacts.get(key), key)
        destination = work_dir / f"hydroshield_{stamp}_{artifact.lower()}.tif"
        _copy_geotiff(source, destination)
        return destination, "image/tiff"

    if export_format == "csv":
        destination = work_dir / f"hydroshield_{stamp}_analysis.csv"
        _write_metrics_csv(result, destination)
        return destination, "text/csv; charset=utf-8"

    if export_format == "json":
        destination = work_dir / f"hydroshield_{stamp}_analysis.json"
        _write_json(result, destination)
        return destination, "application/json"

    raise ExportError("Unsupported export format. Supported formats: geojson, shp, kml, geotiff, csv, json.")


def build_analysis_package(result: Any, work_dir: Path) -> tuple[Path, str]:
    work_dir.mkdir(parents=True, exist_ok=True)
    package_path = work_dir / f"hydroshield_{result.id[:8]}_exports.zip"
    with tempfile.TemporaryDirectory(prefix="hydroshield-export-package-") as tmp:
        tmpdir = Path(tmp)
        files: list[tuple[Path, str]] = []
        for fmt, artifact in [
            ("json", None),
            ("csv", None),
            ("geojson", None),
            ("shp", None),
            ("kml", None),
        ]:
            try:
                file_path, _ = export_analysis(result, fmt, artifact, tmpdir)
                files.append((file_path, file_path.name))
            except ExportError:
                continue
        for raster_name in RASTER_ARTIFACT_KEYS:
            try:
                file_path, _ = export_analysis(result, "geotiff", raster_name, tmpdir)
                files.append((file_path, file_path.name))
            except ExportError:
                continue
        if not files:
            raise ExportError("Analysis result has no exportable artifacts.")
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path, arcname in files:
                archive.write(file_path, arcname=arcname)
    return package_path, "application/zip"
