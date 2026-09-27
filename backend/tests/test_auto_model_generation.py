from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.modelling.auto_case import generate_delft3d_case, generate_dualsphysics_case

VARIANT = {
    "release_mode": "dam_breach",
    "model": "sph",
    "initial_reservoir_water_level_m": 120.0,
    "reservoir_volume_m3": 5_000_000.0,
    "breach_width_m": 20.0,
    "breach_depth_m": 10.0,
    "breach_formation_time_s": 100.0,
    "initial_discharge_m3s": 100.0,
    "controlled_release_discharge_m3s": None,
    "simulation_duration_s": 200.0,
}


def _write_dem(path: Path) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=5,
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=from_origin(500_000, 3_000_000, 10, 10),
    ) as dst:
        dst.write(np.arange(20, dtype=np.float32).reshape(4, 5), 1)


def test_dualsphysics_auto_case_is_valid_and_contains_scenario_geometry(tmp_path):
    dem = tmp_path / "dem.tif"
    _write_dem(dem)
    generated = generate_dualsphysics_case(variant_parameters=VARIANT, dem_path=dem, output_dir=tmp_path / "sph")
    case_path = Path(generated["native_input_directory"]) / generated["case_filename"]
    root = ET.parse(case_path).getroot()
    assert root.tag == "case"
    assert (case_path.parent / "hydroshield_auto_case.json").exists()
    assert (case_path.parent / "Case_Def.xml").exists()
    assert (case_path.parent / "hydroshield_auto_case.json").read_text(encoding="utf-8")
    text = case_path.read_text(encoding="utf-8")
    assert "HydroShield_Bathymetry.csv" in text
    assert "drawfilecsv" in text
    assert 'mode="bathymetry"' in text
    assert "drawbathymetry" not in text
    assert "<hswl " in text
    assert (case_path.parent / "HydroShield_Bathymetry.csv").exists()
    csv_lines = (case_path.parent / "HydroShield_Bathymetry.csv").read_text(encoding="utf-8").splitlines()
    assert csv_lines[0].startswith("Y \\ X => Z;")
    assert len(csv_lines) >= 2
    assert generated["metadata"]["generation_mode"] == "automatic"
    assert generated["metadata"]["breach_width_m"] == 20.0
    # Official GenCase CSV bathymetry is a rectangular Y-by-X matrix.
    rows = [line.split(";") for line in csv_lines[1:]]
    x_count = len(csv_lines[0].split(";")) - 1
    assert x_count > 0
    assert all(len(row) == x_count + 1 for row in rows)



def test_dualsphysics_auto_case_bounds_large_dem_for_workstation_runtime(tmp_path):
    dem = tmp_path / "large_dem.tif"
    data = np.linspace(0, 600, 400 * 400, dtype=np.float32).reshape(400, 400)
    with rasterio.open(
        dem, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1, dtype="float32",
        crs="EPSG:32643", transform=from_origin(500_000, 3_004_000, 10, 10)
    ) as dst:
        dst.write(data, 1)
    generated = generate_dualsphysics_case(variant_parameters=VARIANT, dem_path=dem, output_dir=tmp_path / "sph")
    meta = generated["metadata"]
    bounds = meta["domain_bounds"]
    assert bounds[2] - bounds[0] <= 1200.0 + 20.0
    assert bounds[3] - bounds[1] <= 1200.0 + 20.0
    assert meta["particle_spacing_m"] >= 15.0
    assert meta["estimated_domain_points"] <= 500_000 * 1.15


def test_dualsphysics_auto_case_iteratively_caps_high_relief_domains(tmp_path):
    dem = tmp_path / "high_relief.tif"
    data = np.linspace(0, 5000, 100 * 100, dtype=np.float32).reshape(100, 100)
    with rasterio.open(
        dem, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1, dtype="float32",
        crs="EPSG:32643", transform=from_origin(500_000, 5_001_000, 15, 15)
    ) as dst:
        dst.write(data, 1)
    generated = generate_dualsphysics_case(variant_parameters=VARIANT, dem_path=dem, output_dir=tmp_path / "sph")
    meta = generated["metadata"]
    assert meta["particle_spacing_m"] >= 15.0
    assert meta["estimated_domain_points"] <= 500_000 * 1.05


def test_delft3d_auto_case_writes_net_mdu_dimr_and_variable_bathymetry(tmp_path):
    dem = tmp_path / "dem.tif"
    _write_dem(dem)
    variant = {**VARIANT, "model": "delft3d"}
    generated = generate_delft3d_case(variant_parameters=variant, dem_path=dem, output_dir=tmp_path / "delft3d")
    directory = Path(generated["native_input_directory"])
    for name in ("hydroshield_net.nc", "hydroshield_waterlevel.xyz", "hydroshield.mdu", "dimr_config.xml", "hydroshield_auto_case.json"):
        assert (directory / name).exists(), name
    ET.parse(directory / "dimr_config.xml")
    ds = __import__("xarray").open_dataset(directory / "hydroshield_net.nc", engine="scipy")
    try:
        assert "NetNode_x" in ds
        assert "NetNode_y" in ds
        assert "NetNode_z" in ds
        assert float(ds["NetNode_z"].max()) > float(ds["NetNode_z"].min())
        assert int(ds.sizes["nNetElem"]) > 0
    finally:
        ds.close()
    mdu = (directory / "hydroshield.mdu").read_text(encoding="utf-8")
    assert "NetFile = hydroshield_net.nc" in mdu
    assert "WaterLevIniFile = hydroshield_waterlevel.xyz" in mdu
    manifest = json.loads((directory / "hydroshield_auto_case.json").read_text(encoding="utf-8"))
    assert manifest["generation_mode"] == "automatic"
