from __future__ import annotations

import math
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

import rasterio
from rasterio.merge import merge
from rasterio.windows import from_bounds


class CopernicusDemProvider:
    """Fetch/cache public Copernicus DEM tiles from AWS Open Data.

    The public GLO-30 bucket is attempted first. If any requested tile is not
    available publicly, the provider falls back to a homogeneous GLO-90 mosaic.
    """

    GLO30_BUCKET = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"
    GLO90_BUCKET = "https://copernicus-dem-90m.s3.eu-central-1.amazonaws.com"

    @staticmethod
    def _tile_ids(bbox: tuple[float, float, float, float]) -> list[tuple[int, int]]:
        min_lon, min_lat, max_lon, max_lat = bbox
        lon_start, lon_end = math.floor(min_lon), math.floor(max_lon)
        lat_start, lat_end = math.floor(min_lat), math.floor(max_lat)
        return [(lat, lon) for lat in range(lat_start, lat_end + 1) for lon in range(lon_start, lon_end + 1)]

    @staticmethod
    def _tile_name(lat: int, lon: int, resolution: str) -> str:
        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        prefix = "10" if resolution == "30m" else "30"
        return f"Copernicus_DSM_COG_{prefix}_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"

    def _tile_url(self, lat: int, lon: int, resolution: str) -> str:
        name = self._tile_name(lat, lon, resolution)
        bucket = self.GLO30_BUCKET if resolution == "30m" else self.GLO90_BUCKET
        return f"{bucket}/{name}/{name}.tif"

    @staticmethod
    def _head(url: str, timeout_s: int = 20) -> bool:
        try:
            request = Request(url, method="HEAD", headers={"User-Agent": "HydroShield/0.1"})
            with urlopen(request, timeout=timeout_s) as response:
                return 200 <= response.status < 400
        except Exception:
            return False

    @staticmethod
    def _download(url: str, dest: Path, timeout_s: int = 300) -> None:
        temp = dest.with_suffix(dest.suffix + ".part")
        request = Request(url, headers={"User-Agent": "HydroShield/0.1"})
        try:
            with urlopen(request, timeout=timeout_s) as response, temp.open("wb") as stream:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
            temp.replace(dest)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def fetch(self, bbox: tuple[float, float, float, float], cache_dir: Path, output_path: Path, resolution: str = "auto") -> dict:
        tiles = self._tile_ids(bbox)
        if len(tiles) > 4:
            raise ValueError("Study region spans too many DEM tiles; reduce radius to 25 km or less around the selected dam.")
        selected = resolution
        if resolution == "auto":
            selected = "30m" if all(self._head(self._tile_url(lat, lon, "30m")) for lat, lon in tiles) else "90m"
        if selected not in {"30m", "90m"}:
            raise ValueError("DEM resolution must be auto, 30m, or 90m.")
        cache_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for lat, lon in tiles:
            name = self._tile_name(lat, lon, selected)
            cached = cache_dir / f"{name}.tif"
            if not cached.exists():
                self._download(self._tile_url(lat, lon, selected), cached)
            paths.append(cached)

        sources = [rasterio.open(path) for path in paths]
        try:
            mosaic, transform = merge(sources, bounds=bbox)
            profile = sources[0].profile.copy()
            profile.update(
                driver="GTiff",
                height=mosaic.shape[1],
                width=mosaic.shape[2],
                transform=transform,
                count=1,
                compress="deflate",
                tiled=True,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if mosaic.shape[1] >= 16 and mosaic.shape[2] >= 16:
                profile["tiled"] = True
                profile.pop("blockxsize", None)
                profile.pop("blockysize", None)
            else:
                profile["tiled"] = False
                profile.pop("blockxsize", None)
                profile.pop("blockysize", None)
            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(mosaic[0], 1)
        finally:
            for src in sources:
                src.close()
        return {"resolution": selected, "tile_count": len(paths), "source": "Copernicus DEM GLO-30 Public" if selected == "30m" else "Copernicus DEM GLO-90"}
