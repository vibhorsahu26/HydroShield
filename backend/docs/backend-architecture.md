# HydroShield Backend Architecture

## Source-of-truth requirements

The backend is an automation/decision-support layer around geospatial preprocessing and hydrodynamic engines. The specification calls for a pipeline of data acquisition, geospatial preprocessing, scenario generation, hydrodynamic modelling, result comparison, risk analysis, satellite validation and GIS export. It explicitly names FastAPI/Python plus GDAL, Rasterio, GeoPandas, Shapely, PyProj, NumPy, SciPy and Xarray; PostgreSQL/PostGIS is the proposed database; outputs include GeoJSON, SHP, KML and GeoTIFF. See the supplied specification around system architecture and technology stack.

## Target architecture

```text
React Dashboard
       |
       v
FastAPI API
       |
       +----------------------+
       |                      |
       v                      v
Application Services      Job Orchestrator
       |                      |
       +----------+-----------+
                  |
                  v
        Geospatial Processing
                  |
          +-------+-------+
          |               |
          v               v
        Raster          Vector
       Pipeline        Pipeline
          |               |
          +-------+-------+
                  |
                  v
          Common Model Domain
                  |
            +-----+-----+
            |           |
            v           v
           SPH       Delft3D FM
            |           |
            +-----+-----+
                  |
                  v
           Result Processor
                  |
      +-----------+------------+
      |           |            |
      v           v            v
   Flood Map   Risk/Impact  Comparison
      |           |            |
      +-----------+------------+
                  |
                  v
        Satellite/GEE Validation
                  |
                  v
               Export
     GeoJSON / SHP / KML / GeoTIFF

              PostgreSQL + PostGIS
       metadata + spatial result layers
```

## Exact planned file tree

```text
hydroshield-backend/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── docs/
│   └── backend-architecture.md
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       ├── datasets.py
│   │       ├── projects.py
│   │       ├── scenarios.py
│   │       ├── simulations.py
│   │       ├── results.py
│   │       ├── validation.py
│   │       └── exports.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── errors.py
│   │   └── security.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── datasets.py
│   │   ├── projects.py
│   │   ├── scenarios.py
│   │   ├── simulations.py
│   │   ├── results.py
│   │   ├── validation.py
│   │   └── exports.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── session.py
│   │   ├── models.py
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── projects.py
│   │       ├── datasets.py
│   │       ├── scenarios.py
│   │       ├── simulations.py
│   │       └── results.py
│   ├── geospatial/
│   │   ├── __init__.py
│   │   ├── raster.py
│   │   ├── vector.py
│   │   ├── crs.py
│   │   ├── dem.py
│   │   ├── domain.py
│   │   └── validation.py
│   ├── modelling/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── schemas.py
│   │   ├── sph/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   ├── input_builder.py
│   │   │   └── parser.py
│   │   └── delft3d/
│   │       ├── __init__.py
│   │       ├── adapter.py
│   │       ├── input_builder.py
│   │       └── parser.py
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── jobs.py
│   │   ├── runner.py
│   │   └── states.py
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── flood_metrics.py
│   │   ├── risk.py
│   │   ├── comparison.py
│   │   └── exposure.py
│   ├── satellite/
│   │   ├── __init__.py
│   │   ├── gee.py
│   │   ├── water_extent.py
│   │   └── comparison.py
│   ├── exports/
│   │   ├── __init__.py
│   │   ├── geojson.py
│   │   ├── shapefile.py
│   │   ├── kml.py
│   │   ├── geotiff.py
│   │   └── csv.py
│   └── services/
│       ├── __init__.py
│       ├── project_service.py
│       ├── dataset_service.py
│       ├── scenario_service.py
│       ├── simulation_service.py
│       ├── result_service.py
│       └── validation_service.py
└── tests/
    ├── conftest.py
    ├── test_health.py
    ├── test_datasets.py
    ├── test_projects.py
    ├── test_scenarios.py
    ├── test_geospatial.py
    ├── test_orchestration.py
    ├── test_models.py
    ├── test_analysis.py
    ├── test_satellite_validation.py
    └── test_exports.py
```

