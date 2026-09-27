# HydroShield Backend

FastAPI backend for the HydroShield automated dam-break and flood-inundation modelling platform.

## Completed phases

### Phase 1 — FastAPI foundation
- application factory and routing
- configuration and logging
- structured application errors
- scenario validation

### Phase 2 — Dataset validation
- DEM GeoTIFF validation
- river/vector validation
- hydrology/rainfall CSV validation
- supported dataset typing and metadata extraction

### Phase 3 — Persistence + PostGIS
- SQLAlchemy persistence models
- Alembic migrations
- PostgreSQL/PostGIS-native spatial column and GiST index
- project, dataset, scenario and spatial-feature repositories
- deterministic SQLite test backend

### Phase 4 — Geospatial preprocessing
- projected metric CRS selection/validation
- DEM clipping, reprojection and resampling
- river geometry preparation
- buffered computational-domain generation
- aligned domain-mask GeoTIFF
- Phase 2 validation integrated before preprocessing

### Phase 5 — Scenario generation
- partial, major and extreme breach presets
- explicit controlled-release scenario
- transparent generator version and assumptions
- persisted scenario variants

### Phase 6 — Hydrodynamic model adapters
- common `ModelAdapter` contract
- multi-step native-toolchain runner with a global timeout budget
- per-step and aggregate stdout/stderr logs
- concrete **DualSPHysics 5.4.3** SPH adapter
- DualSPHysics GenCase → solver → PartVTK pipeline
- GPU and CPU execution modes
- HydroShield placeholder substitution in `Case_Def.xml`
- Phase 4 DEM → XYZ bathymetry generation when requested by the case template
- DualSPHysics particle CSV parsing
- Delft3D/D-Flow FM adapter for `dflowfm --autostartstop` and DIMR `run_dimr`
- model manifest linking Phase 5 scenario parameters and Phase 4 preprocessing artifacts

### Phase 8 — Result processing, flood metrics and comparison
- analysis-ready raster validation
- flood-depth threshold → inundation mask and flood polygon
- maximum depth, velocity, arrival time, water level and discharge metrics where source products exist
- settlement/road/bridge/critical-infrastructure exposure overlay
- persisted analysis results and assumptions
- common-grid SPH/Delft3D and scenario comparison with spatial agreement metrics
- difference GeoTIFF artifacts

### Data acquisition closure
- validated uploads can now be stored under a project-scoped storage root
- filenames are sanitized and prefixed with a generated identifier
- the stored object is immediately persisted as a dataset record
- invalid datasets are rejected before storage

## Local development

```bash
python -m pytest
alembic -x db_url=sqlite:///./hydroshield.db upgrade head
uvicorn app.main:app --reload
```

For PostgreSQL/PostGIS:

```text
HYDROSHIELD_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

A real PostGIS connectivity test runs only when `HYDROSHIELD_TEST_POSTGRES_URL` is configured and a PostGIS service is reachable. The code and migration contract are otherwise covered by deterministic local tests.

## DualSPHysics configuration

HydroShield targets DualSPHysics 5.4.3. The official package supplies the native binaries and examples; the repository source tree provides the current v5.4 source/examples. Configure either the binary directory or individual executables:

```text
HYDROSHIELD_DUAL_SPH_BIN_DIR=/path/to/DualSPHysics/bin/linux
HYDROSHIELD_DUAL_SPH_DEVICE=gpu
HYDROSHIELD_DUAL_SPH_GPU_ID=0
# Optional explicit overrides:
# HYDROSHIELD_DUAL_SPH_GENCASE=/path/to/GenCase_linux64
# HYDROSHIELD_DUAL_SPH_SOLVER_GPU=/path/to/DualSPHysics5.4_linux64
# HYDROSHIELD_DUAL_SPH_SOLVER_CPU=/path/to/DualSPHysics5.4CPU_linux64
# HYDROSHIELD_DUAL_SPH_PARTVTK=/path/to/PartVTK_linux64
HYDROSHIELD_DUAL_SPH_OUTPUT_INTERVAL_S=1.0
```

A project supplies a native `Case_Def.xml` under the `native_input_directory`. HydroShield validates it, substitutes only documented `{HYDROSHIELD_*}` placeholders, and keeps the final XML and manifest in the model run directory.

The adapter does **not** synthesize a physically complete river tank, breach wall, roughness model or boundary-condition setup from a few scalar scenario values. Those solver-native modelling choices remain part of the project-specific `Case_Def.xml`. This keeps scenario generation and solver physics separate.

For the bathymetry path, a template can use:

```xml
<drawbathymetry>
  <zpoints file="{HYDROSHIELD_BATHYMETRY_FILE}" />
  <grid dp="5" />
