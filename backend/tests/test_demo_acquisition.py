from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.database.base import Base
from app.database.models import Project
from app.database.session import get_db
from app.main import create_app


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    get_settings.cache_clear()
    settings = get_settings()
    settings.storage_root = tmp_path / "uploads"
    settings.processing_work_dir = tmp_path / "processed"
    settings.export_root = tmp_path / "exports"
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: SessionLocal()
    return TestClient(app), SessionLocal, engine


def test_demo_search_works_without_network(monkeypatch):
    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    monkeypatch.setattr("app.acquisition.nominatim.NominatimClient.search", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("network unavailable")))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post("/api/v1/acquisition/search", json={"query": "Kosi Dam"})
    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert candidate["latitude"] == 28.8312653382
    assert candidate["longitude"] == 77.0395865173


def test_demo_acquisition_seeds_all_required_layers_and_preprocesses(tmp_path, monkeypatch):
    monkeypatch.setattr("app.acquisition.dem.CopernicusDemProvider.fetch", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("network unavailable")))
    monkeypatch.setattr("app.acquisition.overpass.OverpassClient.fetch", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("network unavailable")))
    client, SessionLocal, engine = make_client(tmp_path, monkeypatch)
    db = SessionLocal()
    project = Project(name="Prototype Acquisition")
    db.add(project)
    db.commit()
    db.refresh(project)
    project_id = project.id
    db.close()

    response = client.post(
        f"/api/v1/acquisition/projects/{project_id}/run",
        json={
            "dam_name": "Prototype Dam",
            "latitude": 28.8312653382,
            "longitude": 77.0395865173,
            "radius_km": 10,
            "river_name": "HydroShield River",
            "include_exposure": True,
            "auto_preprocess": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    logical = {item["logical_type"] for item in body["datasets"]}
    assert {"dem", "river", "dam", "settlement", "road", "building", "bridge", "critical_infrastructure"}.issubset(logical)
    assert body["preprocessing"]["dem"]["path"]
    assert body["preprocessing"]["river"]["path"]
    assert body["preprocessing"]["domain"]["path"]
    assert body["preprocessing"]["river_name"] == "HydroShield River"

    # Confirm the generated artifacts are real files, not only API metadata.
    for item in body["datasets"]:
        assert Path(item["storage_uri"]).is_file()
    engine.dispose()


def test_demo_acquisition_prefers_live_terrain_and_osm_layers(tmp_path, monkeypatch):
    from app.acquisition.overpass import OverpassClient
    from app.database.models import Project
    from app.acquisition.schemas import AutomaticAcquisitionRequest

    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    get_settings.cache_clear()
    settings = get_settings()
    settings.storage_root = tmp_path / "uploads"
    settings.processing_work_dir = tmp_path / "processed"
    settings.export_root = tmp_path / "exports"
    engine = create_engine(f"sqlite:///{tmp_path / 'live-first.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionLocal()
    project = Project(name="Live First")
    db.add(project); db.commit(); db.refresh(project)

    from tests.test_automatic_acquisition_e2e import dem_bytes
    class FakeDem:
        def fetch(self, bbox, cache_dir, output_path, resolution):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(dem_bytes())
            return {"resolution":"90m","tile_count":1,"source":"Live Copernicus fixture"}

    live_payload = {"elements":[
      {"type":"way","id":101,"tags":{"waterway":"river","name":"Live River"},"geometry":[{"lat":28.05,"lon":85.02},{"lat":28.15,"lon":85.15}]},
      {"type":"node","id":102,"tags":{"man_made":"dam","name":"Live Dam"},"lat":28.10,"lon":85.10},
      {"type":"node","id":103,"tags":{"place":"village","name":"Live Village"},"lat":28.12,"lon":85.12}
    ]}
    class FakeOverpass:
        def fetch(self, request): return live_payload
        def split_layers(self, payload, *, dam_point, river_name=None): return OverpassClient().split_layers(payload, dam_point=dam_point, river_name=river_name)

    manager = __import__("app.acquisition.manager", fromlist=["AcquisitionManager"]).AcquisitionManager(settings)
    manager.dem = FakeDem()
    manager.overpass = FakeOverpass()
    request = AutomaticAcquisitionRequest(dam_name="Live Dam", latitude=28.1, longitude=85.1, radius_km=5, river_name="Live River", include_exposure=True, auto_preprocess=True)
    run, acquired, preprocessing, warnings, _ = manager.run(db, project.id, request)
    assert run.status == "completed"
    assert run.provider_summary["mode"] == "live_first"
    by_type = {item["logical_type"]: item for item in acquired}
    assert by_type["dem"]["provider"] == "Copernicus DEM"
    assert by_type["river"]["provider"] == "OpenStreetMap Overpass API"
    assert Path(by_type["river"]["record"].storage_uri).is_file()
    assert preprocessing and preprocessing["river_name"] == "Live River"
    db.close(); engine.dispose(); get_settings.cache_clear()


def test_demo_search_prefers_live_nominatim_results(monkeypatch):
    from app.acquisition.manager import AcquisitionManager
    from app.acquisition.schemas import DamCandidate
    from app.core.config import Settings

    monkeypatch.setenv("HYDROSHIELD_DEMO_MODE", "true")
    get_settings.cache_clear()
    settings = Settings(demo_mode=True)
    live = DamCandidate(
        display_name="Live Dam, India", name="Live Dam", latitude=23.0, longitude=72.0,
        osm_type="node", osm_id=123, category="man_made", object_type="dam", river_name=None,
    )
    class FakeGeocoder:
        def search(self, query, country_code=None):
            return [live]
    manager = AcquisitionManager(settings)
    manager.geocoder = FakeGeocoder()
    result = manager.search_dams("Live Dam")
    assert result == [live]
    get_settings.cache_clear()
