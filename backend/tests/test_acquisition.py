import json
from pathlib import Path

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.acquisition.dem import CopernicusDemProvider
from app.acquisition.overpass import OverpassClient
from app.acquisition.schemas import AutomaticAcquisitionRequest
from app.database.base import Base
from app.database.models import Project


def _dem_bytes():
    profile = {
        "driver": "GTiff", "height": 4, "width": 4, "count": 1, "dtype": "float32",
        "crs": "EPSG:4326", "transform": from_origin(85.0, 28.1, 0.01, 0.01), "nodata": -9999,
    }
    with MemoryFile() as mem:
        with mem.open(**profile) as ds:
            ds.write(np.arange(16, dtype="float32").reshape(4, 4), 1)
        return mem.read()


def test_overpass_query_is_single_bounded_query():
    client = OverpassClient()
    request = AutomaticAcquisitionRequest(
        dam_name="Kosi Dam", latitude=28.0, longitude=85.0, radius_km=10, river_name="Kosi", auto_preprocess=False
    )
    query = client.build_query(request)
    assert query.count("[out:json]") == 1
    assert '"waterway"~"^(river|canal|stream)$"' in query
    assert '"highway"' in query
    assert '"place"~"^(city|town|village|hamlet|suburb)$"' in query
    assert '["amenity"~"^(hospital|school|clinic|fire_station|police)$"]' in query


def test_overpass_splits_layers_and_builds_dam_fallback():
    payload = {
        "elements": [
            {"type": "way", "id": 1, "tags": {"waterway": "river", "name": "Kosi"}, "geometry": [{"lat": 28.0, "lon": 85.0}, {"lat": 28.1, "lon": 85.1}]},
            {"type": "way", "id": 2, "tags": {"highway": "primary", "bridge": "yes"}, "geometry": [{"lat": 28.0, "lon": 85.0}, {"lat": 28.1, "lon": 85.1}]},
            {"type": "node", "id": 3, "tags": {"place": "village", "name": "Village"}, "lat": 28.02, "lon": 85.03},
            {"type": "node", "id": 4, "tags": {"amenity": "school", "name": "School"}, "lat": 28.03, "lon": 85.04},
            {"type": "way", "id": 5, "tags": {"building": "yes", "name": "Building"}, "geometry": [{"lat": 28.04, "lon": 85.05}, {"lat": 28.04, "lon": 85.051}, {"lat": 28.041, "lon": 85.051}, {"lat": 28.04, "lon": 85.05}]},
        ]
    }
    layers = OverpassClient().split_layers(payload, dam_point=(85.0, 28.0), river_name="Kosi")
    assert len(layers["river"]["features"]) == 1
    assert len(layers["road"]["features"]) == 1
    assert len(layers["bridge"]["features"]) == 1
    assert len(layers["settlement"]["features"]) == 1
    assert len(layers["critical_infrastructure"]["features"]) == 1
    assert len(layers["building"]["features"]) == 1
    assert layers["dam"]["features"][0]["geometry"]["type"] == "Point"


def test_dem_provider_falls_back_to_90m_when_30m_tile_missing(monkeypatch, tmp_path):
    provider = CopernicusDemProvider()
    monkeypatch.setattr(provider, "_head", lambda url: "copernicus-dem-30m" not in url)

    fake_tile = tmp_path / "fake.tif"
    fake_tile.write_bytes(_dem_bytes())
    monkeypatch.setattr(provider, "_download", lambda url, dest: dest.write_bytes(fake_tile.read_bytes()))
    result = provider.fetch((85.0, 28.0, 85.5, 28.5), tmp_path / "cache", tmp_path / "out.tif", "auto")
    assert result["resolution"] == "90m"
    assert Path(tmp_path / "out.tif").exists()


def test_acquisition_migration_schema_contains_provenance_columns(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'acq.db'}")
    Base.metadata.create_all(engine)
    columns = {col["name"] for col in inspect(engine).get_columns("datasets")}
    assert {"acquisition_run_id", "provider", "source_url", "checksum_sha256", "metadata", "acquired_at"}.issubset(columns)
    engine.dispose()


