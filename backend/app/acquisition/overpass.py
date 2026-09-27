from __future__ import annotations

import json
import re
import threading
import time
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.acquisition.schemas import AutomaticAcquisitionRequest, DamCandidate


class OverpassClient:
    _rate_lock = threading.Lock()
    _last_global_request = 0.0
    def __init__(
        self,
        endpoint: str = "https://overpass-api.de/api/interpreter",
        user_agent: str = "HydroShield/0.1 (dam-break flood modelling)",
        timeout_s: int = 120,
        cache_dir: Path | None = None,
        cache_ttl_s: int = 21_600,
    ):
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir
        self.cache_ttl_s = cache_ttl_s
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _regex(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9 _-]+", " ", value).strip().replace(" ", ".*?")

    @staticmethod
    def _candidate_name(properties: dict) -> str:
        return str(properties.get("name") or properties.get("official_name") or "Unnamed dam").strip()

    def _post_query(self, query: str, cache_key_prefix: str = "search") -> dict:
        cache_file = None
        if self.cache_dir and self.cache_ttl_s > 0:
            key = sha256(f"{cache_key_prefix}:{query}".encode("utf-8")).hexdigest()
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                try:
                    if time.time() - cache_file.stat().st_mtime <= self.cache_ttl_s:
                        return json.loads(cache_file.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
        body = urlencode({"data": query}).encode("utf-8")
        http_request = Request(self.endpoint, data=body, headers={"User-Agent": self.user_agent, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "Accept": "application/json"}, method="POST")
        with OverpassClient._rate_lock:
            delay = 1.05 - (time.monotonic() - OverpassClient._last_global_request)
            if delay > 0:
                time.sleep(delay)
            try:
                with urlopen(http_request, timeout=self.timeout_s) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"OpenStreetMap Overpass provider is unavailable: {exc}") from exc
            OverpassClient._last_global_request = time.monotonic()
        if cache_file:
            try:
                cache_file.write_text(json.dumps(payload), encoding="utf-8")
            except OSError:
                pass
        return payload

    def _dam_candidates_from_payload(self, payload: dict) -> list[DamCandidate]:
        candidates = []
        for element in payload.get("elements", []):
            tags = dict(element.get("tags") or {})
            if tags.get("waterway") != "dam" and tags.get("man_made") != "dam":
                continue
            if element.get("type") == "node":
                lat, lon = element.get("lat"), element.get("lon")
            else:
                center = element.get("center") or {}
                geometry = element.get("geometry") or []
                if center.get("lat") is not None:
                    lat, lon = center.get("lat"), center.get("lon")
                elif geometry:
                    point = geometry[len(geometry) // 2]
                    lat, lon = point.get("lat"), point.get("lon")
                else:
                    continue
            if lat is None or lon is None:
                continue
            name = self._candidate_name(tags)
            location = tags.get("addr:city") or tags.get("addr:state") or tags.get("is_in")
            display = f"{name}, {location}" if location else name
            candidates.append(DamCandidate(display_name=display, name=name, latitude=float(lat), longitude=float(lon), osm_type=element.get("type"), osm_id=int(element["id"]) if element.get("id") else None, category=tags.get("man_made") or tags.get("waterway") or "dam", object_type=tags.get("man_made") or tags.get("waterway") or "dam"))
        return candidates

    def search_dams(self, query: str, country_code: str | None = None, limit: int = 8) -> list[DamCandidate]:
        clean = str(query or "").strip()
        if not clean:
            return []
        escaped = re.escape(clean)

        # Direct dam-name lookup first.
        direct_query = f'''[out:json][timeout:60];
(
  nwr["man_made"="dam"]["name"~"{escaped}",i];
  nwr["waterway"="dam"]["name"~"{escaped}",i];
);
out center tags;'''
        direct_candidates = self._dam_candidates_from_payload(self._post_query(direct_query, "dam-name"))
        if direct_candidates:
            return direct_candidates[:limit]

        # If the query names a river, resolve that river first and then search for
        # dams spatially along its mapped course instead of returning the river itself.
        river_query = f'''[out:json][timeout:90];
way["waterway"~"^(river|canal|stream)$"]["name"~"{escaped}",i];
out geom tags;'''
        river_payload = self._post_query(river_query, "river-name")
        river_features, river_names = [], []
        for element in river_payload.get("elements", []):
            tags = element.get("tags") or {}
            name = str(tags.get("name") or "").strip()
            if name and name not in river_names:
                river_names.append(name)
            feature = self._geojson_feature(element)
            if feature:
                river_features.append(feature)
        if not river_features:
            return []

        coords = []
        for feature in river_features:
            geom = feature.get("geometry") or {}
            if geom.get("type") == "LineString":
                coords.extend((float(x), float(y)) for x, y in geom.get("coordinates") or [])
        if not coords:
            return []
        west, east = min(x for x, _ in coords) - 0.12, max(x for x, _ in coords) + 0.12
        south, north = min(y for _, y in coords) - 0.12, max(y for _, y in coords) + 0.12

        dam_query = f'''[out:json][timeout:90];
(
  nwr["man_made"="dam"]({south},{west},{north},{east});
  nwr["waterway"="dam"]({south},{west},{north},{east});
);
out center tags;'''
        candidates = self._dam_candidates_from_payload(self._post_query(dam_query, "river-dams"))
        if not candidates:
            return []

        from shapely.geometry import LineString, Point
        from shapely.ops import unary_union
        lines = [LineString((feature.get("geometry") or {}).get("coordinates") or []) for feature in river_features]
        river_geom = unary_union([line for line in lines if not line.is_empty]) if lines else None
        if river_geom is not None and not river_geom.is_empty:
            filtered = [c for c in candidates if river_geom.distance(Point(c.longitude, c.latitude)) <= 0.15]
            candidates = filtered or candidates
        if len(river_names) == 1:
            for candidate in candidates:
                candidate.river_name = river_names[0]
        return sorted(candidates, key=lambda item: item.name.lower())[:limit]

    def build_query(self, request: AutomaticAcquisitionRequest) -> str:
        # Fetch the surrounding waterways in one bounded query. The optional river
        # name is matched locally so a typo does not leave the study with no river.
        radius_m = int(round(request.radius_km * 1000))
        lat = f"{request.latitude:.7f}"
        lon = f"{request.longitude:.7f}"
        return f"""[out:json][timeout:90];
(
  way(around:{radius_m},{lat},{lon})["waterway"~"^(river|canal|stream)$"];
  way(around:{radius_m},{lat},{lon})["waterway"="dam"];
  way(around:{radius_m},{lat},{lon})["man_made"="dam"];
  node(around:{radius_m},{lat},{lon})["man_made"="dam"];
  way(around:{radius_m},{lat},{lon})["highway"];
  way(around:{radius_m},{lat},{lon})["building"];
  way(around:{radius_m},{lat},{lon})["highway"]["bridge"];
  node(around:{radius_m},{lat},{lon})["place"~"^(city|town|village|hamlet|suburb)$"];
  way(around:{radius_m},{lat},{lon})["place"~"^(city|town|village|hamlet|suburb)$"];
  node(around:{radius_m},{lat},{lon})["amenity"~"^(hospital|school|clinic|fire_station|police)$"];
  way(around:{radius_m},{lat},{lon})["amenity"~"^(hospital|school|clinic|fire_station|police)$"];
  node(around:{radius_m},{lat},{lon})["power"];
  way(around:{radius_m},{lat},{lon})["power"];
  node(around:{radius_m},{lat},{lon})["railway"];
  way(around:{radius_m},{lat},{lon})["railway"];
);
out body geom;"""

    def fetch(self, request: AutomaticAcquisitionRequest) -> dict:
        query = self.build_query(request)
        cache_file = None
        if self.cache_dir and self.cache_ttl_s > 0:
            key = sha256(query.encode("utf-8")).hexdigest()
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                try:
                    if time.time() - cache_file.stat().st_mtime <= self.cache_ttl_s:
                        return json.loads(cache_file.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
        body = urlencode({"data": query}).encode("utf-8")
        http_request = Request(
            self.endpoint,
            data=body,
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "application/json",
            },
            method="POST",
        )
        with OverpassClient._rate_lock:
            delay = 1.05 - (time.monotonic() - OverpassClient._last_global_request)
            if delay > 0:
                time.sleep(delay)
            try:
                with urlopen(http_request, timeout=self.timeout_s) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"OpenStreetMap Overpass provider is unavailable: {exc}") from exc
            OverpassClient._last_global_request = time.monotonic()
        if cache_file:
            try:
                cache_file.write_text(json.dumps(payload), encoding="utf-8")
            except OSError:
                pass
        return payload

    @staticmethod
    def _geojson_feature(element: dict) -> dict | None:
        tags = dict(element.get("tags") or {})
        osm_type = element.get("type")
        osm_id = element.get("id")
        properties = {"osm_type": osm_type, "osm_id": osm_id, **tags}
        if osm_type == "node" and "lat" in element and "lon" in element:
            return {"type": "Feature", "properties": properties, "geometry": {"type": "Point", "coordinates": [element["lon"], element["lat"]]}}
        geometry = element.get("geometry") or []
        coords = [[point["lon"], point["lat"]] for point in geometry if "lon" in point and "lat" in point]
        if len(coords) < 2:
            return None
        closed = len(coords) >= 4 and coords[0] == coords[-1]
        if closed:
            return {"type": "Feature", "properties": properties, "geometry": {"type": "Polygon", "coordinates": [coords]}}
        return {"type": "Feature", "properties": properties, "geometry": {"type": "LineString", "coordinates": coords}}

    def split_layers(self, payload: dict, *, dam_point: tuple[float, float], river_name: str | None = None) -> dict[str, dict]:
        buckets = {
            "river": [], "dam": [], "road": [], "bridge": [], "building": [], "settlement": [], "critical_infrastructure": [],
        }
        for element in payload.get("elements", []):
            feature = self._geojson_feature(element)
            if not feature:
                continue
            tags = element.get("tags") or {}
            if tags.get("waterway") in {"river", "canal", "stream"}:
                buckets["river"].append(feature)
            if tags.get("waterway") == "dam" or tags.get("man_made") == "dam":
                buckets["dam"].append(feature)
            if tags.get("building"):
                buckets["building"].append(feature)
            if tags.get("highway"):
                buckets["road"].append(feature)
                if "bridge" in tags:
                    buckets["bridge"].append(feature)
            if tags.get("place") in {"city", "town", "village", "hamlet", "suburb"}:
                buckets["settlement"].append(feature)
            if tags.get("amenity") in {"hospital", "school", "clinic", "fire_station", "police"} or tags.get("power") or tags.get("railway"):
                buckets["critical_infrastructure"].append(feature)
        if river_name and buckets["river"]:
            wanted = self._regex(river_name).replace(".*?", " ").strip().lower()
            named = [
                feature for feature in buckets["river"]
                if wanted and wanted in str(feature.get("properties", {}).get("name", "")).lower()
            ]
            if named:
                buckets["river"] = named
        lon, lat = dam_point
        if not buckets["dam"]:
            buckets["dam"].append({
                "type": "Feature",
                "properties": {"source": "selected_geocoder_location", "name": "Selected dam location"},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            })
        return {
            key: {"type": "FeatureCollection", "features": features, "source": "OpenStreetMap Overpass API"}
            for key, features in buckets.items()
        }
