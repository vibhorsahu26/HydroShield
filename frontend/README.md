# HydroShield — Integrated Full Stack

HydroShield is an automated dam-break and flood-inundation decision-support workflow built from the original HydroShield specification.

## Stack

- Frontend: React + Vite + Tailwind CSS + Leaflet
- API: Python + FastAPI
- Geospatial: Rasterio, GeoPandas, Shapely, PyProj, NumPy/Pandas
- Persistence: PostgreSQL + PostGIS in production; SQLite for deterministic tests
- Hydrodynamics: DualSPHysics 5.4.3 SPH adapter + Delft3D FM adapter
- Analysis: flood metrics, exposure, model/scenario comparison
- Earth observation: Google Earth Engine / Sentinel workflows
- Exports: GeoJSON, SHP, KML, GeoTIFF, CSV, JSON

## Integrated Docker deployment

1. Copy `.env.example` to `.env`.
2. Set a strong `POSTGRES_PASSWORD`.
3. Put the approved DualSPHysics 5.4.3 Linux binaries in `../solvers/dualsphysics/bin/` when real SPH execution is required.
4. Configure an Earth Engine Cloud project when satellite validation is required.
5. Run from the repository root:

```bash
docker compose up --build
```

Open `http://localhost:8080`.

The frontend is built with `VITE_API_BASE_URL=/api/v1`. Nginx proxies `/api/` to FastAPI, so the browser uses one origin for the integrated deployment.

## Deployment configuration

For a real public hostname, replace the local host/origin values with explicit HTTPS values in the API environment. The backend production profile intentionally disables OpenAPI/docs and rejects wildcard hosts/origins.

Authentication/identity is not invented here because it was not specified in the original HydroShield requirements. Put the stack behind the organization's authentication and ingress layer for internet-facing use.

## Verification

Backend:

```bash
cd backend
python -m pytest -q -W error
```

Frontend source/integration checks:

```bash
cd frontend
node scripts/source-contract-check.mjs
HYDROSHIELD_API_URL=http://127.0.0.1:8000/api/v1 npm run test:integration
```

Vercel runs `npm ci` and `npm run build` from the `frontend/` project. The repository also includes a root `vercel.json` for deploying the monorepo without changing the project root.

## Original-system safety boundary

HydroShield outputs are scenario-based decision-support products, not guaranteed emergency predictions. Terrain quality, breach assumptions, river geometry, roughness, boundary conditions, resolution and hydrologic inputs materially affect results.
