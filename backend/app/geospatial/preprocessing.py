from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid

from app.geospatial.crs import choose_processing_crs
from app.geospatial.domain import generate_domain, write_domain_and_mask
from app.geospatial.raster import clip_reproject_resample_dem, raster_extent_polygon, read_dem_profile
from app.geospatial.vector import prepare_river, read_vector, vector_metadata, write_geopackage
from app.schemas.datasets import DatasetType
from app.schemas.geospatial import (
    BoundingBox,
    DomainMetadata,
    GeospatialPreprocessConfig,
    GeospatialPreprocessResponse,
    RasterMetadata,
    VectorMetadata,
)
from app.services.dataset_validator import validate_dataset


@dataclass(frozen=True)
class PreprocessingArtifacts:
    dem_path: Path
    river_path: Path
    domain_path: Path
    domain_mask_path: Path


def _validate_inputs(dem_data: bytes, dem_filename: str, river_data: bytes, river_filename: str) -> None:
    dem_result = validate_dataset(dem_data, dem_filename, DatasetType.DEM)
    if not dem_result.valid:
        raise ValueError(f"DEM validation failed: {'; '.join(dem_result.errors)}")

    river_result = validate_dataset(river_data, river_filename, DatasetType.RIVER)
    if not river_result.valid:
        raise ValueError(f"River validation failed: {'; '.join(river_result.errors)}")


def preprocess_geospatial(
    dem_data: bytes,
    dem_filename: str,
    river_data: bytes,
    river_filename: str,
    config: GeospatialPreprocessConfig,
    output_dir: Path,
) -> GeospatialPreprocessResponse:
    """Normalize CRS, prepare river geometry, build corridor domain, and clip/resample DEM."""
    _validate_inputs(dem_data, dem_filename, river_data, river_filename)

    dem_profile, dem_bounds = read_dem_profile(dem_data)
    dem_crs = dem_profile["crs"]
    raw_river = read_vector(river_data, river_filename)
    processing = choose_processing_crs(config.target_crs, dem_crs, dem_bounds, raw_river)

    raw_river_target = raw_river.to_crs(processing.crs)
    dem_extent_target = raster_extent_polygon_from_source(dem_data, processing.crs)
    prepared_for_domain = prepare_river(river_data, river_filename, processing.crs)
    preliminary_domain = generate_domain(
        prepared_for_domain,
        tuple(float(v) for v in dem_extent_target.bounds),
        config.river_buffer_m,
        config.min_domain_area_m2,
    )

    run_dir = output_dir / str(uuid.uuid4())
    artifacts = PreprocessingArtifacts(
        dem_path=run_dir / "processed_dem.tif",
        river_path=run_dir / "prepared_river.gpkg",
        domain_path=run_dir / "computational_domain.gpkg",
        domain_mask_path=run_dir / "domain_mask.tif",
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    dem_meta = clip_reproject_resample_dem(
        dem_data,
        target_crs=processing.crs,
        clip_geometry=preliminary_domain,
        resolution_m=config.resolution_m,
        output_path=artifacts.dem_path,
    )

    processed_dem_extent = raster_extent_polygon(artifacts.dem_path)[0]
    river = prepare_river(river_data, river_filename, processing.crs, processed_dem_extent)
    write_geopackage(river, artifacts.river_path, layer="river")

    domain = generate_domain(
        river,
        tuple(float(v) for v in processed_dem_extent.bounds),
        config.river_buffer_m,
        config.min_domain_area_m2,
    )
    domain_meta = write_domain_and_mask(
        domain,
        artifacts.dem_path,
        artifacts.domain_path,
        artifacts.domain_mask_path,
    )
    river_meta = vector_metadata(river, artifacts.river_path)

    warnings: list[str] = []
    if processing.auto_selected:
        warnings.append(
            f"Processing CRS was automatically selected as {processing.crs.to_string()} from the dataset location."
        )
    if abs(raw_river_target.length.sum() - river.length.sum()) > max(raw_river_target.length.sum() * 0.25, 1.0):
        warnings.append("A substantial portion of the prepared river geometry was outside the processed DEM footprint and was clipped.")
    if domain.area >= processed_dem_extent.area * 0.95:
        warnings.append(
            "Computational domain occupies most of the processed DEM footprint; consider a smaller river buffer if appropriate."
        )

    return GeospatialPreprocessResponse(
        processing_crs=processing.crs.to_string(),
        processing_crs_name=processing.crs.name,
        config=config,
        dem=RasterMetadata(**{**dem_meta, "bounds": BoundingBox.from_tuple(dem_meta["bounds"]) if False else {"min_x": dem_meta["bounds"][0], "min_y": dem_meta["bounds"][1], "max_x": dem_meta["bounds"][2], "max_y": dem_meta["bounds"][3]}}),
        river=VectorMetadata(**{**river_meta, "bounds": {"min_x": river_meta["bounds"][0], "min_y": river_meta["bounds"][1], "max_x": river_meta["bounds"][2], "max_y": river_meta["bounds"][3]}}),
        domain=DomainMetadata(**{**domain_meta, "bounds": {"min_x": domain_meta["bounds"][0], "min_y": domain_meta["bounds"][1], "max_x": domain_meta["bounds"][2], "max_y": domain_meta["bounds"][3]}}),
        warnings=warnings,
    )


def raster_extent_polygon_from_source(data: bytes, target_crs):
    from rasterio.io import MemoryFile
    from rasterio.warp import transform_bounds
    from shapely.geometry import box

    with MemoryFile(data) as memfile:
        with memfile.open() as src:
            bounds = transform_bounds(src.crs, target_crs, *src.bounds, densify_pts=21)
            return box(*bounds)
