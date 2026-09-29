# HydroShield 🌊🛡️

### Flood Scenario Simulation, Geospatial Analysis, and Decision Support Platform

HydroShield is a flood-risk and hydrodynamic simulation platform
designed to bring scenario configuration, geospatial dataset validation,
hydraulic/hydrodynamic solver execution, persistence, and result
visualization into a unified workflow.

The project combines a FastAPI backend, geospatial data processing,
database persistence, solver adapters, runtime validation, and a
web-based interface for configuring and inspecting flood scenarios.

> **Current implementation:** HydroShield is a
> prototype/research-oriented platform. Solver availability, dataset
> coverage, runtime configuration, and simulation capabilities depend on
> the local or deployed environment and the configured solver
> installations.

------------------------------------------------------------------------

## 🎯 Problem

Flood modelling workflows often require several disconnected tools and
manual preparation steps.

A typical workflow may involve:

-   Preparing terrain and boundary datasets.
-   Validating GeoTIFF, GeoJSON, and CSV inputs.
-   Configuring a flood scenario.
-   Selecting an appropriate hydrodynamic solver.
-   Checking whether the required runtime is actually available.
-   Running a simulation.
-   Persisting scenarios, runs, and results.
-   Inspecting outputs through a web interface.

HydroShield explores a unified workflow that reduces the gap between
**scenario preparation**, **simulation execution**, and **result
interpretation**.

The project follows the general pipeline:

``` text
Flood Scenario
      ↓
Dataset Validation
      ↓
Geospatial Preparation
      ↓
Solver Selection
      ↓
Runtime Preflight
      ↓
Hydrodynamic Simulation
      ↓
Result Processing
      ↓
Database Persistence
      ↓
Visualization & Decision Support
```

------------------------------------------------------------------------

## 💡 Solution

HydroShield provides a backend-driven workflow for flood scenario
management and simulation.

The platform is designed to:

1.  Create and validate flood scenarios.
2.  Validate supported geospatial and tabular datasets.
3.  Store scenario and simulation metadata using SQLAlchemy/Alembic
    persistence.
4.  Detect available simulation runtimes and solver capabilities.
5.  Support solver adapters for configured hydrodynamic engines.
6.  Provide runtime preflight information before execution.
7.  Handle solver availability and GPU/CPU fallback where supported.
8.  Execute simulations through the configured solver runtime.
9.  Store and expose simulation information through APIs.
10. Present scenario and runtime status through the web interface.

The core idea is to make flood simulation **traceable, validated, and
accessible through a single application workflow**, rather than treating
solver execution as an isolated command-line task.

------------------------------------------------------------------------

## 🧠 Current Technical Pipeline

``` text
                         Flood Scenario
                              │
                              ▼
                     Scenario Validation
                              │
                              ▼
                    Dataset Validation
                   ┌──────────┼──────────┐
                   │          │          │
                   ▼          ▼          ▼
                GeoTIFF    GeoJSON      CSV
                   │          │          │
                   └──────────┼──────────┘
                              ▼
                    Geospatial Processing
                              │
                              ▼
                     Solver Preflight
                              │
                 ┌────────────┴────────────┐
                 │                         │
                 ▼                         ▼
          DualSPHysics                 Delft3D
                 │                         │
                 └────────────┬────────────┘
                              ▼
                       Runtime Execution
                              │
                              ▼
                     Simulation Results
                              │
                              ▼
                    Persistence Layer
                              │
                              ▼
                         FastAPI
                              │
                              ▼
                       Web Dashboard
```

------------------------------------------------------------------------

## ✨ Features

### 🌊 Flood Scenario Management

-   Scenario creation and validation.
-   Structured flood-simulation configuration.
-   Scenario metadata persistence.
-   Simulation run tracking.
-   Validation before expensive solver execution.

### 🗺️ Geospatial Data Processing

-   GeoTIFF dataset validation.
-   GeoJSON dataset validation.
-   CSV dataset validation.
-   Geospatial metadata inspection.
-   Dataset compatibility checks.
-   Preparation of inputs for simulation workflows.

### ⚙️ Solver Integration

HydroShield is designed around solver adapters so that different
hydrodynamic engines can be integrated without coupling the entire
application to a single solver.

Current solver work includes:

-   **DualSPHysics 5.4.3**
-   **Delft3D**

The backend also includes solver/runtime checks so unavailable engines
can be identified before execution.

### 🖥️ Runtime Management

-   Solver preflight checks.
-   Runtime availability detection.
-   GPU detection where supported.
-   CPU fallback handling where supported.
-   Automatic provisioning workflow for configured DualSPHysics
    environments.
