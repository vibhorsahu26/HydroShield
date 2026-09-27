from __future__ import annotations

from pathlib import Path

from app.geospatial.preprocessing import preprocess_geospatial
from app.schemas.geospatial import GeospatialPreprocessConfig, GeospatialPreprocessResponse


class GeospatialService:
    def preprocess(
        self,
        dem_data: bytes,
        dem_filename: str,
        river_data: bytes,
        river_filename: str,
        config: GeospatialPreprocessConfig,
        output_dir: Path,
    ) -> GeospatialPreprocessResponse:
        return preprocess_geospatial(
            dem_data,
            dem_filename,
            river_data,
            river_filename,
            config,
            output_dir,
        )