</drawbathymetry>
```

The adapter then converts the Phase 4 processed DEM to an XYZ point file and substitutes the generated filename.

## Model execution architecture

```text
Phase 4 preprocessing artifacts
            +
Phase 5 persisted scenario variant
            |
            v
     DualSPHysics adapter
            |
      +-----+------+
      |            |
   GenCase     prepared Case_Def.xml
      |
      v
 DualSPHysics CPU/GPU
      |
      v
    *.bi4
      |
      v
    PartVTK
      |
      v
 PartFluid*.csv
      |
      v
 common result parser
```

Phase 7 puts these long-running native steps behind persistent background jobs rather than executing them in the request lifecycle.

## Phase 8 result analysis

See `docs/result-analysis.md`. Analysis begins from the completed simulation job and consumes analysis-ready result products. The backend does not invent unsupported hydraulic quantities from raw solver artifacts; a product must be supplied in a compatible spatial/units form.

## Verification boundary

The test suite validates the complete adapter contract with deterministic fake executables, generated DEM/XYZ inputs, native XML substitution, particle CSV parsing, failure propagation and the full Phase 2 → Phase 4 → Phase 5 → Phase 6 integration chain.

Actual DualSPHysics numerical physics are considered verified only after the real v5.4.3 native binaries are installed on the target runtime and a real dam-break case is executed.

## Architecture

See `docs/backend-architecture.md` and `docs/model-adapters.md`.

## Phase 7 — Background Simulation Jobs

Simulation execution is asynchronous and durable through the `simulation_jobs` table. The backend supports queued/preparing/running/processing/completed/failed/retrying/cancel_requested/cancelled states, progress tracking, bounded retries, cancellation and restart recovery. See `docs/background-jobs.md`.

## Phase 9: Satellite validation

Satellite validation is implemented with Google Earth Engine as an optional integration (`pip install -e '.[earthengine]'`). The default Sentinel-1 path uses `OPERA/DSWX/L3_V1/S1` and `BWTR_Binary_water`; Sentinel-2 uses `COPERNICUS/S2_SR_HARMONIZED` with a configurable cloud filter, SCL exclusions, and MNDWI threshold.

Configure `HYDROSHIELD_EARTH_ENGINE_PROJECT`, authenticate Earth Engine, and use `POST /api/v1/satellite/validate` with an existing Phase 8 analysis result and an observation phase (`before`, `during`, or `after`). The service exports an observed water mask, converts it to an extent GeoJSON, reprojects it to the model flood-mask grid, computes spatial agreement, and writes a difference map.

Live Earth Engine execution was not performed in this build environment because the Earth Engine client is not installed here and no authenticated Earth Engine project is available. The provider contract, request construction, local comparison engine, persistence and API integration are fully tested with deterministic provider fixtures.


## Phase 10 — GIS and Analysis Exports

The backend now exports analysis results as GeoJSON, self-contained Shapefile ZIPs, KML, GeoTIFF, CSV, JSON, and consolidated ZIP packages. See `docs/exports.md`.


## Phase 11 — Production Hardening

- PostgreSQL-required production configuration with explicit CORS and Host allowlists
- production API docs disabled by configuration
- request IDs and safe security headers on API responses
- structured validation and sanitized unhandled-error responses
- request body and upload-size controls
- database pool sizing, pre-ping and connection timeouts
- liveness and readiness endpoints; PostgreSQL readiness also checks PostGIS
- non-root Docker runtime, healthcheck and deterministic startup script
- production Docker Compose example with persistent PostGIS/application storage
- CI workflow running compile and strict-warning tests
- single Uvicorn worker per instance preserved for the current in-process simulation executor

See `docs/production.md` for deployment requirements and the rationale for the single-worker constraint.
