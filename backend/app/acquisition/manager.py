from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import shape

from app.acquisition.dem import CopernicusDemProvider
from app.acquisition.demo import demo_candidate, generate_demo_acquisition
from app.acquisition.nominatim import NominatimClient
from app.acquisition.overpass import OverpassClient
from app.acquisition.schemas import AutomaticAcquisitionRequest
from app.database.models import AcquisitionRun
from app.database.repositories.datasets import DatasetRepository
from app.database.repositories.projects import ProjectRepository
from app.schemas.datasets import DatasetType
from app.services.geospatial_service import GeospatialService
from app.services.dataset_validator import validate_dataset
from app.schemas.geospatial import GeospatialPreprocessConfig
from app.core.config import get_settings


@dataclass(frozen=True)
class AcquisitionProviderConfig:
    nominatim_url: str
    overpass_url: str
    user_agent: str


class AcquisitionManager:
    def __init__(self, settings):
        self.settings = settings
        self.projects = ProjectRepository()
        self.datasets = DatasetRepository()
        self.dem = CopernicusDemProvider()
        self.geocoder = NominatimClient(settings.nominatim_url, settings.acquisition_user_agent, timeout_s=settings.acquisition_timeout_s, cache_dir=settings.storage_root / "cache" / "nominatim", cache_ttl_s=settings.acquisition_cache_ttl_s)
        self.overpass = OverpassClient(settings.overpass_url, settings.acquisition_user_agent, timeout_s=settings.acquisition_timeout_s, cache_dir=settings.storage_root / "cache" / "overpass", cache_ttl_s=settings.acquisition_cache_ttl_s)
        self.geospatial = GeospatialService()

    @staticmethod
    def _is_dam_candidate(candidate) -> bool:
        text = " ".join(str(value or "") for value in (candidate.name, candidate.display_name, candidate.category, candidate.object_type)).lower()
        return any(token in text for token in ("dam", "reservoir", "barrage", "waterworks"))

    def search_dams(self, query: str, country_code: str | None = None):
        settings = getattr(self, "settings", None) or get_settings()
        provider_errors = []
        try:
            geocoded = self.geocoder.search(query, country_code) if self.geocoder is not None else []
            candidates = [item for item in geocoded if self._is_dam_candidate(item)]
            if candidates:
                return candidates
        except Exception as exc:
            provider_errors.append(str(exc))
        try:
            live_candidates = self.overpass.search_dams(query, country_code=country_code)
            if live_candidates:
                return live_candidates
        except Exception as exc:
            provider_errors.append(str(exc))
        if getattr(settings, "demo_mode", False):
            return [demo_candidate(query)]
        if provider_errors:
            raise ValueError(provider_errors[-1])
        return []

    @staticmethod
    def _bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * max(abs(__import__('math').cos(__import__('math').radians(lat))), 0.1))
        return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)

    @staticmethod
    def _write_geojson(collection: dict, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(collection), encoding="utf-8")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _bounds_for_geojson(path: Path) -> tuple[float, float, float, float] | None:
        gdf = gpd.read_file(path)
        if gdf.empty:
            return None
        return tuple(float(v) for v in gdf.total_bounds)

    def _run_demo(self, db, project_id: str, request: AutomaticAcquisitionRequest, run: AcquisitionRun, run_dir: Path, bbox):
        """Prefer live public study data and fall back only for unavailable pieces."""
        demo = generate_demo_acquisition(run_dir, dam_name=request.dam_name, river_name=request.river_name)
        warnings: list[str] = []
        selected_paths = dict(demo["paths"])
        source_meta: dict[str, dict[str, Any]] = {
            key: {
                "provider": "HydroShield study dataset",
                "source": "Local prepared dataset",
                "source_url": None,
                "source_id": "local-fallback",
                "license": "HydroShield study dataset",
                "metadata": {"logical_type": key, "fallback": True},
            }
            for key in selected_paths
        }

        # Live terrain first.
        dem_info = None
        try:
            dem_path = run_dir / "dem_live.tif"
            dem_info = self.dem.fetch(
                bbox,
                self.settings.storage_root / "cache" / "copernicus_dem",
                dem_path,
                request.dem_resolution,
            )
            validation = validate_dataset(
                dem_path.read_bytes(),
                dem_path.name,
                DatasetType.DEM,
                max_upload_bytes=self.settings.max_acquisition_download_bytes,
            )
            if not validation.valid:
                raise ValueError("; ".join(validation.errors))
            selected_paths["dem"] = dem_path
            source_meta["dem"] = {
                "provider": "Copernicus DEM",
                "source": dem_info["source"],
                "source_url": "https://registry.opendata.aws/copernicus-dem/",
                "source_id": dem_info["resolution"],
                "license": "Copernicus DEM terms",
                "metadata": dict(dem_info),
            }
            if dem_info["resolution"] == "90m":
                warnings.append("30 m elevation coverage was unavailable for part of this study area; 90 m coverage was used.")
        except Exception as exc:
            warnings.append(f"Live elevation retrieval was unavailable; prepared terrain was used. ({exc})")

        # Live OSM first for the river, dam and exposure layers.
        try:
            osm_payload = self.overpass.fetch(request)
            layers = self.overpass.split_layers(
                osm_payload,
                dam_point=(request.longitude, request.latitude),
                river_name=request.river_name,
            )
            logical_types = ("river", "dam", "settlement", "road", "building", "bridge", "critical_infrastructure")
            for logical_type in logical_types:
                if not request.include_exposure and logical_type in {"settlement", "road", "building", "bridge", "critical_infrastructure"}:
                    continue
                features = layers.get(logical_type, {}).get("features", [])
                if not features:
                    continue
                path = run_dir / f"{logical_type}_live.geojson"
                self._write_geojson(layers[logical_type], path)
                selected_paths[logical_type] = path
                source_meta[logical_type] = {
                    "provider": "OpenStreetMap Overpass API",
                    "source": "OpenStreetMap",
                    "source_url": self.settings.overpass_url,
                    "source_id": None,
                    "license": "OpenStreetMap ODbL",
                    "metadata": {"logical_type": logical_type, "osm_attribution": "© OpenStreetMap contributors"},
                }
        except Exception as exc:
            warnings.append(f"Live map retrieval was unavailable; prepared map layers were used. ({exc})")

        river_name = request.river_name or demo.get("river_name") or "Downstream river network"
        try:
            river_gdf = gpd.read_file(selected_paths["river"])
            names = []
            if "name" in river_gdf.columns:
                names = [str(v).strip() for v in river_gdf["name"].tolist() if str(v).strip() and str(v).strip().lower() != "nan"]
            if names:
                river_name = names[0]
        except Exception:
            pass

        preprocessing = None
        try:
            if request.auto_preprocess:
                if dem_info:
                    resolution_text = str(dem_info.get("resolution", "90m")).replace("m", "")
                    preprocess_resolution = float(resolution_text) if resolution_text else 90.0
                else:
                    preprocess_resolution = 100.0
                preprocessing_response = self.geospatial.preprocess(
                    dem_data=selected_paths["dem"].read_bytes(),
                    dem_filename=selected_paths["dem"].name,
                    river_data=selected_paths["river"].read_bytes(),
                    river_filename=selected_paths["river"].name,
                    config=GeospatialPreprocessConfig(
                        resolution_m=preprocess_resolution,
                        river_buffer_m=1000.0,
                        min_domain_area_m2=1.0,
                    ),
                    output_dir=self.settings.processing_work_dir / project_id / "automatic" / run.id,
                )
                preprocessing = preprocessing_response.model_dump(mode="json")
                preprocessing["river_name"] = river_name
        except Exception as exc:
            warnings.append(f"The selected terrain and river data could not be reconciled; prepared study data was used. ({exc})")
            selected_paths = dict(demo["paths"])
            source_meta = {
                key: {
                    "provider": "HydroShield study dataset",
                    "source": "Local prepared dataset",
                    "source_url": None,
                    "source_id": "local-fallback",
                    "license": "HydroShield study dataset",
                    "metadata": {"logical_type": key, "fallback": True},
                }
                for key in selected_paths
            }
            river_name = request.river_name or demo.get("river_name") or "Downstream river network"
            if request.auto_preprocess:
                preprocessing_response = self.geospatial.preprocess(
                    dem_data=selected_paths["dem"].read_bytes(),
                    dem_filename="dem.tif",
                    river_data=selected_paths["river"].read_bytes(),
                    river_filename="river.geojson",
                    config=GeospatialPreprocessConfig(
                        resolution_m=100.0,
                        river_buffer_m=1000.0,
                        min_domain_area_m2=1.0,
                    ),
                    output_dir=self.settings.processing_work_dir / project_id / "automatic" / run.id,
                )
                preprocessing = preprocessing_response.model_dump(mode="json")
                preprocessing["river_name"] = river_name

        acquired = []
        layer_specs = [
            ("dem", DatasetType.DEM.value, "dem", "GeoTIFF"),
            ("river", DatasetType.RIVER.value, "river", "GeoJSON"),
            ("dam", DatasetType.DAM.value, "dam", "GeoJSON"),
        ]
        if request.include_exposure:
            layer_specs.extend([
                ("settlement", DatasetType.SETTLEMENT.value, "settlement", "GeoJSON"),
                ("road", DatasetType.INFRASTRUCTURE.value, "road", "GeoJSON"),
                ("building", DatasetType.INFRASTRUCTURE.value, "building", "GeoJSON"),
                ("bridge", DatasetType.INFRASTRUCTURE.value, "bridge", "GeoJSON"),
                ("critical_infrastructure", DatasetType.INFRASTRUCTURE.value, "critical_infrastructure", "GeoJSON"),
            ])

        for key, dataset_type, logical_type, fmt in layer_specs:
            path = selected_paths[key]
            validation = validate_dataset(
                path.read_bytes(),
                path.name,
                DatasetType(dataset_type),
                max_upload_bytes=self.settings.max_acquisition_download_bytes,
            )
            if not validation.valid:
                raise ValueError(f"{logical_type} dataset failed validation: {'; '.join(validation.errors)}")
            if fmt == "GeoTIFF":
                bounds = list(validation.bounds or demo["bbox_wgs84"])
                geometry_types = []
                feature_count = None
                columns = []
                crs = validation.crs or "EPSG:4326"
            else:
                gdf = gpd.read_file(path)
                bounds = list(gdf.total_bounds) if not gdf.empty else list(demo["bbox_wgs84"])
                geometry_types = sorted(set(gdf.geometry.dropna().geom_type.tolist())) if not gdf.empty else []
                feature_count = int(len(gdf))
                columns = [str(c) for c in gdf.columns if c != gdf.geometry.name]
                crs = gdf.crs.to_string() if gdf.crs else "EPSG:4326"
            meta = source_meta[key]
            record = self.datasets.create(
                db,
                project_id=project_id,
                dataset_type=dataset_type,
                filename=path.name,
                storage_uri=str(path.resolve()),
                format=fmt,
                validation_status="validated",
                crs=crs,
                geometry_types=geometry_types,
                shape=list(validation.shape) if validation.shape else None,
                bounds=bounds,
                feature_count=feature_count,
                columns=columns,
                warnings=[],
                errors=[],
                acquisition_run_id=run.id,
                provider=meta["provider"],
                source_url=meta["source_url"],
                source_id=meta["source_id"],
                checksum_sha256=self._sha256(path),
                license=meta["license"],
                source_metadata=meta["metadata"],
            )
            acquired.append({
                "record": record,
                "logical_type": logical_type,
                "provider": meta["provider"],
                "source": meta["source"],
                "warnings": [],
            })

        run.status = "completed"
        run.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        run.provider_summary = {
            "datasets": [item["logical_type"] for item in acquired],
            "bbox_wgs84": list(bbox),
            "preprocessing": preprocessing,
            "mode": "live_first",
            "river_name": river_name,
        }
        run.warnings = warnings
        db.commit()
        return run, acquired, preprocessing, warnings, bbox

    def run(self, db, project_id: str, request: AutomaticAcquisitionRequest):
        self.projects.get(db, project_id)
        bbox = self._bbox(request.latitude, request.longitude, request.radius_km)
        run = AcquisitionRun(project_id=project_id, status="running", request=request.model_dump(mode="json"))
        db.add(run)
        db.commit()
        db.refresh(run)
        run_dir = self.settings.storage_root / project_id / "acquisition" / run.id
        warnings: list[str] = []
        acquired = []
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            if getattr(self.settings, "demo_mode", False):
                return self._run_demo(db, project_id, request, run, run_dir, bbox)
            dem_path = run_dir / "dem.tif"
            dem_info = self.dem.fetch(
                bbox,
                self.settings.storage_root / "cache" / "copernicus_dem",
                dem_path,
                request.dem_resolution,
            )
            dem_validation = validate_dataset(dem_path.read_bytes(), dem_path.name, DatasetType.DEM, max_upload_bytes=self.settings.max_acquisition_download_bytes)
            if not dem_validation.valid:
                raise ValueError(f"Automatically acquired DEM failed validation: {'; '.join(dem_validation.errors)}")
            dem_record = self.datasets.create(
                db,
                project_id=project_id,
                dataset_type=DatasetType.DEM.value,
                filename=dem_path.name,
                storage_uri=str(dem_path.resolve()),
                format="GeoTIFF",
                validation_status="validated",
                crs="EPSG:4326",
                geometry_types=[],
                shape=None,
                bounds=list(bbox),
                feature_count=None,
                columns=[],
                warnings=[f"Automatic source: {dem_info['source']}", f"Source resolution: {dem_info['resolution']}"],
                errors=[],
                acquisition_run_id=run.id,
                provider="Copernicus DEM",
                source_url="https://registry.opendata.aws/copernicus-dem/",
                source_id=dem_info["resolution"],
                checksum_sha256=self._sha256(dem_path),
                license="Copernicus DEM terms",
                source_metadata=dem_info,
            )
            acquired.append({"record": dem_record, "logical_type": "dem", "provider": "Copernicus DEM", "source": dem_info["source"], "warnings": dem_record.warnings})
            if dem_info["resolution"] == "90m":
                warnings.append("Copernicus GLO-30 was unavailable for at least one requested tile; a homogeneous GLO-90 DEM was used instead.")

            osm_payload = self.overpass.fetch(request)
            layers = self.overpass.split_layers(osm_payload, dam_point=(request.longitude, request.latitude), river_name=request.river_name)
            layer_specs = [
                ("river", DatasetType.RIVER.value, "river"),
                ("dam", DatasetType.DAM.value, "dam"),
            ]
            if request.include_exposure:
                layer_specs.extend([
                    ("settlement", DatasetType.SETTLEMENT.value, "settlement"),
                    ("road", DatasetType.INFRASTRUCTURE.value, "road"),
                    ("building", DatasetType.INFRASTRUCTURE.value, "building"),
                    ("bridge", DatasetType.INFRASTRUCTURE.value, "bridge"),
                    ("critical_infrastructure", DatasetType.INFRASTRUCTURE.value, "critical_infrastructure"),
                ])
            for layer_key, dataset_type, logical_type in layer_specs:
                path = run_dir / f"{layer_key}.geojson"
                self._write_geojson(layers[layer_key], path)
                try:
                    dataset_enum = DatasetType(dataset_type)
                    validation = validate_dataset(path.read_bytes(), path.name, dataset_enum, max_upload_bytes=self.settings.max_upload_bytes)
                    if not validation.valid:
                        raise ValueError("; ".join(validation.errors))
                    gdf = gpd.read_file(path)
                    crs = gdf.crs.to_string() if gdf.crs else "EPSG:4326"
                    geometry_types = sorted(set(gdf.geometry.dropna().geom_type.tolist())) if not gdf.empty else []
                    feature_count = int(len(gdf))
                    layer_warnings = []
                    if logical_type == "dam" and all(g == "Point" for g in geometry_types) and geometry_types:
                        layer_warnings.append("Dam geometry is point-based; no mapped dam-wall/reservoir polygon was found in the selected study area.")
                    if logical_type == "settlement" and "Point" in geometry_types:
                        layer_warnings.append("Settlement layer contains OSM place points; use boundary polygons when available for area-based exposure analysis.")
                    record = self.datasets.create(
                        db,
                        project_id=project_id,
                        dataset_type=dataset_type,
                        filename=path.name,
                        storage_uri=str(path.resolve()),
                        format="GeoJSON",
                        validation_status="validated",
                        crs=crs,
                        geometry_types=geometry_types,
                        shape=None,
                        bounds=list(gdf.total_bounds) if not gdf.empty else list(bbox),
                        feature_count=feature_count,
                        columns=[str(c) for c in gdf.columns if c != gdf.geometry.name],
                        warnings=layer_warnings,
                        errors=[],
                        acquisition_run_id=run.id,
                        provider="OpenStreetMap Overpass API",
                        source_url=self.settings.overpass_url,
                        source_id=None,
                        checksum_sha256=self._sha256(path),
                        license="OpenStreetMap ODbL",
                        source_metadata={"logical_type": logical_type, "osm_attribution": "© OpenStreetMap contributors"},
                    )
                    acquired.append({"record": record, "logical_type": logical_type, "provider": "OpenStreetMap Overpass API", "source": "OpenStreetMap", "warnings": layer_warnings})
                except Exception as exc:
                    warnings.append(f"Could not validate automatically acquired {logical_type} layer: {exc}")

            if not layers["river"]["features"]:
                raise ValueError("No river geometry was found in the selected study area. Increase the radius or choose the downstream river name.")

            preprocessing = None
            if request.auto_preprocess:
                preprocess_resolution = 30.0 if dem_info["resolution"] == "30m" else 90.0
                preprocessing_response = self.geospatial.preprocess(
                    dem_data=dem_path.read_bytes(),
                    dem_filename=dem_path.name,
                    river_data=(run_dir / "river.geojson").read_bytes(),
                    river_filename="river.geojson",
                    config=GeospatialPreprocessConfig(resolution_m=preprocess_resolution, river_buffer_m=1000.0, min_domain_area_m2=1.0),
                    output_dir=self.settings.processing_work_dir / project_id / "automatic" / run.id,
                )
                preprocessing = preprocessing_response.model_dump(mode="json")

            run.status = "completed"
            run.finished_at = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
            run.provider_summary = {"datasets": [item["logical_type"] for item in acquired], "osm_attribution": "© OpenStreetMap contributors", "bbox_wgs84": list(bbox), "preprocessing": preprocessing}
            run.warnings = warnings
            db.commit()
            return run, acquired, preprocessing, warnings, bbox
        except Exception as exc:
            run.status = "failed"
            run.finished_at = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
            run.error_message = str(exc)
            db.commit()
            raise
