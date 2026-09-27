# HydroShield Phase 7 — Background Simulation Jobs

Phase 7 makes model execution asynchronous while keeping job state durable in PostgreSQL/SQLite.

## Job lifecycle

`queued -> preparing -> running -> processing -> completed`

Failure and control states:

`failed`, `retrying`, `cancel_requested`, `cancelled`

## API

`POST /api/v1/simulations` queues a simulation and returns HTTP 202.

`GET /api/v1/simulations/{job_id}` returns the durable job state.

`GET /api/v1/simulations/projects/{project_id}` lists project jobs.

`POST /api/v1/simulations/{job_id}/cancel` requests cancellation.

## Persistence

The `simulation_jobs` table stores project/scenario/variant/model identity, lifecycle state, progress, attempt counters, timeout, serialized Phase 6 preparation configuration, working directory, manifest, result payload, error information, cancellation flag and timestamps.

Migration: `0003_simulation_jobs`.

## Execution

`SimulationJobManager` uses a bounded in-process `ThreadPoolExecutor`. Each worker opens its own SQLAlchemy session. Native solver execution is still performed by the Phase 6 `CommandRunner`, which now supports progress callbacks, global timeouts and cooperative cancellation via `Popen`.

On application startup, interrupted `running`, `preparing`, `processing` and `cancel_requested` jobs are recovered to `queued` and resubmitted. Terminal jobs are never resubmitted.

## Retry behavior

A job can be configured with `max_attempts` from 1 to 5. Failed solver executions and preparation exceptions are retried until the attempt budget is exhausted. A final failure becomes `failed` and retains the error and most recent result payload.

## Production boundary

This phase provides durable state and reliable native-process control, but the executor is intentionally in-process. A production/HPC deployment can replace the executor with Celery/RQ or a dedicated worker service without changing the API or database job contract.
