from __future__ import annotations

import pytest

from app.satellite.gee import EarthEngineSatelliteProvider, EarthEngineUnavailable


def test_provider_uses_specified_collections():
    assert EarthEngineSatelliteProvider.S1_COLLECTION == "OPERA/DSWX/L3_V1/S1"
    assert EarthEngineSatelliteProvider.S2_COLLECTION == "COPERNICUS/S2_SR_HARMONIZED"


def test_missing_earth_engine_dependency_is_explicit(monkeypatch):
    import builtins
    original = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ee":
            raise ImportError("missing")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(EarthEngineUnavailable, match="earthengine-api"):
        EarthEngineSatelliteProvider()._load_ee()


def test_roi_is_normalized_to_wgs84(tmp_path):
    path = tmp_path / "roi.geojson"
    path.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[78.0,20.0],[78.01,20.0],[78.01,20.01],[78.0,20.01],[78.0,20.0]]]}}]}',
        encoding="utf-8",
    )
    provider = EarthEngineSatelliteProvider()
    geom = provider.roi_from_geojson(path)
    assert geom.geom_type == "Polygon"
    assert -180 <= geom.bounds[0] <= 180
    assert -90 <= geom.bounds[1] <= 90
