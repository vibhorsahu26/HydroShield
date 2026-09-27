from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from app.schemas.datasets import DatasetType, DatasetValidationResult


MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class FileClassification:
    kind: str
    format: str


RASTER_SUFFIXES = {".tif": "GeoTIFF", ".tiff": "GeoTIFF"}
VECTOR_SUFFIXES = {
    ".geojson": "GeoJSON",
    ".json": "GeoJSON",
    ".gpkg": "GeoPackage",
}
TABULAR_SUFFIXES = {".csv": "CSV"}


def classify_filename(filename: str) -> FileClassification:
    suffix = Path(filename).suffix.lower()
    if suffix in RASTER_SUFFIXES:
        return FileClassification("raster", RASTER_SUFFIXES[suffix])
    if suffix in VECTOR_SUFFIXES:
        return FileClassification("vector", VECTOR_SUFFIXES[suffix])
    if suffix in TABULAR_SUFFIXES:
        return FileClassification("tabular", TABULAR_SUFFIXES[suffix])
    raise ValueError(f"Unsupported input format: {suffix or '<no extension>'}")


def _validate_raster(data: bytes, filename: str, dataset_type: DatasetType, fmt: str) -> DatasetValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    shape = None
    bounds = None
    crs = None

    try:
        with rasterio.MemoryFile(data) as memfile:
            with memfile.open() as src:
                shape = (src.count, src.height, src.width)
                bounds = tuple(float(v) for v in src.bounds)
                crs = src.crs.to_string() if src.crs else None

                if src.crs is None:
                    errors.append("Raster has no coordinate reference system (CRS).")
                if src.width < 2 or src.height < 2:
                    errors.append("Raster dimensions must be at least 2x2 pixels.")
                if dataset_type == DatasetType.DEM and src.count != 1:
                    errors.append("DEM input must contain exactly one raster band.")

                sample = src.read(1, masked=True)
                if sample.count() == 0:
                    errors.append("Raster contains no valid cells in its first band.")
                elif not np.isfinite(sample.compressed()).all():
                    errors.append("Raster contains non-finite numeric values.")

                if dataset_type == DatasetType.SATELLITE and src.count < 1:
                    errors.append("Satellite raster must contain at least one band.")
    except Exception as exc:
        errors.append(f"Raster could not be opened: {exc}")

    return DatasetValidationResult(
        valid=not errors,
        dataset_type=dataset_type,
        filename=filename,
        format=fmt,
        crs=crs,
        shape=shape,
        bounds=bounds,
        warnings=warnings,
        errors=errors,
    )


def _expected_geometry_types(dataset_type: DatasetType) -> set[str] | None:
    return {
        DatasetType.RIVER: {"LineString", "MultiLineString"},
        DatasetType.DAM: {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"},
        DatasetType.SETTLEMENT: {"Point", "MultiPoint", "Polygon", "MultiPolygon"},
        DatasetType.INFRASTRUCTURE: {
            "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"
        },
        DatasetType.LANDCOVER: {"Polygon", "MultiPolygon"},
    }.get(dataset_type)


def _validate_vector(data: bytes, filename: str, dataset_type: DatasetType, fmt: str) -> DatasetValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    gdf: gpd.GeoDataFrame | None = None

    try:
        suffix = Path(filename).suffix.lower()
        if suffix in {".geojson", ".json"}:
            gdf = gpd.read_file(io.BytesIO(data))
        else:
            with NamedTemporaryFile(suffix=suffix) as tmp:
                tmp.write(data)
                tmp.flush()
                gdf = gpd.read_file(tmp.name)

        if gdf is None or gdf.empty:
            errors.append("Vector dataset contains no features.")
        else:
            crs = gdf.crs.to_string() if gdf.crs else None
            if gdf.crs is None:
                errors.append("Vector dataset has no coordinate reference system (CRS).")

            geometries = gdf.geometry.dropna()
            geometry_types = sorted(set(geometries.geom_type.tolist()))
            if geometries.empty:
                errors.append("Vector dataset contains no valid geometries.")

            expected = _expected_geometry_types(dataset_type)
            if expected and geometry_types and not set(geometry_types).issubset(expected):
                errors.append(
                    f"Geometry types {geometry_types} are not valid for dataset type "
                    f"'{dataset_type.value}'. Expected one of {sorted(expected)}."
                )

            bounds_values = tuple(float(v) for v in gdf.total_bounds)
            return DatasetValidationResult(
                valid=not errors,
                dataset_type=dataset_type,
                filename=filename,
                format=fmt,
                crs=crs,
                geometry_types=geometry_types,
                bounds=bounds_values,
                feature_count=int(len(gdf)),
                columns=[str(c) for c in gdf.columns if c != gdf.geometry.name],
                warnings=warnings,
                errors=errors,
            )
    except Exception as exc:
        errors.append(f"Vector dataset could not be opened: {exc}")

    return DatasetValidationResult(
        valid=False,
        dataset_type=dataset_type,
        filename=filename,
        format=fmt,
        warnings=warnings,
        errors=errors,
    )


def _validate_tabular(data: bytes, filename: str, dataset_type: DatasetType, fmt: str) -> DatasetValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    columns: list[str] = []
    shape: tuple[int, ...] | None = None

    try:
        frame = pd.read_csv(io.BytesIO(data))
        columns = [str(c) for c in frame.columns]
        shape = tuple(frame.shape)
        if frame.empty:
            errors.append("CSV contains no rows.")
        if not frame.select_dtypes(include=[np.number]).columns.tolist():
            warnings.append("No numeric columns were detected; hydrological/rainfall processing may need additional parsing.")
        if dataset_type not in {DatasetType.HYDROLOGY, DatasetType.RAINFALL}:
            errors.append(f"CSV input is not supported for dataset type '{dataset_type.value}'.")
    except Exception as exc:
        errors.append(f"CSV could not be parsed: {exc}")

    return DatasetValidationResult(
        valid=not errors,
        dataset_type=dataset_type,
        filename=filename,
        format=fmt,
        shape=shape,
        columns=columns,
        warnings=warnings,
        errors=errors,
    )


def validate_dataset(
    data: bytes, filename: str, dataset_type: DatasetType, *, max_upload_bytes: int = MAX_UPLOAD_BYTES
) -> DatasetValidationResult:
    if not filename:
        raise ValueError("Filename is required.")
    if len(data) > max_upload_bytes:
        raise ValueError(f"File exceeds the {max_upload_bytes // (1024 * 1024)} MB upload limit.")

    classification = classify_filename(filename)
    if classification.kind == "raster":
        return _validate_raster(data, filename, dataset_type, classification.format)
    if classification.kind == "vector":
        return _validate_vector(data, filename, dataset_type, classification.format)
    return _validate_tabular(data, filename, dataset_type, classification.format)
