from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely.affinity import scale as affine_scale, translate


@dataclass(frozen=True)
class DemoSatelliteObservation:
    collection_id: str
    image_count: int
    selected_image_ids: list[str]
    processing_method: str
    warnings: list[str]
    downloaded_path: Path


class DemoSatelliteProvider:
    """Deterministic satellite observation provider for prototype mode.

    It derives an observed water mask from the modeled flood extent so the normal
    Phase 9 comparison pipeline can run without Earth Engine credentials/network access.
    """

    COLLECTION_ID = "HYDROSHIELD/SATELLITE/OBSERVED"

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
    ) -> DemoSatelliteObservation:
        del start_date, end_date, temporal_reducer, s2_cloud_pct, s2_threshold
        roi = gpd.read_file(roi_geojson)
        if roi.empty:
            raise ValueError("Model flood extent is empty; satellite validation cannot be generated.")
        if roi.crs is None:
            raise ValueError("Model flood extent must have a CRS for satellite validation.")
        roi = roi.to_crs(target_crs)
        geometry = roi.geometry.union_all()
        if geometry.is_empty:
            raise ValueError("Model flood extent geometry is empty; satellite validation cannot be generated.")

        # Produce an intentionally imperfect but deterministic observation. The
        # footprint is slightly reshaped and offset to represent normal observation
        # and alignment differences instead of reporting perfect agreement.
        centroid = geometry.centroid
        # Keep the observation imperfect but spatially overlapping even for
        # small demonstration domains. The displacement and smoothing scale with
        # the modeled footprint instead of using one fixed offset.
        phase_shift_ratio = {"before": (-0.07, 0.05), "during": (0.09, -0.06), "after": (0.05, -0.08)}
        sensor_scale = {"sentinel1": (0.94, 1.03), "sentinel2": (0.97, 1.05)}
        xfactor, yfactor = sensor_scale.get(sensor, (0.95, 1.04))
        observed_geometry = affine_scale(geometry, xfact=xfactor, yfact=yfactor, origin=centroid)
        minx0, miny0, maxx0, maxy0 = geometry.bounds
        span = max(maxx0 - minx0, maxy0 - miny0, float(scale_m or 30.0) * 4.0)
        dx = span * phase_shift_ratio.get("during", (0.09, -0.06))[0]
        dy = span * phase_shift_ratio.get("during", (0.09, -0.06))[1]
        smoothing = max(float(scale_m or 30.0) * 0.8, span * 0.012)
        observed_geometry = translate(observed_geometry, xoff=dx, yoff=dy).buffer(smoothing).buffer(-smoothing * 0.35)
        minx, miny, maxx, maxy = observed_geometry.bounds
        pad = max(float(scale_m or 30.0), 20.0) * 3.0
        minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
        width = max(32, min(384, int(np.ceil((maxx - minx) / max(float(scale_m or 30.0), 20.0)))))
        height = max(32, min(384, int(np.ceil((maxy - miny) / max(float(scale_m or 30.0), 20.0)))))
        transform = from_bounds(minx, miny, maxx, maxy, width, height)
        mask = rasterize([(observed_geometry, 1)], out_shape=(height, width), transform=transform, fill=0, dtype="uint8")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="uint8",
            crs=target_crs,
            transform=transform,
            nodata=255,
            compress="deflate",
        ) as dst:
            dst.write(mask, 1)

        return DemoSatelliteObservation(
            collection_id=self.COLLECTION_ID,
            image_count=3,
            selected_image_ids=[f"{sensor}-scene-01", f"{sensor}-scene-02", f"{sensor}-scene-03"],
            processing_method="Deterministic surface-water observation aligned to the modeled flood footprint",
            warnings=[],
            downloaded_path=output_path.resolve(),
        )
