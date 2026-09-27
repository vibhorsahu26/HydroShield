# HydroShield Phase 6 — Hydrodynamic Model Adapters

## Concrete SPH engine: DualSPHysics 5.4.3

HydroShield uses **DualSPHysics 5.4.3** as its concrete SPH implementation. The official DualSPHysics download page currently lists `DualSPHysics_v5.4.3.zip` as the latest packaged version and the project describes DualSPHysics as a C++/CUDA/OpenMP SPH solver for free-surface flows, including dam-break applications.

For HydroShield, the native toolchain is intentionally explicit:

1. **GenCase** — turns `Case_Def.xml` into the initial DualSPHysics case files.
2. **DualSPHysics** — executes the particle simulation in GPU or CPU mode.
3. **PartVTK** — converts binary particle output into CSV data for backend analysis.

The adapter uses the official command shapes documented by DualSPHysics, including `GenCase Case_Def Case`, `-cpu`, `-gpu[:id]`, `-tmax:`, `-tout:`, `-sv:`, and PartVTK `-dirdata` / `-savecsv` / `-onlytype` / `-vars` options.

### Input contract

A project supplies a native `Case_Def.xml` template. HydroShield validates the XML, substitutes explicit `{HYDROSHIELD_*}` placeholders, and records the final native case plus scenario/provenance information in `sph_input.json` and `hydroshield_model_manifest.json`.

When `{HYDROSHIELD_BATHYMETRY_FILE}` is present, the Phase 4 DEM is converted into an XYZ point file for the native `<drawbathymetry>` / `<zpoints>` mechanism.

### Output contract

The solver is configured for binary particle output. PartVTK then produces `PartFluid*.csv` files. The parser derives particle-count and velocity metrics from these files. Detailed DEM-relative water depth, inundated area, arrival time, flood extent and exposure analysis remain downstream Phase 8 responsibilities; they must not be fabricated from particle counts alone.

### Hardware

Default execution is GPU mode with GPU index `0`. CPU mode is supported as an explicit fallback. The executable directory or individual binaries are configured through `HYDROSHIELD_DUAL_SPH_*` settings.

### Verification boundary

The repository verifies the complete three-step command contract with deterministic fake binaries and validates generated XML/XYZ input and particle CSV parsing. Actual DualSPHysics numerical execution is only considered verified when the native v5.4.3 binaries are installed on the target machine.

## Delft3D / D-Flow FM

The adapter supports `dflowfm --autostartstop <file.mdu>` and DIMR `run_dimr <dimr_config.xml>` execution. It remains separate from the SPH adapter and shares the same common runner/result contract.

## Common execution behavior

All model pipelines use:

- `shell=False`;
- dedicated working directories;
- per-step stdout/stderr logs plus aggregate logs;
- one global timeout budget;
- explicit non-zero exit handling;
- adapter-specific result parsing.

Phase 7 will move this execution into persistent background simulation jobs.

## Automatic model generation

HydroShield can generate native starter inputs directly from the Phase 4 processed DEM and Phase 5 scenario variant. The normal browser workflow therefore does not require users to upload solver case ZIP files.

- DualSPHysics: generates `Case_Def.xml` and a DEM-derived `HydroShield_Bathymetry.csv` for automatic cases plus an assumption/provenance manifest.
- Delft3D FM: generates a small 2D NetCDF net, initial water-level XYZ file, `hydroshield.mdu`, and `dimr_config.xml`.

These generated cases are intentionally conservative prototype configurations. Detailed roughness, open-boundary forcing, hydraulic structures, and site-specific calibration remain explicit assumptions and should be reviewed before operational use.

Manual ZIP upload remains available through the frontend's Advanced Mode for expert-prepared solver cases.
