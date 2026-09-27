# Satellite validation

Phase 9 implements the HydroShield satellite-validation layer. The default Sentinel-1 provider uses Earth Engine's OPERA DSWx-S1 collection and the `BWTR_Binary_water` band. Invalid classes are masked before the temporal composite. Sentinel-2 uses the harmonized surface-reflectance collection with SCL exclusions and a configurable MNDWI threshold.

Validation compares the observed binary water mask to the Phase 8 model flood mask on the model's projected grid using nearest-neighbor reprojection. Outputs include observed flood extent GeoJSON, a three-state difference GeoTIFF, and spatial agreement metrics including IoU, precision, recall, F1, intersection, union, model-only and observed-only area.

The API requires an authenticated Earth Engine environment. The Python client is optional; install `.[earthengine]` and initialize Earth Engine with an appropriate Cloud project before using the live provider.

The implementation deliberately uses `getDownloadURL` for bounded prototype regions. For large or long-running exports, switch to Earth Engine batch image export to Cloud Storage/Drive.

The phase supports the specification's before/during/after event framing through the `phase` field; each phase is a separately reproducible validation request.