-   Runtime status exposed to the application interface.
-   Solver choices can be disabled when their required runtime is
    unavailable.

### 🗄️ Persistence

HydroShield uses a database-backed persistence layer for application
state.

The persistence workflow includes:

-   SQLAlchemy models.
-   Alembic migrations.
-   Scenario persistence.
-   Simulation/run metadata.
-   Database-backed application state.
-   Supabase/PostgreSQL-compatible deployment architecture.

### 🌐 Web Application

The web interface is designed to expose:

-   Scenario configuration.
-   Dataset information.
-   Solver selection.
-   Runtime availability.
-   Simulation state.
-   Results and related information.

Advanced workflows can expose custom case upload functionality while
keeping the normal scenario workflow simpler.

------------------------------------------------------------------------

## 🏗️ System Architecture

``` text
                         User
                          │
                          ▼
                  Web Application
                          │
                          ▼
                    FastAPI API
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
 Scenario Services   Dataset Services   Runtime Services
        │                 │                 │
        │                 ▼                 │
        │          GeoTIFF/GeoJSON/CSV      │
        │                                   │
        └─────────────────┬─────────────────┘
                          ▼
                   Solver Adapters
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
              DualSPHysics   Delft3D
                    │           │
                    └─────┬─────┘
                          ▼
                   Simulation Output
                          │
                          ▼
                  Persistence Layer
                          │
                          ▼
                    PostgreSQL
                  / Supabase DB
```

------------------------------------------------------------------------

## 🛠️ Technology Stack

### Backend

-   Python
-   FastAPI
-   Uvicorn
-   Pydantic
-   SQLAlchemy
-   Alembic
-   Pandas
-   NumPy
-   GeoPandas
-   Shapely
-   Rasterio
-   Docker

### Database

-   PostgreSQL
-   Supabase
-   SQLAlchemy ORM
-   Alembic migrations

### Geospatial Data

HydroShield's validation and processing workflow is designed around:

-   GeoTIFF raster datasets
-   GeoJSON vector datasets
-   CSV/tabular datasets
-   Coordinate reference systems
-   Spatial metadata
-   Terrain and flood-model input data

### Hydrodynamic Simulation

-   DualSPHysics 5.4.3
-   Delft3D
-   Solver adapter architecture
-   Runtime/preflight validation
-   GPU detection and fallback where supported

### Frontend

The frontend provides the web-based scenario and simulation interface
and communicates with the FastAPI backend through HTTP APIs.

### Deployment

The backend is designed to run in containerized environments using
Docker.

A database-backed deployment can use:

``` text
Frontend
   │
   ▼
FastAPI Backend
   │
   ▼
Supabase / PostgreSQL
```

------------------------------------------------------------------------

## 📁 Repository Structure

The exact structure may evolve as additional simulation phases are
implemented. A representative HydroShield repository is organized around
the following components:

``` text
HydroShield/
│
├── README.md
├── LICENSE
├── .gitignore
│
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── ...
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── solvers/
│   │   ├── validators/
│   │   ├── config.py
│   │   ├── db.py
│   │   └── main.py
│   │
│   ├── alembic/
│   ├── scripts/
│   ├── tests/
│   ├── data/
│   ├── models/
│   ├── .env.example
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── ...
│
└── ...
```

> The structure above describes the intended organization of the
> project. Use the actual repository tree as the source of truth when
> documenting a particular release.

------------------------------------------------------------------------

## 🔌 API

HydroShield exposes its application functionality through FastAPI.

The backend includes API areas for:

### Health & Runtime

Used to verify that the service is running and inspect runtime/solver
availability.

``` http
GET /api/health
```

Runtime and solver preflight endpoints are also part of the
runtime-management workflow.

### Scenarios

Scenario endpoints are responsible for:

-   Creating scenarios.
-   Validating scenario configuration.
-   Retrieving scenario information.
-   Managing simulation-related metadata.

### Datasets

Dataset validation endpoints/processes handle supported:

``` text
GeoTIFF
GeoJSON
CSV
```

Validation can include file format, metadata, spatial information, and
compatibility checks required by the simulation workflow.

### Simulation

Simulation functionality is responsible for:

-   Solver selection.
-   Runtime preflight.
-   Simulation execution.
-   Run state.
-   Result information.

### Database

Database-backed endpoints/services persist application state through
SQLAlchemy and Alembic-managed schema changes.

> **Note:** Exact endpoint paths should be generated from the current
> FastAPI routes rather than copied from this README if the API evolves.

------------------------------------------------------------------------

## 💻 Local Development

### Prerequisites

Depending on the workflow being used, you may need:

