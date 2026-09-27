import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.session import get_db
from app.main import create_app


def make_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: SessionLocal()
    return TestClient(app), engine, SessionLocal


def test_dam_search_uses_provider(monkeypatch, tmp_path):
    from app.acquisition.manager import AcquisitionManager
    from app.acquisition.schemas import DamCandidate
    monkeypatch.setattr(AcquisitionManager, "__init__", lambda self, settings: setattr(self, "geocoder", type("G", (), {"search": lambda _s, *_a, **_k: [DamCandidate(display_name="Kosi Dam, Nepal", name="Kosi Dam", latitude=28.0, longitude=85.0)]})()))
    app = create_app()
    client = TestClient(app)
    response = client.post("/api/v1/acquisition/search", json={"query": "Kosi Dam"})
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["name"] == "Kosi Dam"
    assert body["provider"] == "OpenStreetMap Nominatim"


def test_acquisition_api_persists_project_run_and_dataset_records(monkeypatch, tmp_path):
    from app.acquisition.manager import AcquisitionManager
    from tests.test_datasets import make_dem_geotiff

    def fake_init(self, settings):
        def fake_fetch(_s, bbox, cache, out, resolution):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(make_dem_geotiff())
            return {"resolution": "90m", "tile_count": 1, "source": "Copernicus DEM GLO-90"}

        self.dem = type("D", (), {"fetch": fake_fetch})()
        self.overpass = type(
            "O",
            (),
            {
                "fetch": lambda _s, request: {"elements": [{"type": "way", "id": 1, "tags": {"waterway": "river", "name": "River"}, "geometry": [{"lat": 28.0, "lon": 85.0}, {"lat": 28.1, "lon": 85.1}]}]},
                "split_layers": lambda _s, payload, dam_point, river_name=None: __import__('app.acquisition.overpass', fromlist=['OverpassClient']).OverpassClient().split_layers(payload, dam_point=dam_point, river_name=river_name),
            },
        )()
        from app.database.repositories.projects import ProjectRepository
        from app.database.repositories.datasets import DatasetRepository
        self.geocoder = None
        self.projects = ProjectRepository()
        self.datasets = DatasetRepository()
        self.settings = settings
        self.geospatial = type("G", (), {"preprocess": lambda *a, **k: None})()

    monkeypatch.setattr(AcquisitionManager, "__init__", fake_init)

    client, engine, SessionLocal = make_client(tmp_path, monkeypatch)
    db = SessionLocal()
    from app.database.models import Project
    project = Project(name="Auto Acquisition Project")
    db.add(project)
    db.commit()
    db.refresh(project)
    db.close()

    payload = {"dam_name": "Selected Dam", "latitude": 28.0, "longitude": 85.0, "radius_km": 2, "auto_preprocess": False}
    response = client.post(f"/api/v1/acquisition/projects/{project.id}/run", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["datasets"]
    assert any(item["logical_type"] == "dam" for item in body["datasets"])
    assert any(item["logical_type"] == "dem" for item in body["datasets"])
    engine.dispose()


def test_acquisition_api_respects_include_exposure_false(monkeypatch, tmp_path):
    from app.acquisition.manager import AcquisitionManager
    from tests.test_datasets import make_dem_geotiff
    from app.acquisition.overpass import OverpassClient
    from app.database.models import Project

    def fake_init(self, settings):
        self.settings = settings
        self.projects = __import__('app.database.repositories.projects', fromlist=['ProjectRepository']).ProjectRepository()
        self.datasets = __import__('app.database.repositories.datasets', fromlist=['DatasetRepository']).DatasetRepository()
        self.dem = type('D', (), {'fetch': lambda _s, bbox, cache, out, resolution: (out.parent.mkdir(parents=True, exist_ok=True), out.write_bytes(make_dem_geotiff()), {'resolution':'90m','tile_count':1,'source':'fake'})[-1]})()
        self.overpass = OverpassClient()
        self.geospatial = type('G', (), {'preprocess': lambda *a, **k: None})()
        self.geocoder = None
    # use a real Overpass splitter/query fixture
    monkeypatch.setattr(AcquisitionManager, '__init__', fake_init)
    original_split = OverpassClient.split_layers
    monkeypatch.setattr(OverpassClient, 'fetch', lambda self, request: {'elements':[{'type':'way','id':1,'tags':{'waterway':'river','name':'River'},'geometry':[{'lat':28.0,'lon':85.0},{'lat':28.1,'lon':85.1}]}]})
    client, engine, SessionLocal = make_client(tmp_path, monkeypatch)
    db=SessionLocal(); project=Project(name='No Exposure'); db.add(project); db.commit(); db.refresh(project); db.close()
    response=client.post(f'/api/v1/acquisition/projects/{project.id}/run', json={'dam_name':'Dam','latitude':28.0,'longitude':85.0,'radius_km':2,'include_exposure':False,'auto_preprocess':False})
    assert response.status_code == 201, response.text
    logical={item['logical_type'] for item in response.json()['datasets']}
    assert 'dem' in logical and 'river' in logical and 'dam' in logical
    assert not {'road','bridge','settlement','critical_infrastructure'} & logical
    engine.dispose()
