from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.satellite.comparison import compare_predicted_observed


def write_mask(path, data, *, crs="EPSG:32643", transform=None):
    transform = transform or from_origin(0, 40, 10, 10)
    with rasterio.open(path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1,
                       dtype="uint8", crs=crs, transform=transform, nodata=255) as dst:
        dst.write(data.astype("uint8"), 1)


def test_predicted_vs_observed_metrics_and_difference(tmp_path):
    model = np.array([[1, 1], [0, 0]], dtype="uint8")
    observed = np.array([[1, 0], [0, 1]], dtype="uint8")
    model_path = tmp_path / "model.tif"
    observed_path = tmp_path / "observed.tif"
    write_mask(model_path, model)
    write_mask(observed_path, observed)

    result = compare_predicted_observed(
        model_mask_path=str(model_path),
        observed_mask_path=str(observed_path),
        output_dir=tmp_path / "out",
    )
    m = result["metrics"]
    assert m["intersection_area_m2"] == 100.0
    assert m["union_area_m2"] == 300.0
    assert m["model_only_area_m2"] == 100.0
    assert m["observed_only_area_m2"] == 100.0
    assert m["iou"] == 1 / 3
    assert m["precision"] == 0.5
    assert m["recall"] == 0.5
    assert (tmp_path / "out" / "satellite_difference.tif").exists()
    assert (tmp_path / "out" / "observed_flood_extent.geojson").exists()


def test_no_overlap_fails(tmp_path):
    model_path = tmp_path / "model.tif"
    observed_path = tmp_path / "observed.tif"
    write_mask(model_path, np.ones((2, 2), dtype="uint8"), transform=from_origin(0, 40, 10, 10))
    write_mask(observed_path, np.ones((2, 2), dtype="uint8"), transform=from_origin(100, 140, 10, 10))
    try:
        compare_predicted_observed(model_mask_path=str(model_path), observed_mask_path=str(observed_path), output_dir=tmp_path / "out")
    except ValueError as exc:
        assert "no overlapping valid pixels" in str(exc)
    else:
        raise AssertionError("Expected no-overlap validation error")