-   Python 3.11+
-   Node.js and npm
-   Git
-   Docker
-   Docker Compose
-   PostgreSQL/Supabase access
-   A supported hydrodynamic solver runtime for actual simulation
    execution

For solver-specific execution, additional system dependencies may be
required.

------------------------------------------------------------------------

### Clone

``` bash
git clone <your-hydroshield-repository-url>
cd HydroShield
```

------------------------------------------------------------------------

### Backend

Create a virtual environment:

``` bash
cd backend
python -m venv .venv
```

#### Windows

``` powershell
.venv\Scripts\activate
```

#### Linux/macOS

``` bash
source .venv/bin/activate
```

Install dependencies:

``` bash
pip install -r requirements.txt
```

Run the API:

``` bash
uvicorn app.main:app --reload
```

The development server is normally available at:

``` text
http://127.0.0.1:8000
```

FastAPI documentation:

``` text
http://127.0.0.1:8000/docs
```

------------------------------------------------------------------------

### Frontend

From the frontend directory:

``` bash
cd frontend
npm install
npm run dev
```

The development URL depends on the Vite configuration, commonly:

``` text
http://localhost:5173
```

------------------------------------------------------------------------

## 🗄️ Database Setup

HydroShield uses SQLAlchemy for persistence and Alembic for database
migrations.

Configure the database connection through the project's environment
configuration.

Example:

``` text
DATABASE_URL=<your-postgresql-or-supabase-connection-string>
```

Run migrations using the project's Alembic configuration:

``` bash
alembic upgrade head
```

> Use the migration commands and environment variables defined by the
> current backend configuration if they differ from the examples above.

------------------------------------------------------------------------

## ⚙️ Solver Runtime Setup

HydroShield supports a solver-adapter approach so that runtime
configuration is separated from the main application.

### DualSPHysics

The project targets:

``` text
DualSPHysics 5.4.3
```

The Docker workflow includes support for automatic provisioning when the
corresponding environment configuration is enabled.

The runtime should be checked before a simulation is started.

A typical workflow is:

``` text
Application
    ↓
Solver Preflight
    ↓
DualSPHysics Runtime Available?
    ├── No → Disable/Report Solver
    │
    └── Yes
          ↓
       Execute
```

### Delft3D

Delft3D is integrated through a solver adapter.

The adapter is responsible for isolating Delft3D-specific execution
details from the rest of the application.

Because solver installations differ by environment, the runtime should
be validated before attempting execution.

------------------------------------------------------------------------

## 🐳 Docker

HydroShield includes a containerized backend workflow.

Build the backend image:

``` bash
docker build -t hydroshield-backend .
```

Run the container according to the environment configuration:

``` bash
docker run --env-file .env -p 8000:8000 hydroshield-backend
```

For local multi-service development, use the repository's Docker Compose
configuration when available:

``` bash
docker compose up --build
```

### Solver provisioning

The Docker workflow can be configured to automatically provision the
supported DualSPHysics runtime.

When automatic provisioning is enabled, the image/build process verifies
that the expected solver files are present before the runtime is
considered usable.

------------------------------------------------------------------------

## 🔐 Environment Variables

HydroShield uses environment variables for deployment-specific
configuration.

Typical configuration areas include:

``` text
DATABASE_URL=
SUPABASE_URL=
SUPABASE_KEY=
HYDROSHIELD_AUTO_PROVISION_DUALSPHYSICS=
```

Additional solver, CORS, storage, and application settings may be
required depending on the deployment.

Do not commit:

-   Database credentials.
-   Supabase secrets.
-   API keys.
-   Local `.env` files.
-   Solver credentials or private configuration.
-   Generated credentials or tokens.

Use `.env.example` to document required variables without exposing
secrets.

------------------------------------------------------------------------

## 🧪 Testing & Verification

HydroShield follows a phase-based development and verification workflow.

The project should be tested after each major implementation phase, with
previous functionality rechecked through regression tests.

Verification areas include:

### Backend

-   API startup.
-   Scenario validation.
-   Dataset validation.
-   Database migrations.
-   Persistence.
-   Solver preflight.
-   Runtime detection.
-   Simulation execution.

### Geospatial

-   GeoTIFF validation.
-   GeoJSON validation.
-   CSV validation.
-   Coordinate/reference-system handling.
-   Input compatibility.

### Solvers

-   DualSPHysics runtime detection.
-   DualSPHysics execution.
-   Delft3D runtime detection.
-   Delft3D adapter execution.

### Frontend

-   Scenario creation.
-   Dataset selection/upload.
-   Solver availability.
-   Runtime status.
-   Simulation state.
-   Result presentation.

