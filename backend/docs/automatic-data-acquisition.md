# Automatic Data Acquisition

HydroShield can prepare a study from a selected dam instead of requiring the user to manually locate the core geospatial files.

## Normal workflow

1. Search for a dam/place through the explicit dam-search action.
2. Select a result and provide an optional downstream river name and study radius.
3. Run automatic acquisition.
4. HydroShield downloads and validates:
   - Copernicus DEM GLO-30 when the requested tiles are publicly accessible, otherwise a homogeneous GLO-90 fallback.
   - OpenStreetMap river and dam/network/exposure features through one bounded Overpass query.
5. The existing Phase 4 geospatial preprocessing pipeline prepares the DEM, river and computational domain.
6. Acquired datasets are stored with provider, source, checksum, license, timestamps and logical type provenance.

Hydrology, rainfall and land-cover remain manual/optional because the project specification marks those inputs as applicable rather than requiring a single universal public provider.

## Providers

- Dam search: OpenStreetMap Nominatim.
- River/dam/roads/bridges/settlements/critical infrastructure: OpenStreetMap Overpass API.
- DEM: AWS Open Data Copernicus DEM public buckets.
- Satellite validation is still handled separately by the Phase 9 Earth Engine integration.

The application caches Nominatim and Overpass responses to reduce repeated requests. It serializes outbound provider requests per process and uses an identifying User-Agent. OSM attribution is retained in the acquisition response and persisted metadata.

## API

`POST /api/v1/acquisition/search`

Search for a dam/place. Search is explicit rather than autocomplete.

`POST /api/v1/acquisition/projects/{project_id}/run`

Run acquisition and optional preprocessing for the selected dam.

`GET /api/v1/acquisition/projects/{project_id}/runs`

List previous acquisition runs so a prepared study can be restored after a dashboard refresh.

`GET /api/v1/projects/{project_id}/datasets/{dataset_id}/preview`

Render a stored vector dataset as WGS84 GeoJSON for the map.

## Reliability boundary

Provider outages, rate limits, missing source coverage and incomplete OpenStreetMap tagging are surfaced as warnings/errors. HydroShield never fabricates a DEM, river, infrastructure layer or satellite observation when the provider cannot supply one.
