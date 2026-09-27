from pathlib import Path

from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]


def run_alembic(tmp_db):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_db}")
    command.upgrade(cfg, "head")
    return cfg


def test_initial_migration_creates_all_persistence_tables(tmp_path):
    db_path = tmp_path / "migration.db"
    run_alembic(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"projects", "datasets", "scenarios", "scenario_variants", "spatial_features", "alembic_version"}.issubset(tables)
    finally:
        engine.dispose()


def test_initial_migration_can_downgrade_to_base(tmp_path):
    db_path = tmp_path / "migration-downgrade.db"
    cfg = run_alembic(db_path)
    command.downgrade(cfg, "base")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert "alembic_version" in tables
        assert not ({"projects", "datasets", "scenarios", "scenario_variants", "spatial_features"} & tables)
    finally:
        engine.dispose()


def test_postgis_migration_contract_contains_native_spatial_setup():
    migration = (ROOT / "alembic" / "versions" / "0001_initial_persistence.py").read_text()
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in migration
    assert "TYPE geometry(Geometry)" in migration
    assert "USING GIST (geom)" in migration
    assert "ST_Intersects" not in migration  # spatial querying belongs in the repository layer



def test_scenario_variants_migration_contract():
    migration = (ROOT / "alembic" / "versions" / "0002_scenario_variants.py").read_text()
    assert 'scenario_variants' in migration
    assert 'base_scenario_id' in migration
    assert 'uq_scenario_variants_base_code' in migration
    assert 'kind' in migration
    assert 'parameters' in migration
    assert 'assumptions' in migration


def test_phase7_migration_reaches_head(tmp_path):
    import subprocess, sys
    db_url = f"sqlite:///{tmp_path / 'phase7_head.db'}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={db_url}", "upgrade", "head"],
        cwd=__import__('pathlib').Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={db_url}", "current"],
        cwd=__import__('pathlib').Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "0006_automatic_data_acquisition" in result.stdout
