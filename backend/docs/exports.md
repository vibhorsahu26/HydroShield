# HydroShield Export Layer — Phase 10

Phase 10 exposes GIS-ready exports from persisted Phase 8 analysis results.

## Supported formats

- `geojson`: flood extent vector in its analysis CRS.
- `shp`: self-contained ZIP containing `.shp`, `.shx`, `.dbf`, `.prj` and related files.
- `kml`: flood extent reprojected to EPSG:4326 for common mapping clients.
- `geotiff`: copies a selected raster artifact while preserving CRS, transform, nodata and values.
- `csv`: flattened analysis metrics, exposure values and layer metrics.
- `json`: analysis metadata, metrics, exposure, artifacts, warnings and assumptions.

## API

`GET /api/v1/exports/analysis/{result_id}?format=geojson`

`GET /api/v1/exports/analysis/{result_id}?format=shp`

`GET /api/v1/exports/analysis/{result_id}?format=kml`

`GET /api/v1/exports/analysis/{result_id}?format=geotiff&artifact=water_depth`

GeoTIFF artifact values:

`water_depth`, `flood_mask`, `velocity`, `arrival_time`, `water_level`

`GET /api/v1/exports/analysis/{result_id}?format=csv`

`GET /api/v1/exports/analysis/{result_id}?format=json`

A consolidated export package is available at:

`GET /api/v1/exports/analysis/{result_id}/package`

The package contains every exportable artifact currently available for the analysis result.

Comparison statistics can be exported as JSON or CSV using:

`GET /api/v1/exports/comparisons/{comparison_id}?format=json`

`GET /api/v1/exports/comparisons/{comparison_id}?format=csv`

## Design rules

Exports are generated from persisted analysis records rather than accepting arbitrary filesystem paths from the API caller. Missing optional artifacts result in a clear 422 response. Raster exports retain the source grid and CRS; KML is converted to WGS84 because KML coordinates are longitude/latitude.

The export layer does not calculate new hydraulic results. It packages and converts outputs already produced by the modelling and analysis pipeline.