def test_nominatim_search_cache_avoids_second_request(tmp_path, monkeypatch):
    from app.acquisition.nominatim import NominatimClient
    from urllib.request import Request
    payload = [{"display_name": "Test Dam", "name": "Test Dam", "lat": "28.0", "lon": "85.0", "osm_type": "way", "osm_id": 99, "class": "man_made", "type": "dam"}]
    calls = []
    class Response:
        status = 200
        def read(self):
            import json
            return json.dumps(payload).encode()
        def __enter__(self): return self
        def __exit__(self, *args): return False
    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url if isinstance(request, Request) else request)
        return Response()
    monkeypatch.setattr("app.acquisition.nominatim.urlopen", fake_urlopen)
    client = NominatimClient(base_url="https://example.test/search", min_interval_s=0, cache_dir=tmp_path / "cache", cache_ttl_s=3600)
    first = client.search("Test Dam")
    second = client.search("Test Dam")
    assert [x.name for x in first] == [x.name for x in second] == ["Test Dam"]
    assert len(calls) == 1


def test_overpass_cache_avoids_second_request(tmp_path, monkeypatch):
    client = OverpassClient(endpoint="https://example.test/interpreter", cache_dir=tmp_path / "cache", cache_ttl_s=3600)
    request = AutomaticAcquisitionRequest(dam_name="Test Dam", latitude=28.0, longitude=85.0, radius_km=2, auto_preprocess=False)
    calls=[]
    payload={"elements":[{"type":"way","id":1,"tags":{"waterway":"river","name":"Test River"},"geometry":[{"lat":28.0,"lon":85.0},{"lat":28.01,"lon":85.01}]}]}
    class Response:
        def read(self): return json.dumps(payload).encode()
        def __enter__(self): return self
        def __exit__(self,*args): return False
    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return Response()
    monkeypatch.setattr("app.acquisition.overpass.urlopen", fake_urlopen)
    first=client.fetch(request); second=client.fetch(request)
    assert first==second==payload
    assert len(calls)==1


def test_overpass_search_by_river_returns_only_dams_and_sets_river_name(monkeypatch):
    client = OverpassClient(cache_ttl_s=0)
    river_payload = {
        "elements": [
            {"type": "way", "id": 100, "tags": {"waterway": "river", "name": "Kaveri"}, "geometry": [{"lat": 12.0, "lon": 75.0}, {"lat": 12.5, "lon": 76.0}]},
        ]
    }
    dam_payload = {
        "elements": [
            {"type": "node", "id": 201, "lat": 12.20, "lon": 75.40, "tags": {"man_made": "dam", "name": "Kaveri Dam One"}},
            {"type": "node", "id": 202, "lat": 12.40, "lon": 75.80, "tags": {"waterway": "dam", "name": "Kaveri Dam Two"}},
            {"type": "way", "id": 999, "tags": {"waterway": "river", "name": "Kaveri"}, "geometry": [{"lat": 12.0, "lon": 75.0}, {"lat": 12.1, "lon": 75.1}]},
        ]
    }
    queries = []
    def fake_query(query, prefix):
        queries.append(prefix)
        if prefix == "dam-name":
            return {"elements": []}
        return river_payload if prefix == "river-name" else dam_payload
    monkeypatch.setattr(client, "_post_query", fake_query)
    results = client.search_dams("Kaveri")
    assert len(results) == 2
    assert all("dam" in (item.object_type or "").lower() for item in results)
    assert [item.name for item in results] == ["Kaveri Dam One", "Kaveri Dam Two"]
    assert all(item.river_name == "Kaveri" for item in results)
    assert queries == ["dam-name", "river-name", "river-dams"]


def test_acquisition_manager_filters_non_dam_geocoder_results(monkeypatch):
    from app.acquisition.manager import AcquisitionManager
    from app.acquisition.schemas import DamCandidate
    manager = object.__new__(AcquisitionManager)
    manager.settings = type("S", (), {"demo_mode": False})()
    manager.geocoder = type("G", (), {"search": lambda self, *args, **kwargs: [DamCandidate(display_name="Kaveri, India", name="Kaveri", latitude=12.0, longitude=75.0, category="waterway", object_type="river")]})()
    manager.overpass = type("O", (), {"search_dams": lambda self, *args, **kwargs: [DamCandidate(display_name="Kaveri Dam", name="Kaveri Dam", latitude=12.1, longitude=75.1, category="man_made", object_type="dam", river_name="Kaveri")]})()
    assert [item.name for item in manager.search_dams("Kaveri")] == ["Kaveri Dam"]