A successful application startup alone should not be treated as proof
that a hydrodynamic solver can successfully execute a real simulation.

------------------------------------------------------------------------

## 📊 Model & Simulation Evaluation

HydroShield is primarily a simulation and decision-support platform
rather than a single predictive ML model.

Simulation results should therefore be evaluated using documented test
cases and appropriate hydraulic/hydrodynamic validation procedures.

The project should avoid unsupported claims such as:

-   Unverified accuracy percentages.
-   Unsupported improvements over established solvers.
-   Generalized flood-prediction accuracy from a limited test case.
-   Production-readiness claims based only on successful API startup.

Any performance or accuracy numbers should come from reproducible
experiments and should document:

-   Dataset/test case.
-   Solver configuration.
-   Evaluation metric.
-   Hardware/runtime environment.
-   Baseline.
-   Validation procedure.

------------------------------------------------------------------------

## ⚠️ Current Limitations

HydroShield is a prototype/research-oriented flood simulation platform.

Current limitations include:

-   Solver availability depends on the deployment environment.
-   Hydrodynamic simulation requires correctly configured solver
    runtimes.
-   Different solvers have different input formats and runtime
    requirements.
-   GPU acceleration is dependent on hardware, drivers, and solver
    support.
-   CPU fallback does not necessarily provide equivalent performance.
-   Geospatial datasets must satisfy the requirements of the configured
    simulation workflow.
-   Delft3D and DualSPHysics require environment-specific validation.
-   Broader validation across different flood scenarios and geographic
    areas is required before making generalized performance claims.
-   Simulation outputs should be interpreted in the context of the input
    data, boundary conditions, solver configuration, and numerical
    assumptions.

------------------------------------------------------------------------

## 🔄 Development Phases

HydroShield is being developed incrementally.

### Phase 1 --- FastAPI Foundation & Scenario Validation

Completed foundation work includes:

-   FastAPI application structure.
-   Initial scenario validation.
-   Backend API foundation.

### Phase 2 --- Dataset Validation

Completed dataset-validation work includes:

-   GeoTIFF validation.
-   GeoJSON validation.
-   CSV validation.
-   Geospatial/data compatibility checks.

### Phase 3 --- Persistence

The persistence layer introduces:

-   SQLAlchemy models.
-   Alembic migrations.
-   Database-backed scenario and simulation state.
-   PostgreSQL/Supabase integration.

### Subsequent Simulation Phases

Further development focuses on:

-   Solver runtime management.
-   DualSPHysics provisioning.
-   GPU detection/fallback.
-   Delft3D integration.
-   Solver preflight.
-   Actual solver execution.
-   Result handling.
-   UI runtime status.
-   End-to-end regression testing.

------------------------------------------------------------------------

## 🤝 Contributing

Create a feature branch:

``` bash
git checkout -b feature/your-feature
```

Make changes and run the relevant tests.

Then:

``` bash
git add .
git commit -m "Describe your change"
git push origin feature/your-feature
```

For substantial changes, document:

-   What changed.
-   Why it changed.
-   How it was tested.
-   Any new environment variables.
-   Any solver/runtime requirements.
-   Any database migration requirements.

------------------------------------------------------------------------

## 👥 Project

HydroShield is a research-oriented software project focused on
integrating flood scenario management, geospatial data validation,
hydrodynamic simulation, and decision-support workflows into a single
platform.

------------------------------------------------------------------------

## 📄 License

The project software should be distributed under the license included in
the repository.

Third-party software, datasets, maps, terrain data, solver packages,
imagery, and other external assets remain subject to their respective
licenses and terms.

In particular, users should review the licensing and redistribution
requirements of:

-   DualSPHysics.
-   Delft3D.
-   Geospatial datasets.
-   Terrain/elevation datasets.
-   Mapping libraries and map providers.
-   Any third-party datasets used for flood scenarios.

------------------------------------------------------------------------

## ⭐ Project Flow

``` text
Flood Scenario
      ↓
Scenario Validation
      ↓
Dataset Validation
      ↓
GeoTIFF / GeoJSON / CSV
      ↓
Geospatial Processing
      ↓
Database Persistence
      ↓
Solver Preflight
      ↓
DualSPHysics / Delft3D
      ↓
Simulation Execution
      ↓
Result Processing
      ↓
FastAPI
      ↓
Web Dashboard
```

------------------------------------------------------------------------

## 📌 Project Status

HydroShield is under active development.

The backend is being implemented phase-by-phase with validation and
regression testing after major changes. Solver execution and runtime
behavior should be verified in the target deployment environment before
being considered production-ready.
