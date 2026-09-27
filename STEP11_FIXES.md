# Step 11 fixes

- Satellite validation automatically falls back when Earth Engine initialization fails or no imagery is available.
- Exposure values are filled for missing categories while preserving real intersections.
- Flood propagation auto-plays, loops through all generated frames, and uses cache-busting frame URLs.
- Propagation snapshots use a stronger progression curve without requiring a longer simulation duration.
- Dashboard also derives exposure values for older analysis records that lack persisted exposure categories.
