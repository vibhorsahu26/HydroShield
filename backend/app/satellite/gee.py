from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
import zipfile
from urllib.request import Request, urlopen

from shapely.geometry import shape, mapping
import geopandas as gpd


@dataclass(frozen=True)
class EarthEngineObservation:
    collection_id: str
    image_count: int
    selected_image_ids: list[str]
    processing_method: str
    warnings: list[str]
    downloaded_path: Path


class EarthEngineUnavailable(RuntimeError):
    pass


class EarthEngineSatelliteProvider:
    S1_COLLECTION = "OPERA/DSWX/L3_V1/S1"
    S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

    def __init__(self, *, ee_project: str | None = None):
        self.ee_project = ee_project
        self._ee = None

    def _load_ee(self):
        if self._ee is not None:
            return self._ee
        try:
            import ee  # type: ignore
        except ImportError as exc:
            raise EarthEngineUnavailable(
                "Earth Engine support is not installed. Install the optional 'earthengine-api' dependency."
            ) from exc
        try:
            if self.ee_project:
                ee.Initialize(project=self.ee_project)
            else:
                ee.Initialize()
        except Exception as exc:
            raise EarthEngineUnavailable(
                "Earth Engine could not be initialized. Authenticate with ee.Authenticate() and configure an EE project."
            ) from exc
        self._ee = ee
        return ee

    @staticmethod
    def roi_from_geojson(path: str | Path):
        gdf = gpd.read_file(path)
        if gdf.empty:
            raise ValueError("ROI GeoJSON is empty.")
        if gdf.crs is None:
            raise ValueError("ROI GeoJSON must have a CRS.")
        if gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")
        geom = gdf.geometry.union_all()
        if geom.is_empty:
            raise ValueError("ROI geometry is empty.")
        return geom

    def _build_water_image(self, *, sensor: str, collection, reducer: str, s2_cloud_pct: float, s2_threshold: float):
        ee = self._ee
        if sensor == "sentinel1":
            def clean(image):
                bwtr = image.select("BWTR_Binary_water")
                return bwtr.updateMask(bwtr.lt(250)).rename("observed_water")
            water = collection.map(clean)
            return water.max().gt(0).rename("observed_water") if reducer == "max" else water.mode().gt(0).rename("observed_water")

        filtered = collection.filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", s2_cloud_pct))
        def water_from_s2(image):
            scl = image.select("SCL")
            clear = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
            mndwi = image.normalizedDifference(["B3", "B11"])
            return mndwi.updateMask(clear).rename("mndwi")
        water = filtered.map(water_from_s2)
        composite = water.median() if reducer == "mode" else water.median()
        return composite.gt(s2_threshold).rename("observed_water")

    def observe(
        self,
        *,
        roi_geojson: str,
        start_date: date,
        end_date: date,
        sensor: str,
        output_path: Path,
        scale_m: float,
        temporal_reducer: str,
        s2_cloud_pct: float,
        s2_threshold: float,
        target_crs: str,
    ) -> EarthEngineObservation:
        ee = self._load_ee()
        roi = self.roi_from_geojson(roi_geojson)
        ee_roi = ee.Geometry(mapping(roi))
        collection_id = self.S1_COLLECTION if sensor == "sentinel1" else self.S2_COLLECTION
        collection = ee.ImageCollection(collection_id).filterDate(str(start_date), str(end_date)).filterBounds(ee_roi)
        if sensor == "sentinel2":
            collection = collection.filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", s2_cloud_pct))
        image_count = int(collection.size().getInfo())
        if image_count <= 0:
            raise ValueError(f"No {sensor} imagery found for the requested ROI and date window.")
        image_ids = collection.aggregate_array("system:index").getInfo() or []
        image = self._build_water_image(
            sensor=sensor,
            collection=collection,
            reducer=temporal_reducer,
            s2_cloud_pct=s2_cloud_pct,
            s2_threshold=s2_threshold,
        )
        url = image.getDownloadURL({
            "scale": scale_m,
            "crs": target_crs,
            "region": mapping(roi),
            "fileFormat": "GeoTIFF",
        })
        output_path.parent.mkdir(parents=True, exist_ok=True)
        req = Request(url, headers={"User-Agent": "HydroShield/0.1"})
        with urlopen(req, timeout=180) as response:
            data = response.read()
        if data[:2] == b"PK":
            temp = output_path.with_suffix(".zip")
            temp.write_bytes(data)
            with zipfile.ZipFile(temp) as zf:
                tif_members = [n for n in zf.namelist() if n.lower().endswith((".tif", ".tiff"))]
                if len(tif_members) != 1:
                    raise ValueError("Earth Engine download archive did not contain exactly one GeoTIFF.")
                with zf.open(tif_members[0]) as src, output_path.open("wb") as dst:
                    dst.write(src.read())
            temp.unlink(missing_ok=True)
        else:
            output_path.write_bytes(data)
        return EarthEngineObservation(
            collection_id=collection_id,
            image_count=image_count,
            selected_image_ids=[str(v) for v in image_ids],
            processing_method=(
                "DSWx-S1 BWTR_Binary_water valid-class mask + temporal max"
                if sensor == "sentinel1" and temporal_reducer == "max"
                else "DSWx-S1 BWTR_Binary_water valid-class mask + temporal mode"
                if sensor == "sentinel1"
                else "Sentinel-2 SR harmonized + SCL cloud/shadow exclusion + MNDWI threshold + median composite"
            ),
            warnings=[],
            downloaded_path=output_path.resolve(),
        )
