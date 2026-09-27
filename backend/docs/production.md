# HydroShield production deployment

HydroShield's API is designed for a single Uvicorn process per application instance because the Phase 7 job manager is an in-process bounded executor backed by durable SQL job state. Do not start multiple Uvicorn worker processes in the same container unless the job execution architecture is replaced by a separate worker service.

## Required production settings

Set a PostgreSQL/PostGIS `HYDROSHIELD_DATABASE_URL`, explicit `HYDROSHIELD_ALLOWED_HOSTS`, explicit `HYDROSHIELD_ALLOWED_ORIGINS`, and `HYDROSHIELD_DOCS_ENABLED=false`. Use a strong database password from a secret manager rather than committing credentials to files.

`HYDROSHIELD_RUN_MIGRATIONS_ON_STARTUP=true` is suitable for a single-instance deployment. In a multi-replica deployment, run `alembic upgrade head` as a separate release/migration job and keep startup migrations disabled.

## HTTPS and proxying

Terminate TLS at a reverse proxy/load balancer such as Caddy, Traefik, Nginx or a cloud load balancer. Pass only trusted proxy IPs through `HYDROSHIELD_FORWARDED_ALLOW_IPS`. Set `HYDROSHIELD_ENFORCE_HTTPS=true` only when the application should itself reject plain HTTP; otherwise enforce HTTPS at the proxy.

## Storage

Mount persistent storage for `/app/data`. Dataset uploads, model working directories, processed geospatial artifacts and exports are filesystem-backed in this prototype. Use a durable volume or object-storage-backed replacement before horizontal scaling.

## Simulation workers

Set `HYDROSHIELD_JOB_WORKER_COUNT` to a value appropriate for available CPU/RAM/GPU capacity. Each worker can spawn a native solver process. Do not size this number from HTTP request concurrency alone.

## Optional external integrations

DualSPHysics binaries must be mounted/configured separately. Google Earth Engine requires the optional client, a Google Cloud project and authentication. These external dependencies are intentionally not bundled into the API image.

## Health endpoints

`GET /api/v1/health` is a liveness endpoint. `GET /api/v1/health/ready` checks database connectivity and application storage; PostgreSQL deployments also require PostGIS availability.


### DualSPHysics runtime note
The public DualSPHysics v5.4.3 Linux binary directory currently publishes GenCase, the GPU solver, PartVTK and shared libraries, but not `DualSPHysics5.4CPU_linux64`. HydroShield therefore treats the CPU executable as optional. GPU deployments use the provisioned GPU runtime; CPU-only fallback requires a separately supplied or built CPU executable.
