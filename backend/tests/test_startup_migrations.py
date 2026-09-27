from pathlib import Path

from alembic import command
from alembic.config import Config


def test_alembic_config_resolves_from_app_parent(tmp_path):
    db = tmp_path / "startup.db"
    cfg = Config(str(Path("alembic.ini").resolve()))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
    from sqlalchemy import create_engine, inspect
    engine = create_engine(f"sqlite:///{db}")
    tables = set(inspect(engine).get_table_names())
    assert {"projects", "scenario_variants", "simulation_jobs", "analysis_results", "satellite_validation_results", "acquisition_runs"}.issubset(tables)
    engine.dispose()
