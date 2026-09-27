from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.modelling.sph.result_to_rasters import build_sph_analysis_rasters


def write_dem(path: Path) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=3,
        height=3,
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=from_origin(0, 30, 10, 10),
        nodata=-9999,
    ) as dst:
        dst.write(np.full((3, 3), 100.0, dtype="float32"), 1)


def write_frame(path: Path, rows: list[tuple[float, float, float, float, float, float]]) -> None:
    path.write_text(
        "x [m];y [m];z [m];vel.x [m/s];vel.y [m/s];vel.z [m/s]\n"
        + "\n".join(";".join(str(v) for v in row) for row in rows)
        + "\n",
        encoding="utf-8",
    )


def test_native_sph_particles_become_depth_velocity_and_arrival_rasters(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    particles = work / "dual_sphysics" / "HydroShieldCase_out" / "particles"
    particles.mkdir(parents=True)
    write_frame(particles / "PartFluid_0000.csv", [(5, 25, 100.2, 0, 3, 0)])
    write_frame(particles / "PartFluid_0001.csv", [(5, 25, 101.0, 0, 4, 0), (15, 15, 100.3, 1, 0, 0)])

    result = build_sph_analysis_rasters(
        working_directory=work,
        dem_path=dem,
        output_directory=tmp_path / "analysis",
        output_interval_s=1.0,
        flood_threshold_m=0.05,
    )

    with rasterio.open(result["water_depth_raster"]) as src:
        depth = src.read(1)
        assert src.crs.to_string() == "EPSG:32643"
        assert depth[0, 0] == 1.0
        assert depth[1, 1] == 0.3
    with rasterio.open(result["velocity_raster"]) as src:
        velocity = src.read(1)
        assert velocity[0, 0] == 4.0
        assert velocity[1, 1] == 1.0
    with rasterio.open(result["arrival_time_raster"]) as src:
        arrival = src.read(1)
        assert arrival[0, 0] == 0.0
        assert arrival[1, 1] == 1.0
    with rasterio.open(result["water_level_raster"]) as src:
        level = src.read(1)
        assert level[0, 0] == 101.0

    assert result["summary"]["max_water_depth_m"] == 1.0
    assert result["summary"]["max_velocity_mps"] == 4.0
    assert result["summary"]["inundated_cell_count"] == 2
    assert result["summary"]["first_arrival_time_s"] == 0.0
    assert len(result["summary"]["frames"]) == 2


def test_native_sph_result_rejects_non_overlapping_particles_with_coordinate_diagnostics(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    particles = work / "dual_sphysics" / "particles"
    particles.mkdir(parents=True)
    write_frame(particles / "PartFluid_0000.csv", [(1000, 1000, 100.0, 1, 0, 0)])

    import pytest

    with pytest.raises(ValueError, match="do not overlap.*DEM bounds=.*particle bounds="):
        build_sph_analysis_rasters(
            working_directory=work,
            dem_path=dem,
            output_directory=tmp_path / "analysis",
            output_interval_s=1.0,
            flood_threshold_m=0.05,
        )


def test_native_sph_result_reports_detected_columns_when_invalid(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    particles = work / "dual_sphysics" / "particles"
    particles.mkdir(parents=True)
    (particles / "PartFluid_0000.csv").write_text("idp;pressure\n1;0\n", encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="Detected columns: idp, pressure"):
        build_sph_analysis_rasters(
            working_directory=work,
            dem_path=dem,
            output_directory=tmp_path / "analysis",
            output_interval_s=1.0,
            flood_threshold_m=0.05,
        )


def test_native_sph_ignores_statistics_csv_and_recovers_from_bi4_with_partvtk_csv(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    out = work / "dual_sphysics" / "HydroShieldCase_out"
    data = out / "data"
    data.mkdir(parents=True)
    for frame_id in (0, 1):
        (data / f"Part_{frame_id:04d}.bi4").write_bytes(b"synthetic")
    (out / "HydroShieldCase.xml").write_text("<case/>", encoding="utf-8")

    particles = out / "particles"
    particles.mkdir()
    (particles / "PartFluid_0000.csv").write_text(
        "TimeStep;Np;Nbound;Nfixed;Nmoving;Nfloat;Nfluid\n0;10;5;5;0;0;5\n",
        encoding="utf-8",
    )

    fake = tmp_path / "fake_partvtk.py"
    fake.write_text(
        r'''import sys
from pathlib import Path
args=sys.argv[1:]
assert args[args.index('-filexml')+1] == 'AUTO'
assert '-onlytype:-all,+fluid' in args
assert '-vars:+idp,+vel,+rhop,+press,+type' in args
prefix=Path(args[args.index('-savecsv')+1])
prefix.parent.mkdir(parents=True, exist_ok=True)
header='x [m];y [m];z [m];vel.x [m/s];vel.y [m/s];vel.z [m/s]\n'
(prefix.parent/(prefix.name+'_0000.csv')).write_text(header+'5;25;101;0;2;0\n', encoding='utf-8')
(prefix.parent/(prefix.name+'_0001.csv')).write_text(header+'5;25;102;0;4;0\n15;15;100.5;3;0;0\n', encoding='utf-8')
''',
        encoding="utf-8",
    )

    result = build_sph_analysis_rasters(
        working_directory=work,
        dem_path=dem,
        output_directory=tmp_path / "analysis",
        output_interval_s=1.0,
        flood_threshold_m=0.05,
        partvtk_executable=f"{__import__('sys').executable} {fake}",
    )
    assert result["provenance"]["particle_source_format"] == "partvtk_csv_recovery"
    assert result["summary"]["max_water_depth_m"] == 2.0
    assert result["summary"]["max_velocity_mps"] == 4.0
    assert result["summary"]["frame_ids"] == [0, 1]
    assert any("TimeStep" in warning for warning in result["warnings"])


def test_native_sph_prefers_authoritative_bi4_frames_over_partial_particle_csv(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    out = work / "dual_sphysics" / "HydroShieldCase_out"
    data = out / "data"
    data.mkdir(parents=True)
    for frame_id in (0, 1, 2):
        (data / f"Part_{frame_id:04d}.bi4").write_bytes(b"synthetic")
    (out / "HydroShieldCase.xml").write_text("<case/>", encoding="utf-8")

    particles = out / "particles"
    particles.mkdir()
    (particles / "PartFluid_0000.csv").write_text(
        "x [m];y [m];z [m];vel.x [m/s];vel.y [m/s];vel.z [m/s]\n5;25;101;0;1;0\n",
        encoding="utf-8",
    )
    fake = tmp_path / "fake_partvtk.py"
    fake.write_text(
        r'''import sys
from pathlib import Path
args=sys.argv[1:]
prefix=Path(args[args.index('-savecsv')+1])
prefix.parent.mkdir(parents=True, exist_ok=True)
header='x [m];y [m];z [m];vel.x [m/s];vel.y [m/s];vel.z [m/s]\n'
for i, z in enumerate((101, 102, 103)):
    (prefix.parent/f'{prefix.name}_{i:04d}.csv').write_text(header+f'5;25;{z};0;{i+1};0\n', encoding='utf-8')
''',
        encoding="utf-8",
    )
    result = build_sph_analysis_rasters(
        working_directory=work,
        dem_path=dem,
        output_directory=tmp_path / "analysis",
        output_interval_s=1.0,
        flood_threshold_m=0.05,
        partvtk_executable=f"{__import__('sys').executable} {fake}",
    )
    assert result["summary"]["frame_ids"] == [0, 1, 2]
    assert result["summary"]["time_steps"] == 3
    assert result["provenance"]["particle_source_format"] == "partvtk_csv_recovery"


def test_native_sph_reuses_complete_existing_partvtk_csv_frames_without_recovery(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    out = work / "dual_sphysics" / "HydroShieldCase_out"
    data = out / "data"
    particles = out / "particles"
    data.mkdir(parents=True)
    particles.mkdir(parents=True)
    for frame_id in (0, 1):
        (data / f"Part_{frame_id:04d}.bi4").write_bytes(b"synthetic")
        write_frame(particles / f"PartFluid_{frame_id:04d}.csv", [(5, 25, 101 + frame_id, 0, 2 + frame_id, 0)])

    result = build_sph_analysis_rasters(
        working_directory=work,
        dem_path=dem,
        output_directory=tmp_path / "analysis",
        output_interval_s=1.0,
        flood_threshold_m=0.05,
        partvtk_executable=str(tmp_path / "definitely-missing-partvtk"),
    )

    assert result["provenance"]["particle_source_format"] == "partvtk_csv"
    assert result["summary"]["frame_ids"] == [0, 1]
    assert any("complete PartVTK particle CSV frame set" in warning for warning in result["warnings"])


def test_native_sph_fails_when_partvtk_recovery_misses_authoritative_frame(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    out = work / "dual_sphysics" / "HydroShieldCase_out"
    data = out / "data"
    data.mkdir(parents=True)
    for frame_id in (0, 1, 2):
        (data / f"Part_{frame_id:04d}.bi4").write_bytes(b"synthetic")
    (out / "HydroShieldCase.xml").write_text("<case/>", encoding="utf-8")
    fake = tmp_path / "fake_partvtk.py"
    fake.write_text(
        r'''import sys
from pathlib import Path
args=sys.argv[1:]
prefix=Path(args[args.index('-savecsv')+1])
prefix.parent.mkdir(parents=True, exist_ok=True)
header='x [m];y [m];z [m];vel.x [m/s];vel.y [m/s];vel.z [m/s]\n'
for i, z in enumerate((101, 102)):
    (prefix.parent/f'{prefix.name}_{i:04d}.csv').write_text(header+f'5;25;{z};0;1;0\n', encoding='utf-8')
''',
        encoding="utf-8",
    )
    import pytest

    with pytest.raises(ValueError, match="did not produce a complete frame set"):
        build_sph_analysis_rasters(
            working_directory=work,
            dem_path=dem,
            output_directory=tmp_path / "analysis",
            output_interval_s=1.0,
            flood_threshold_m=0.05,
            partvtk_executable=f"{__import__('sys').executable} {fake}",
        )


def test_partvtk_csv_with_metadata_preamble_is_parsed_as_particle_data(tmp_path):
    dem = tmp_path / "dem.tif"
    write_dem(dem)
    work = tmp_path / "work"
    out = work / "dual_sphysics" / "HydroShieldCase_out"
    data = out / "data"
    particles = out / "particles"
    data.mkdir(parents=True)
    particles.mkdir(parents=True)
    (data / "Part_0000.bi4").write_bytes(b"synthetic")

    # Native PartVTK CSVs can contain metadata lines before the actual particle-table header.
    (particles / "PartFluid_0000.csv").write_text(
        "TimeStep [s];Np;Nbound;Nfixed;Nmoving;Nfloat;Nfluid\n"
        "0;10;5;5;0;0;5\n"
        "x [m],y [m],z [m],vel.x [m/s],vel.y [m/s],vel.z [m/s]\n"
        "5,25,101,0,3,0\n",
        encoding="utf-8",
    )

    result = build_sph_analysis_rasters(
        working_directory=work,
        dem_path=dem,
        output_directory=tmp_path / "analysis",
        output_interval_s=1.0,
        flood_threshold_m=0.05,
    )

    assert result["provenance"]["particle_source_format"] == "partvtk_csv"
    assert result["summary"]["max_water_depth_m"] == 1.0
    assert result["summary"]["max_velocity_mps"] == 3.0
