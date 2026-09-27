from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.exports.preview import build_raster_preview


def test_build_raster_preview_outputs_wgs84_png(tmp_path):
    source = tmp_path / 'depth.tif'
    profile = {
        'driver':'GTiff','height':3,'width':4,'count':1,'dtype':'float32','crs':'EPSG:32643',
        'transform':from_origin(500000, 3200000, 30, 30),'nodata':-9999,
    }
    with rasterio.open(source,'w',**profile) as dst:
        dst.write(np.arange(12,dtype='float32').reshape(3,4),1)
    output = tmp_path / 'preview.png'
    bounds, meta = build_raster_preview(source, output)
    assert output.exists() and output.stat().st_size > 0
    assert len(bounds) == 2 and bounds[0][0] < bounds[1][0] and bounds[0][1] < bounds[1][1]
    assert meta['width'] > 0 and meta['height'] > 0