Files in the tree are created only as the corresponding phase starts; this avoids placeholder code pretending that an unimplemented solver is production-ready.

## Phase-by-phase implementation order

### Phase 1 — Backend foundation — COMPLETE

Create the FastAPI app factory, configuration, logging, error handling, route registration and initial API contracts.

Verification: import checks, compilation, pytest, TestClient smoke tests, OpenAPI path check, and real Uvicorn health check.

### Phase 2 — Data intake + validation — COMPLETE

Create dataset typing and validators for GeoTIFF, vector data and hydrology/rainfall CSVs. Validate file format, size, CRS, raster shape/bands, geometry types and basic tabular structure.

Verification: generated valid DEM GeoTIFF, valid river GeoJSON, invalid river geometry, invalid extension and API response checks.

### Phase 3 — Persistence + PostGIS

Create SQLAlchemy models, repository interfaces, Alembic migrations, PostgreSQL/PostGIS connection handling, dataset/project/scenario persistence and spatial indexes.

Verification: migration upgrade/downgrade, repository CRUD integration tests and PostGIS spatial-query tests. A real PostGIS instance is required for completion of this phase.

### Phase 3 — Persistence + PostGIS — COMPLETE

The persistence layer now contains:

```text
app/database/base.py
app/database/models.py
app/database/session.py
app/database/repositories/projects.py
app/database/repositories/datasets.py
app/database/repositories/scenarios.py
app/database/repositories/spatial_features.py
app/services/project_service.py
app/services/persistence_service.py
app/schemas/projects.py
app/schemas/persistence.py
alembic/env.py
alembic/versions/0001_initial_persistence.py
alembic.ini
```

The schema persists projects, validated dataset metadata, scenarios/configuration and generic vector features. PostgreSQL migrations enable PostGIS, convert the feature geometry column to native `geometry(Geometry)` and create a GiST index. The spatial repository uses native PostGIS functions for geometry insertion and bounding-box intersection queries; SQLite uses WKB/Shapely only as a local test backend.

Integration endpoints are now:

```text
POST /api/v1/projects
GET  /api/v1/projects/{project_id}
POST /api/v1/projects/{project_id}/datasets
GET  /api/v1/projects/{project_id}/datasets
POST /api/v1/projects/{project_id}/scenarios
GET  /api/v1/projects/{project_id}/scenarios
```

A dataset record may only be persisted against an existing project, and scenarios pass through the same `ScenarioConfig` validation contract used by the Phase 1 validator before being stored. Phase 2's real DEM validation response is exercised in the Phase 3 integration test before persistence.

Verification: full pytest suite, strict-warning run, Python compilation, Alembic SQLite upgrade/downgrade, static PostgreSQL migration SQL generation, PostGIS migration-contract assertions, OpenAPI path inspection and live API smoke testing.

### Phase 4 — Geospatial preprocessing — COMPLETE

The preprocessing layer now provides a common metric processing CRS, validates inputs through the Phase 2 dataset validator, prepares river linework, creates a buffered computational corridor clipped to the DEM footprint, and produces a model-ready terrain package.

Implemented files:

```text
app/geospatial/crs.py
app/geospatial/raster.py
app/geospatial/vector.py
app/geospatial/domain.py
app/geospatial/preprocessing.py
app/services/geospatial_service.py
app/schemas/geospatial.py
app/api/routes/geospatial.py
tests/test_geospatial.py
tests/test_geospatial_api.py
```

The preprocessing endpoint is:

```text
POST /api/v1/geospatial/preprocess
```

Inputs are a DEM GeoTIFF and river GeoJSON plus optional target CRS, DEM resolution and river buffer. When no target CRS is supplied, the backend selects a projected metric CRS from the dataset location; geographic/projected datasets are normalized into that common CRS. A non-metric geographic CRS such as EPSG:4326 is rejected as a processing CRS because buffering and modelling-domain dimensions are defined in metres.

