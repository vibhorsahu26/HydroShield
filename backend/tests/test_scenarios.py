
def valid_payload():
    return {
        "name": "Major Breach",
        "initial_reservoir_water_level_m": 100.0,
        "reservoir_volume_m3": 1_000_000.0,
        "breach_width_m": 40.0,
        "breach_depth_m": 20.0,
        "breach_formation_time_s": 600.0,
        "initial_discharge_m3s": 2500.0,
        "simulation_duration_s": 7200.0,
        "model": "both",
    }


def test_scenario_validation_accepts_supported_contract(client):
    response = client.post("/api/v1/scenarios/validate", json=valid_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["normalized_scenario"]["model"] == "both"


def test_scenario_rejects_breach_deeper_than_water_level(client):
    payload = valid_payload()
    payload["breach_depth_m"] = 101.0
    response = client.post("/api/v1/scenarios/validate", json=payload)
    assert response.status_code == 422


def test_scenario_rejects_breach_formation_longer_than_simulation(client):
    payload = valid_payload()
    payload["breach_formation_time_s"] = 9000.0
    response = client.post("/api/v1/scenarios/validate", json=payload)
    assert response.status_code == 422


def test_scenario_rejects_unknown_fields(client):
    payload = valid_payload()
    payload["fake_parameter"] = 123
    response = client.post("/api/v1/scenarios/validate", json=payload)
    assert response.status_code == 422
