import os

import pytest


POSTGRES_URL = os.getenv("HYDROSHIELD_TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="Set HYDROSHIELD_TEST_POSTGRES_URL to run real PostGIS integration tests")
def test_real_postgis_is_configured():
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(POSTGRES_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT PostGIS_Full_Version()")
            value = cur.fetchone()[0]
            assert "POSTGIS" in value.upper()