Generated artifacts per preprocessing run:

```text
processed_dem.tif
prepared_river.gpkg
computational_domain.gpkg
domain_mask.tif
```

The processed DEM is clipped to the buffered river corridor and resampled with bilinear interpolation at the requested metric resolution. The prepared river is cleaned, exploded into usable line geometries, reprojected and clipped to the processed DEM footprint. The computational domain is stored in the same CRS as the processed DEM, and its raster mask is checked for exact grid alignment.

Verification: deterministic WGS84 DEM/river fixtures, automatic UTM selection, explicit CRS handling, non-metric CRS rejection, artifact existence, output CRS consistency, DEM resolution, river length, domain area, aligned domain mask, API integration, Phase 2 validation reuse, strict-warning pytest execution and Alembic regression tests.

### Phase 5 — Scenario generation

Implement reusable breach/release scenario templates, parameter validation, scenario versioning and deterministic model-input generation.

Verification: parameter edge cases, deterministic output hashes, scenario-difference tests and schema round trips.

### Phase 6 — Hydrodynamic adapters

Implement a common solver interface plus isolated SPH and Delft3D FM adapters. The backend orchestrates solvers; it does not pretend to replace them.

Verification: adapter contract tests, fixture runs with stub executables, command construction, timeout handling, output discovery and parser tests. Full physics validation requires actual solver runs.

### Phase 7 — Background execution

Move long simulations out of request/response execution into a job system. Track states such as preparing, generating model, running, processing and complete.

Verification: job lifecycle transitions, retry behaviour, cancellation, idempotency and failure recovery.

### Phase 8 — Result processing + risk analysis

Normalize solver outputs into a common raster/grid representation. Compute extent, max depth, velocity, arrival time, inundated area, settlement/road/infrastructure exposure and scenario/model differences.

Verification: synthetic raster/vector fixtures with hand-calculated expected values.

### Phase 9 — Satellite/GEE validation

Integrate observation retrieval/preprocessing, observed water extent creation and model-vs-observation spatial agreement/difference layers.

Verification: mocked GEE responses, known raster masks and agreement metrics.

### Phase 10 — GIS exports

Generate GeoJSON, SHP, KML, GeoTIFF, CSV and JSON outputs with stable CRS metadata and downloadable job artifacts.

Verification: open exported files with the same libraries used for ingestion and assert geometry/CRS/attribute integrity.

### Phase 11 — Production hardening

Authentication/authorization, rate limits, request-size limits, structured audit logs, secrets, containerization, health/readiness checks, metrics, object storage, cleanup policies and deployment configuration.

Verification: security tests, container build, startup checks, configuration validation and end-to-end staging test.

## Rules for the implementation

1. Solvers are adapters behind interfaces; no solver-specific logic is allowed in API routes.
2. Heavy geospatial and simulation work never runs synchronously inside a normal HTTP request.
3. Every stage produces explicit metadata, assumptions and version information.
4. Result layers use a common CRS/grid contract before model comparison.
5. Failed jobs retain diagnostic logs and status; they are not silently marked complete.
6. Simulation outputs are scenario-based decision-support products, not official warnings. The specification explicitly requires uncertainty and input assumptions to be shown.

## Phase 5 — Scenario Generation

A persisted base scenario can generate a deterministic scenario family before hydrodynamic execution.
Supported variants are partial breach (25%), major breach (50%), extreme breach (100%), and controlled water release.
The breach preset fractions are an explicit implementation convention: the percentage is applied linearly to breach
width, breach depth, and initial discharge. This is recorded in each variant's `assumptions` and is not represented as
a physical law of SPH or Delft3D. Controlled release requires an explicit discharge input and contains no breach parameters.

Persistence is provided by `scenario_variants`, linked to the base `scenarios` row. Generated variants are idempotency-
protected per base scenario and variant code. The API exposes generation and listing under the project/scenario resource.
