from pathlib import Path


def test_phase9_migration_exists_and_is_current():
    text = Path('alembic/versions/0005_satellite_validation.py').read_text()
    assert 'revision = "0005_satellite_validation"' in text
    assert '0004_analysis_results' in text
    assert 'satellite_validation_results' in text
    assert 'collection_id' in text
    assert 'image_count' in text
