# Phase 8 — Result Processing and Analysis

HydroShield separates numerical solver execution from result analysis. Solver adapters produce native artifacts; Phase 8 consumes analysis-ready GeoTIFF/CSV/vector products and computes common flood and exposure metrics.

## Analysis input contract

Required:

- `water_depth_raster`: single-band projected GeoTIFF, metres of water depth.

Optional:

- `velocity_raster`: single-band projected GeoTIFF, m/s.
- `arrival_time_raster`: single-band projected GeoTIFF, seconds from simulation start.
- `water_level_raster`: single-band projected GeoTIFF, metres above datum.
- `dem_raster`: single-band projected GeoTIFF used with depth to derive water level.
- `discharge_csv`: CSV with a recognised discharge column such as `Q`, `discharge_m3s`, or `flow_m3s`.
- `exposure_layers`: named vector files for settlements, roads, bridges, infrastructure, or other project-defined layers.

## Core calculations

Flood extent is generated from `water_depth > flood_threshold_m`. Inundated area is flooded-pixel count multiplied by projected pixel area. The flood mask is polygonized into GeoJSON for downstream GIS use.

Maximum water level is taken from a provided water-level raster when available; otherwise it is derived as `DEM + water depth` on the common analysis grid.

First arrival time is the minimum finite arrival-time value among flooded cells.

Exposure is an intersection analysis between the generated flood polygon and the supplied settlement/infrastructure layers. The backend reports affected feature counts and, for linear/polygon layers, intersected length/area where appropriate. No population total or damage-cost estimate is inferred unless an explicit dataset/valuation model is supplied later.

## Comparison contract

A model comparison requires the same scenario variant and different hydrodynamic models. A scenario comparison requires the same hydrodynamic model. Both analyses must use the same flood-depth threshold.

Continuous fields are aligned to a common projected grid covering the union of the two raster extents. Difference is always `right - left`. Reported statistics include count, MAE, RMSE, bias and maximum absolute difference.

Flood comparison reports left/right areas, intersection, union, left-only/right-only areas, and intersection-over-union (IoU).

## Persistence

`analysis_results` stores the analysis metrics, exposure summary, generated artifacts, warnings and assumptions. `result_comparisons` stores model/scenario comparison metrics and artifacts.

The analysis record also retains its source input paths and links to the Phase 7 simulation job through `simulation_job_id`.

## Native SPH result bridge

For completed HydroShield-managed SPH jobs, the backend can automatically convert `PartFluid*.csv` particle frames into analysis-ready GeoTIFFs without a user upload. The common analysis grid is the persisted preprocessed projected DEM grid. For each grid cell, HydroShield reconstructs maximum fluid-particle elevation and speed from the particle frames; maximum water depth is `max_particle_elevation - DEM`, clipped at zero, and first arrival is the first output frame whose reconstructed depth exceeds the configured flood threshold. The generated depth, velocity, arrival-time and maximum water-level rasters are then passed through the normal Phase 8 analysis processor so flood extent, inundated area, exposure and dashboard artifacts use the same validation/persistence path as manually supplied analysis inputs.

This is a particle-to-raster reconstruction method for the prototype, not a replacement for a solver-native gridded water-depth product. The assumptions and reconstruction provenance are retained on the analysis record, and a warning is emitted when particles fall outside the persisted DEM grid.
